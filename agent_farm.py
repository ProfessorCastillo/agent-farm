#!/usr/bin/env python3
"""Minimal configurable succession pilot for a local Ollama model farm."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PERSONA_ARCHETYPES = [
    "archivist",
    "essayist",
    "engineer",
    "folklorist",
    "librarian",
    "playwright",
    "publisher",
    "systems thinker",
]

PERSONA_DISPOSITIONS = [
    "ambitious",
    "careful",
    "iconoclastic",
    "playful",
    "skeptical",
    "patient",
    "restless",
    "strangely literal",
]

PERSONA_VALUES = [
    "clarity",
    "coherence",
    "novelty",
    "emotional force",
    "surprise",
    "craftsmanship",
    "continuity",
    "usefulness",
]


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def api_json(base_url: str, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Ollama at {base_url}: {exc.reason}") from exc


def safe_path(root: Path, relative: str, *, must_exist: bool = False) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError("Absolute paths are not allowed")

    root = root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path escapes the workspace") from exc

    if must_exist and not resolved.exists():
        raise FileNotFoundError(relative)
    return resolved


def list_files(root: Path, path: str = ".") -> str:
    directory = safe_path(root, path, must_exist=True)
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {path}")

    entries = []
    for item in sorted(directory.rglob("*")):
        if len(entries) >= 250:
            entries.append("... listing truncated ...")
            break
        relative = item.relative_to(root)
        if item.is_symlink():
            entries.append(f"SYMLINK {relative}")
        elif item.is_dir():
            entries.append(f"DIR     {relative}/")
        else:
            entries.append(f"FILE    {relative} ({item.stat().st_size} bytes)")
    return "\n".join(entries) if entries else "Workspace is empty."


def read_file(root: Path, path: str, max_read_bytes: int) -> str:
    target = safe_path(root, path, must_exist=True)
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    if target.stat().st_size > max_read_bytes:
        raise ValueError(f"File exceeds the {max_read_bytes}-byte read limit")
    return target.read_text(encoding="utf-8")


def write_file(root: Path, path: str, content: str, max_write_bytes: int, append: bool = False) -> str:
    target = safe_path(root, path)
    encoded = content.encode("utf-8")
    if len(encoded) > max_write_bytes:
        raise ValueError(f"Content exceeds the {max_write_bytes}-byte write limit")
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise ValueError(f"Refusing to overwrite non-regular file: {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as handle:
        handle.write(content)
    verb = "Appended to" if append else "Wrote"
    return f"{verb} {target.relative_to(root)} ({len(encoded)} bytes supplied)"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories inside the inherited project workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative directory; default is ."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file inside the inherited project workspace.",
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace a UTF-8 text file inside the project workspace.",
            "parameters": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_handoff",
            "description": "Write your handoff to the next participant. The harness chooses an immutable numbered filename.",
            "parameters": {
                "type": "object",
                "required": ["content"],
                "properties": {"content": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append UTF-8 text to a file inside the project workspace.",
            "parameters": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    },
]


def execute_tool(
    root: Path,
    call: dict[str, Any],
    config: dict[str, Any],
    required_handoff: str,
) -> tuple[str, dict[str, Any]]:
    function = call.get("function", {})
    name = function.get("name", "")
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")

    public_args = {key: value for key, value in arguments.items() if key != "content"}
    if "content" in arguments:
        public_args["content_bytes"] = len(str(arguments["content"]).encode("utf-8"))

    if name == "list_files":
        result = list_files(root, str(arguments.get("path", ".")))
    elif name == "read_file":
        result = read_file(root, str(arguments["path"]), int(config["max_read_bytes"]))
    elif name == "write_file":
        target = safe_path(root, str(arguments["path"]))
        relative = target.relative_to(root.resolve())
        if relative.parts and relative.parts[0] == "handoffs":
            raise ValueError("Use write_handoff; numbered handoffs cannot be edited with write_file")
        result = write_file(
            root,
            str(arguments["path"]),
            str(arguments["content"]),
            int(config["max_write_bytes"]),
        )
    elif name == "append_file":
        target = safe_path(root, str(arguments["path"]))
        relative = target.relative_to(root.resolve())
        if relative.parts and relative.parts[0] == "handoffs":
            raise ValueError("Use write_handoff; numbered handoffs cannot be edited with append_file")
        result = write_file(
            root,
            str(arguments["path"]),
            str(arguments["content"]),
            int(config["max_write_bytes"]),
            append=True,
        )
    elif name == "write_handoff":
        result = write_file(
            root,
            required_handoff,
            str(arguments["content"]),
            int(config["max_write_bytes"]),
        )
        public_args["path"] = required_handoff
    else:
        raise ValueError(f"Unknown tool: {name}")

    return result, {"tool": name, "arguments": public_args, "ok": True}


def workspace_snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            snapshot[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def contribution_status(
    before: dict[str, str],
    after: dict[str, str],
    required_handoff: str,
) -> tuple[bool, bool, list[str]]:
    changed = sorted({*before, *after} - {key for key in before if before.get(key) == after.get(key)})
    handoff_changed = required_handoff in changed and required_handoff in after
    artifact_changed = any(
        path != "HANDOFF.md" and not path.startswith("handoffs/")
        for path in changed
    )
    return artifact_changed, handoff_changed, changed


def persona(rng: random.Random) -> str:
    disposition = rng.choice(PERSONA_DISPOSITIONS)
    article = "an" if disposition[0].lower() in "aeiou" else "a"
    return (
        f"You are {article} {disposition} {rng.choice(PERSONA_ARCHETYPES)} "
        f"who especially values {rng.choice(PERSONA_VALUES)}."
    )


def schedule(models: list[str], turns: int, rng: random.Random) -> list[str]:
    result: list[str] = []
    while len(result) < turns:
        epoch = list(models)
        rng.shuffle(epoch)
        result.extend(epoch)
    return result[:turns]


def unique_personas(turns: int, rng: random.Random) -> list[str]:
    possible = len(PERSONA_ARCHETYPES) * len(PERSONA_DISPOSITIONS) * len(PERSONA_VALUES)
    if turns > possible:
        raise ValueError(f"Cannot generate {turns} unique personas from {possible} combinations")
    result: list[str] = []
    seen: set[str] = set()
    while len(result) < turns:
        candidate = persona(rng)
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def next_handoff(root: Path) -> tuple[str | None, str]:
    handoff_dir = root / "handoffs"
    numbered: list[tuple[int, Path]] = []
    if handoff_dir.exists():
        for path in handoff_dir.glob("*.md"):
            if path.stem.isdigit():
                numbered.append((int(path.stem), path))

    if numbered:
        last_number, last_path = max(numbered)
        previous = str(last_path.relative_to(root))
        number = last_number + 1
    else:
        legacy = root / "HANDOFF.md"
        previous = "HANDOFF.md" if legacy.exists() else None
        number = 1

    return previous, f"handoffs/{number:04d}.md"


def system_prompt(
    command: str,
    identity: str,
    previous_handoff: str | None,
    required_handoff: str,
) -> str:
    inheritance = (
        f"The most recent predecessor handoff is {previous_handoff}. Read it early."
        if previous_handoff
        else "There is no predecessor handoff; you are the first participant."
    )
    return f"""You are one temporary participant in a project continued by a succession of independent AI models.

