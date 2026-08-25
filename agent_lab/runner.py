from __future__ import annotations

import difflib
import fcntl
import json
import os
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.request import Request, urlopen

from .config import LabConfig
from .state import SchedulerState, atomic_write_json
from .validation import content_manifest, material_change, validate_site


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another lab process holds {path.name}") from exc
        yield


def _safe_copy(source: Path, destination: Path) -> None:
    if destination.exists():
        raise RuntimeError(f"refusing to overwrite existing turn directory: {destination}")
    shutil.copytree(source, destination, symlinks=True)


def _text_patch(before: Path, after: Path, destination: Path) -> None:
    before_manifest = content_manifest(before)
    after_manifest = content_manifest(after)
    lines: list[str] = []
    for relative in sorted(set(before_manifest) | set(after_manifest)):
        old = before / relative
        new = after / relative
        if before_manifest.get(relative, {}).get("sha256") == after_manifest.get(relative, {}).get(
            "sha256"
        ):
            continue
        try:
            old_lines = old.read_text(encoding="utf-8").splitlines(keepends=True) if old.exists() else []
            new_lines = new.read_text(encoding="utf-8").splitlines(keepends=True) if new.exists() else []
        except UnicodeDecodeError:
            lines.append(f"Binary files differ: {relative}\n")
            continue
        lines.extend(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
    destination.write_text("".join(lines), encoding="utf-8")


def _sanitized_environment(config: LabConfig, home: Path) -> dict[str, str]:
    runtime_node = config.repo / ".runtime" / "node" / "bin"
    runtime_opencode = config.repo / ".runtime" / "opencode" / "node_modules" / ".bin"
    tmp = home / "tmp"
    data = home / ".local" / "share"
    cache = home / ".cache"
    config_home = home / ".config"
    for directory in (tmp, data, cache, config_home):
        directory.mkdir(parents=True, exist_ok=True)
    trusted = (config.repo / "lab" / "opencode.json").read_text(encoding="utf-8")
    return {
        "PATH": f"{runtime_node}:{runtime_opencode}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "XDG_DATA_HOME": str(data),
        "XDG_CACHE_HOME": str(cache),
        "XDG_CONFIG_HOME": str(config_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OLLAMA_HOST": "http://127.0.0.1:11434",
        "NO_PROXY": "127.0.0.1,localhost",
        "OPENCODE_CONFIG_CONTENT": trusted,
        "OPENCODE_DISABLE_AUTOUPDATE": "true",
        "OPENCODE_AUTO_SHARE": "false",
    }


def _run_opencode(
    config: LabConfig,
    model: str,
    stage: Path,
    run_dir: Path,
) -> tuple[int | None, bool, float]:
    stdout_path = run_dir / "opencode-events.jsonl"
    stderr_path = run_dir / "opencode-stderr.log"
    home = run_dir / "home"
    command = [
        str(config.opencode.binary),
        "--pure",
        "run",
        "--dir",
        str(stage),
        "--model",
        model,
        "--agent",
        "build",
        "--format",
        "json",
        "--auto",
        config.prompt,
    ]
    started = time.monotonic()
    timed_out = False
    returncode: int | None = None
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=stage,
            env=_sanitized_environment(config, home),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=config.turn_timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait(timeout=10)
    return returncode, timed_out, round(time.monotonic() - started, 3)


def _unload_model(model: str) -> None:
    ollama_model = model.removeprefix("ollama/")
    request = Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": ollama_model, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60):
            pass
    except Exception:
        pass


def _tail(path: Path, limit: int = 8192) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    return data[-limit:].decode("utf-8", errors="replace")


def run_once(config: LabConfig, *, browser: bool = True) -> dict[str, object]:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    spool = config.state_dir / "spool"
    spool.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(config.state_dir / "run.lock"):
        pending = sorted(spool.glob("*.json"))
        if pending:
            raise RuntimeError(f"publication is pending: {pending[0].name}")
        if not config.site_dir.is_dir():
            raise RuntimeError(f"site directory is missing: {config.site_dir}")
        if not config.opencode.binary.is_file():
            raise RuntimeError(f"OpenCode runtime is missing: {config.opencode.binary}")

        scheduler = SchedulerState(
            config.state_dir / "scheduler.json",
            config.model_pool_version,
            config.models,
        )
        existing = scheduler.inflight()
        if existing:
            raise RuntimeError(
                f"unfinished scheduler reservation requires recovery: {existing.run_id}"
            )
        run_id = new_run_id()
        reservation = scheduler.reserve(run_id)
        run_dir = config.state_dir / "raw" / run_id
        baseline = run_dir / "baseline"
        candidate = run_dir / "candidate"
        screenshots = run_dir / "screenshots"
        run_dir.mkdir(parents=True)
        _safe_copy(config.site_dir, baseline)

        started_at = timestamp()
        returncode: int | None = None
        timed_out = False
        duration = 0.0
        infrastructure_error: str | None = None
        with tempfile.TemporaryDirectory(prefix="agent-farm-turn-") as temporary:
            stage = Path(temporary) / "site"
            _safe_copy(config.site_dir, stage)
            try:
                returncode, timed_out, duration = _run_opencode(
                    config, reservation.model, stage, run_dir
                )
            except Exception as exc:
                infrastructure_error = str(exc)
            finally:
                _unload_model(reservation.model)
            _safe_copy(stage, candidate)

        changed = False
        changed_files: list[str] = []
        validation = None
        try:
            changed, changed_files = material_change(baseline, candidate)
            validation = validate_site(
                candidate,
                config.validation,
                screenshots,
                browser=browser,
            )
        except Exception as exc:
            infrastructure_error = infrastructure_error or f"validation failed: {exc}"

        accepted = bool(
            infrastructure_error is None
            and returncode == 0
            and not timed_out
            and changed
            and validation is not None
            and validation.ok
        )
        _text_patch(baseline, candidate, run_dir / "attempt.patch")
        with tarfile.open(run_dir / "candidate.tar.gz", "w:gz") as archive:
            archive.add(candidate, arcname="site", recursive=True)

        if infrastructure_error:
            status = "infrastructure_error"
            reason = infrastructure_error
        elif timed_out:
            status = "timed_out"
            reason = "OpenCode exceeded the turn timeout"
        elif returncode != 0:
            status = "agent_failed"
            reason = f"OpenCode exited with status {returncode}"
        elif not changed:
            status = "no_material_change"
            reason = "candidate has no non-whitespace website change"
        elif validation is not None and not validation.ok:
            status = "rejected"
            reason = "candidate failed deterministic validation"
        else:
            status = "accepted"
            reason = None

        record: dict[str, object] = {
            "schema_version": 1,
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": timestamp(),
            "model": reservation.model,
            "pool_version": reservation.pool_version,
            "epoch": reservation.epoch,
            "epoch_seed": reservation.epoch_seed,
            "epoch_position": reservation.epoch_position,
            "opencode_version": config.opencode.version,
            "duration_seconds": duration,
            "returncode": returncode,
            "timed_out": timed_out,
            "status": status,
            "reason": reason,
            "accepted": accepted,
            "changed_files": changed_files,
            "before_manifest": content_manifest(baseline),
            "after_manifest": content_manifest(candidate),
            "validation": validation.to_dict() if validation else None,
            "final_output_excerpt": _tail(run_dir / "opencode-events.jsonl"),
            "raw_archive": f"raw/{run_id}",
        }
        atomic_write_json(run_dir / "record.json", record)
        atomic_write_json(spool / f"{run_id}.json", record)
        scheduler.complete(run_id)
        return record
