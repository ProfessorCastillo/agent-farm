from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from .budget import runner_budget
from .config import LabConfig, load_config
from .lineage import ensure_lineage
from .publisher import publish_next
from .runner import run_once
from .validation import validate_site


DEFAULT_CONFIG = Path("lab/config.toml")
def _config(args: argparse.Namespace) -> LabConfig:
    return load_config(Path(args.config))


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def preflight(config: LabConfig, *, browser: bool = True) -> dict[str, object]:
    config.state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    config.state_dir.chmod(0o700)
    checks: dict[str, dict[str, object]] = {}

    def check(name: str, function) -> None:
        try:
            detail = function()
            checks[name] = {"ok": True, "detail": detail}
        except Exception as exc:
            checks[name] = {"ok": False, "detail": str(exc)}

    def site_check() -> dict[str, object]:
        lineage = ensure_lineage(config)
        report = validate_site(
            lineage,
            config.validation,
            config.state_dir / "preflight-screenshots",
            browser=browser,
        )
        if not report.ok:
            raise RuntimeError(json.dumps(report.to_dict(), sort_keys=True))
        return report.to_dict()

    def opencode_check() -> str:
        actual = subprocess.run(
            [str(config.opencode.binary), "--version"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        if actual != config.opencode.version:
            raise RuntimeError(f"expected {config.opencode.version}, found {actual}")
        return actual

    def opencode_environment() -> dict[str, str]:
        home = config.state_dir / "preflight-opencode-home"
        home.mkdir(parents=True, exist_ok=True)
        return {
            "PATH": (
                f"{config.repo / '.runtime/node/bin'}:"
                f"{config.repo / '.runtime/opencode/node_modules/.bin'}:/usr/bin:/bin"
            ),
            "HOME": str(home),
            "XDG_DATA_HOME": str(home / "data"),
            "XDG_CACHE_HOME": str(home / "cache"),
            "XDG_CONFIG_HOME": str(home / "config"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "OPENCODE_CONFIG_CONTENT": (
                config.repo / "lab" / "opencode.json"
            ).read_text(encoding="utf-8"),
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_AUTO_SHARE": "false",
            "OLLAMA_HOST": "http://127.0.0.1:11434",
            "NO_PROXY": "127.0.0.1,localhost",
        }

    def opencode_policy_check() -> str:
        resolved = subprocess.run(
            [str(config.opencode.binary), "--pure", "debug", "config"],
            env=opencode_environment(),
            text=True,
            capture_output=True,
            check=True,
        )
        policy = json.loads(resolved.stdout).get("permission")
        if not isinstance(policy, dict):
            raise RuntimeError("OpenCode permission policy is missing")
        expected_denials = (
            "bash",
            "external_directory",
            "question",
            "skill",
            "task",
            "webfetch",
            "websearch",
        )
        unexpected = [name for name in expected_denials if policy.get(name) != "deny"]
        if unexpected:
            raise RuntimeError(
                "OpenCode permission policy does not deny: " + ", ".join(unexpected)
            )
        return "shell, external directories, network tools, and delegation denied"

    def model_check() -> list[str]:
        output = subprocess.run(
            [str(config.opencode.binary), "--pure", "models", "ollama"],
            env=opencode_environment(),
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        missing = sorted(set(config.models) - set(output))
        if missing:
            raise RuntimeError(f"OpenCode is missing configured models: {', '.join(missing)}")
        return output

    check("runner_budget", lambda: runner_budget(config))
    check("site", site_check)
    check(
        "opencode",
        opencode_check,
    )
    check("opencode_policy", opencode_policy_check)
    check("models", model_check)
    check(
        "ollama",
        lambda: json.load(urlopen("http://127.0.0.1:11434/api/tags", timeout=5))["models"][
            0
        ]["name"],
    )
    check(
        "deploy_key",
        lambda: (
            "present with mode 0600"
            if config.publish.deploy_key.is_file()
            and not config.publish.deploy_key.stat().st_mode & 0o077
            else (_ for _ in ()).throw(RuntimeError("missing or permissions are not 0600"))
        ),
    )
    return {"ok": all(bool(value["ok"]) for value in checks.values()), "checks": checks}


def status(config: LabConfig) -> dict[str, object]:
    spool = sorted((config.state_dir / "spool").glob("*.json"))
    raw = sorted((config.state_dir / "raw").glob("*"))
    scheduler = config.state_dir / "scheduler.json"
    lineage = config.state_dir / "lineage" / "site"
    lineage_ready = lineage.is_dir() and not lineage.is_symlink()
    return {
        "site": str(lineage if lineage_ready else config.site_dir),
        "seed_site": str(config.site_dir),
        "lineage_site": str(lineage) if lineage_ready else None,
        "model_pool_version": config.model_pool_version,
        "models": list(config.models),
        "scheduler": json.loads(scheduler.read_text(encoding="utf-8"))
        if scheduler.exists()
        else None,
        "pending_publications": [path.name for path in spool],
        "latest_raw_run": raw[-1].name if raw else None,
    }


def prune(config: LabConfig) -> dict[str, object]:
    root = config.state_dir / "raw"
    if not root.exists():
        return {"removed": [], "remaining_bytes": 0}
    pending_ids = {path.stem for path in (config.state_dir / "spool").glob("*.json")}
    entries = [path for path in root.iterdir() if path.is_dir()]

    def size(path: Path) -> int:
        return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())

    details = sorted(
        [(path, size(path), path.stat().st_mtime) for path in entries],
        key=lambda item: item[2],
    )
    total = sum(item[1] for item in details)
    cutoff = time.time() - config.raw_retention_days * 86400
    removed: list[str] = []
    for path, path_size, modified in details:
        if path.name in pending_ids:
            continue
        if modified < cutoff or total > config.raw_retention_bytes:
            shutil.rmtree(path)
            total -= path_size
            removed.append(path.name)
    return {"removed": removed, "remaining_bytes": total}


def _systemctl(action: str) -> None:
    units = ["agent-farm-run.timer", "agent-farm-publish.timer"]
    if os.geteuid() != 0:
        raise RuntimeError(
            f"{action} controls a system unit; rerun this command with sudo"
        )
    command = ["systemctl"]
    if action == "pause":
        command.extend(["disable", "--now", *units])
    else:
        command.extend(["enable", "--now", *units])
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("run-once")
    commands.add_parser("publish")
    commands.add_parser("status")
    commands.add_parser("pause")
    commands.add_parser("resume")
    commands.add_parser("prune")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = _config(args)
        os.environ.setdefault(
            "PLAYWRIGHT_BROWSERS_PATH",
            str(config.repo / ".runtime" / "playwright"),
        )
        if args.command == "preflight":
            result = preflight(config)
            _json(result)
            return 0 if result["ok"] else 1
        if args.command == "run-once":
            result = run_once(config)
            _json(result)
            return 0
        if args.command == "publish":
            _json(publish_next(config))
            return 0
        if args.command == "status":
            _json(status(config))
            return 0
        if args.command == "prune":
            _json(prune(config))
            return 0
        if args.command in {"pause", "resume"}:
            _systemctl(args.command)
            _json({"status": args.command, "at": datetime.now(timezone.utc).isoformat()})
            return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"agent-farm: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