Original human command:

    {command}

Temporary persona:

    {identity}

{inheritance}

Inspect the inherited workspace and decide for yourself what the project should become and what contribution matters most now. You may preserve, reinterpret, or reject earlier decisions. Do not ask the human for clarification.

During this turn you must:
1. Use the tools to make a material contribution to the project, not merely discuss one.
2. Change or create at least one project file other than HANDOFF.md.
3. Call write_handoff with a concise message to the next participant. The harness will preserve it as {required_handoff}.

Earlier numbered handoffs are immutable historical records. You may read them but cannot change them. You may only work through the supplied workspace tools. The execution harness and experiment configuration are outside your authority."""


def run_turn(
    model: str,
    identity: str,
    generation_seed: int,
    supports_thinking: bool,
    previous_handoff: str | None,
    required_handoff: str,
    root: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    before = workspace_snapshot(root)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": system_prompt(
                str(config["command"]), identity, previous_handoff, required_handoff
            ),
        },
        {
            "role": "user",
            "content": "Begin by inspecting the inherited workspace. Decide what to do, make the changes, and leave your handoff.",
        },
    ]

    events: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    final_text = ""
    reminded = False
    error: str | None = None
    started = time.monotonic()

    try:
        for round_number in range(1, int(config["max_tool_rounds"]) + 1):
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "tools": TOOLS,
                "stream": False,
                "keep_alive": str(config["keep_alive"]),
                "options": {
                    "num_ctx": int(config["num_ctx"]),
                    "temperature": float(config["temperature"]),
                    "top_p": float(config["top_p"]),
                    "seed": generation_seed,
                },
            }
            if supports_thinking:
                payload["think"] = True

            response = api_json(
                str(config["ollama_url"]),
                "/api/chat",
                payload,
                int(config["request_timeout_seconds"]),
            )

            metrics.append({
                "round": round_number,
                "prompt_eval_count": response.get("prompt_eval_count"),
                "eval_count": response.get("eval_count"),
                "total_duration_ns": response.get("total_duration"),
            })

            message = response.get("message", {})
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.get("content", ""),
            }
            if message.get("tool_calls"):
                assistant_message["tool_calls"] = message["tool_calls"]
            messages.append(assistant_message)

            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                for call in tool_calls:
                    tool_name = call.get("function", {}).get("name", "unknown")
                    try:
                        result, event = execute_tool(root, call, config, required_handoff)
                    except Exception as exc:
                        result = f"Tool error: {exc}"
                        event = {"tool": tool_name, "ok": False, "error": str(exc)}
                    events.append(event)
                    messages.append({
                        "role": "tool",
                        "tool_name": tool_name,
                        "content": result,
                    })
                continue

            final_text = str(message.get("content", ""))
            artifact_changed, handoff_changed, _ = contribution_status(
                before, workspace_snapshot(root), required_handoff
            )
            if artifact_changed and handoff_changed:
                break

            if not reminded:
                missing = []
                if not artifact_changed:
                    missing.append("a material change outside HANDOFF.md")
                if not handoff_changed:
                    missing.append("a write_handoff call")
                messages.append({
                    "role": "user",
                    "content": "Your turn is not complete. Use the tools now to provide " + " and ".join(missing) + ".",
                })
                reminded = True
                continue

            error = "Model ended without satisfying the contribution requirements"
            break
        else:
            error = "Maximum tool rounds reached"
    except Exception as exc:
        error = str(exc)
    finally:
        try:
            api_json(
                str(config["ollama_url"]),
                "/api/generate",
                {"model": model, "keep_alive": 0},
                60,
            )
        except Exception:
            pass

    after = workspace_snapshot(root)
    artifact_changed, handoff_changed, changed = contribution_status(
        before, after, required_handoff
    )
    # If the work is verifiable on disk, "max rounds" is a false negative
    if artifact_changed and handoff_changed and error == "Maximum tool rounds reached":
        error = None
    success = artifact_changed and handoff_changed and error is None

    return {
        "success": success,
        "error": error,
        "duration_seconds": round(time.monotonic() - started, 3),
        "changed_files": changed,
        "artifact_changed": artifact_changed,
        "handoff_changed": handoff_changed,
        "previous_handoff": previous_handoff,
        "handoff_path": required_handoff,
        "tool_events": events,
        "metrics": metrics,
        "final_response": final_text,
    }


def git_commit(repo: Path, paths: list[str], message: str, push: bool) -> dict[str, Any]:
    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            capture_output=True,
            check=check,
        )

    if git("rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        return {"status": "skipped", "reason": "not a Git repository"}
    if git("diff", "--cached", "--quiet", check=False).returncode != 0:
        return {"status": "skipped", "reason": "pre-existing staged changes"}

    git("add", "--", *paths)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return {"status": "skipped", "reason": "nothing to commit"}

    commit = git(
        "-c", "user.name=Agent Farm",
        "-c", "user.email=agent-farm@local",
        "commit", "-m", message,
    )
    commit_hash = git("rev-parse", "HEAD").stdout.strip()
    result: dict[str, Any] = {"status": "committed", "commit": commit_hash, "output": commit.stdout.strip()}
    if push:
        pushed = git("push", "origin", "HEAD", check=False)
        result["push"] = {
            "ok": pushed.returncode == 0,
            "output": pushed.stdout.strip() or pushed.stderr.strip(),
        }
    return result


def detect_start_index(logs: Path, workspace: Path) -> int:
    """Find the next start index based on existing log files and handoffs."""
    highest = 0
    # Check logs: pilot-NNN.json
    if logs.is_dir():
        for path in logs.glob("pilot-*.json"):
            stem = path.stem  # e.g. "pilot-001"
            if not stem.startswith("pilot-"):
                continue
            suffix = stem[len("pilot-"):]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    # Check handoffs: NNNN.md
    handoff_dir = workspace / "handoffs"
    if handoff_dir.is_dir():
        for path in handoff_dir.glob("*.md"):
            if path.stem.isdigit():
                highest = max(highest, int(path.stem))
    return highest + 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="pilot.json", help="Path to pilot JSON configuration")
    parser.add_argument("--turns", type=int, help="Override the configured number of turns")
    parser.add_argument("--start-index", type=int,
                        help="First turn index to log (default: auto-detect from existing logs)")
    parser.add_argument("--plan", action="store_true", help="Print the sampled schedule without calling Ollama")
    parser.add_argument("--no-commit", action="store_true", help="Do not create Git commits")
    parser.add_argument("--push", action="store_true", help="Push each successful local commit to origin")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    repo = config_path.parent
    turns = args.turns if args.turns is not None else int(config["turns"])
    if turns < 1:
        raise ValueError("turns must be at least 1")

    models = list(config["models"])
    if not models:
        raise ValueError("models cannot be empty")

    experiment_seed = config.get("random_seed")
    if experiment_seed is None:
        experiment_seed = int.from_bytes(os.urandom(8), "big")
    rng = random.Random(int(experiment_seed))
    selected_models = schedule(models, turns, rng)
    selected_personas = unique_personas(turns, rng)
    generation_seeds = [rng.randrange(1, 2_147_483_647) for _ in range(turns)]

    workspace = repo / str(config["workspace"])
    logs = repo / str(config["logs"])

    # Determine log start index
    if args.start_index is not None:
        if args.start_index < 1:
            raise ValueError("--start-index must be >= 1")
        start_index = args.start_index
    else:
        start_index = detect_start_index(logs, workspace)

    if start_index > 1:
        print(f"Continuing from turn {start_index} (existing logs detected)")

    print(f"Pilot seed: {experiment_seed}")
    for offset, (model, identity) in enumerate(zip(selected_models, selected_personas)):
        print(f"Turn {start_index + offset}: {model} — {identity}")
    if args.plan:
        return 0

    workspace.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    # Load existing summary if present
    summary_path = logs / "pilot-summary.json"
    if summary_path.exists() and start_index > 1:
        summary = load_json(summary_path)
        if "runs" not in summary:
            summary["runs"] = []
        existing_turns = len(summary["runs"])
        print(f"Loaded existing summary with {existing_turns} prior run(s)")
    else:
        summary: dict[str, Any] = {
            "started_at": timestamp(),
            "experiment_seed": experiment_seed,
            "command": config["command"],
            "runs": [],
        }

    for offset, (model, identity, generation_seed) in enumerate(
        zip(selected_models, selected_personas, generation_seeds)
    ):
        index = start_index + offset
        print(f"\nStarting turn {index}: {model}", flush=True)
        record: dict[str, Any] = {
            "turn": index,
            "started_at": timestamp(),
            "model": model,
            "persona": identity,
            "generation_seed": generation_seed,
        }
        try:
            previous_handoff, required_handoff = next_handoff(workspace)
            record["previous_handoff"] = previous_handoff
            record["handoff_path"] = required_handoff
            model_details = api_json(
                str(config["ollama_url"]),
                "/api/show",
                {"model": model, "verbose": False},
                30,
            )
            supports_thinking = "thinking" in model_details.get("capabilities", [])
            record["capabilities"] = model_details.get("capabilities", [])
            record.update(
                run_turn(
                    model,
                    identity,
                    generation_seed,
                    supports_thinking,
                    previous_handoff,
                    required_handoff,
                    workspace,
                    config,
                )
            )
        except Exception as exc:
            record.update({
                "success": False,
                "error": str(exc),
                "duration_seconds": 0,
                "changed_files": [],
                "artifact_changed": False,
                "handoff_changed": False,
                "previous_handoff": record.get("previous_handoff"),
                "handoff_path": record.get("handoff_path"),
                "tool_events": [],
                "metrics": [],
                "final_response": "",
            })
        record["finished_at"] = timestamp()

        log_path = logs / f"pilot-{index:03d}.json"
        log_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        summary["experiment_seed"] = experiment_seed
        summary["command"] = config["command"]
        summary["finished_at"] = timestamp()
        summary["runs"].append({
            "turn": index,
            "model": model,
            "persona": identity,
            "success": record["success"],
            "error": record["error"],
            "changed_files": record["changed_files"],
        })
        summary["successful_turns"] = sum(1 for run in summary["runs"] if run["success"])
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        if not args.no_commit:
            try:
                record["git"] = git_commit(
                    repo,
                    [str(workspace.relative_to(repo)), str(logs.relative_to(repo))],
                    f"pilot turn {index}: {model}",
                    args.push,
                )
            except Exception as exc:
                record["git"] = {"status": "failed", "reason": str(exc)}
        status = "SUCCEEDED" if record["success"] else "FAILED"
        print(f"Turn {index} {status}: {', '.join(record['changed_files']) or 'no workspace changes'}")

    total_runs = len(summary["runs"])
    successful = summary["successful_turns"]
    print(f"\nPilot complete: {successful}/{total_runs} successful turns total")
    print(f"Summary: {summary_path}")
    return 0 if successful == total_runs else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
