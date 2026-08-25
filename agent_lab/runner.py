from __future__ import annotations

import difflib
import fcntl
import json
import math
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

from .budget import (
    MODEL_UNLOAD_TIMEOUT_SECONDS,
    OPENCODE_KILL_TIMEOUT_SECONDS,
    OPENCODE_TERMINATE_TIMEOUT_SECONDS,
    runner_budget,
)
from .config import LabConfig
from .durability import fsync_tree
from .lineage import ensure_lineage
from .state import Reservation, SchedulerState, atomic_write_json
from .validation import content_manifest, material_change, validate_site


_FINAL_STATUSES = {
    "accepted",
    "agent_failed",
    "infrastructure_error",
    "interrupted",
    "no_material_change",
    "rejected",
    "timed_out",
}


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
                returncode = process.wait(timeout=OPENCODE_TERMINATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait(timeout=OPENCODE_KILL_TIMEOUT_SECONDS)
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
        with urlopen(request, timeout=MODEL_UNLOAD_TIMEOUT_SECONDS):
            pass
    except Exception:
        pass


def _pending_status(
    pending: list[Path],
    scheduler: SchedulerState,
) -> dict[str, object]:
    inflight = scheduler.inflight()
    reconciled = False
    if inflight is not None and any(path.stem == inflight.run_id for path in pending):
        scheduler.complete(inflight.run_id)
        reconciled = True
    return {
        "schema_version": 1,
        "status": "publication_pending",
        "run_id": pending[0].stem,
        "pending_publications": [path.name for path in pending],
        "scheduler_reconciled": reconciled,
    }


def _recover_interrupted(
    config: LabConfig,
    spool: Path,
    scheduler: SchedulerState,
    reservation: Reservation,
) -> dict[str, object]:
    now = timestamp()
    run_dir = config.state_dir / "raw" / reservation.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    record_path = run_dir / "record.json"
    if record_path.is_file():
        try:
            existing = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            existing = None
        if isinstance(existing, dict) and _coherent_final_record(
            existing,
            config,
            reservation,
            run_dir,
        ):
            atomic_write_json(spool / f"{reservation.run_id}.json", existing)
            scheduler.complete(reservation.run_id)
            return existing
        invalid = run_dir / "record.invalid.json"
        sequence = 1
        while invalid.exists():
            invalid = run_dir / f"record.invalid-{sequence}.json"
            sequence += 1
        record_path.replace(invalid)

    record: dict[str, object] = {
        "schema_version": 1,
        "run_id": reservation.run_id,
        "started_at": now,
        "finished_at": now,
        "model": reservation.model,
        "pool_version": reservation.pool_version,
        "epoch": reservation.epoch,
        "epoch_seed": reservation.epoch_seed,
        "epoch_position": reservation.epoch_position,
        "opencode_version": config.opencode.version,
        "duration_seconds": None,
        "returncode": None,
        "timed_out": False,
        "status": "interrupted",
        "reason": "the previous runner process ended before the turn was finalized",
        "accepted": False,
        "changed_files": [],
        "before_manifest": {},
        "after_manifest": {},
        "validation": None,
        "raw_archive": f"raw/{reservation.run_id}",
    }
    atomic_write_json(record_path, record)
    atomic_write_json(spool / f"{reservation.run_id}.json", record)
    scheduler.complete(reservation.run_id)
    return record


def _exact_int(value: object) -> bool:
    return type(value) is int


def _valid_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _valid_manifest(value: object, *, allow_empty: bool = False) -> bool:
    if not isinstance(value, dict) or (not value and not allow_empty):
        return False
    hexadecimal = frozenset("0123456789abcdef")
    for relative, metadata in value.items():
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            return False
        if any(part in {"", ".", ".."} for part in Path(relative).parts):
            return False
        if not isinstance(metadata, dict) or set(metadata) != {"sha256", "bytes"}:
            return False
        digest = metadata["sha256"]
        byte_count = metadata["bytes"]
        if not (
            isinstance(digest, str)
            and len(digest) == 64
            and all(character in hexadecimal for character in digest)
        ):
            return False
        if not _exact_int(byte_count) or byte_count < 0:
            return False
    return True


def _coherent_final_record(
    record: dict[str, object],
    config: LabConfig,
    reservation: Reservation,
    run_dir: Path,
) -> bool:
    required = {
        "schema_version",
        "run_id",
        "started_at",
        "finished_at",
        "model",
        "pool_version",
        "epoch",
        "epoch_seed",
        "epoch_position",
        "opencode_version",
        "duration_seconds",
        "returncode",
        "timed_out",
        "status",
        "reason",
        "accepted",
        "changed_files",
        "before_manifest",
        "after_manifest",
        "validation",
        "raw_archive",
    }
    if not required.issubset(record):
        return False
    if not (
        _exact_int(record["schema_version"])
        and record["schema_version"] == 1
        and record["run_id"] == reservation.run_id
        and record["model"] == reservation.model
        and _exact_int(record["pool_version"])
        and record["pool_version"] == reservation.pool_version
        and _exact_int(record["epoch"])
        and record["epoch"] == reservation.epoch
        and _exact_int(record["epoch_seed"])
        and record["epoch_seed"] == reservation.epoch_seed
        and _exact_int(record["epoch_position"])
        and record["epoch_position"] == reservation.epoch_position
        and record["opencode_version"] == config.opencode.version
        and record["raw_archive"] == f"raw/{reservation.run_id}"
    ):
        return False

    started = _valid_timestamp(record["started_at"])
    finished = _valid_timestamp(record["finished_at"])
    if started is None or finished is None or finished < started:
        return False
    duration = record["duration_seconds"]
    if duration is not None and (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration < 0
    ):
        return False
    returncode = record["returncode"]
    if returncode is not None and not _exact_int(returncode):
        return False
    if not isinstance(record["timed_out"], bool):
        return False

    status = record["status"]
    accepted = record["accepted"]
    reason = record["reason"]
    validation = record["validation"]
    if status not in _FINAL_STATUSES or not isinstance(accepted, bool):
        return False
    if accepted != (status == "accepted"):
        return False
    if status != "interrupted" and duration is None:
        return False
    if accepted:
        if not (
            returncode == 0
            and record["timed_out"] is False
            and reason is None
            and isinstance(validation, dict)
            and validation.get("ok") is True
        ):
            return False
    elif not isinstance(reason, str) or not reason:
        return False
    if validation is not None and (
        not isinstance(validation, dict) or not isinstance(validation.get("ok"), bool)
    ):
        return False

    changed_files = record["changed_files"]
    if not isinstance(changed_files, list) or any(
        not isinstance(path, str) for path in changed_files
    ):
        return False
    if changed_files != sorted(set(changed_files)):
        return False
    allow_empty_manifests = status == "interrupted"
    if not _valid_manifest(
        record["before_manifest"], allow_empty=allow_empty_manifests
    ) or not _valid_manifest(
        record["after_manifest"], allow_empty=allow_empty_manifests
    ):
        return False
    manifest_paths = set(record["before_manifest"]) | set(record["after_manifest"])
    if any(path not in manifest_paths for path in changed_files):
        return False
    changed = bool(changed_files)
    if accepted:
        baseline = run_dir / "baseline"
        candidate = run_dir / "candidate"
        if not baseline.is_dir() or baseline.is_symlink():
            return False
        if not candidate.is_dir() or candidate.is_symlink():
            return False
        try:
            before_manifest = content_manifest(baseline)
            after_manifest = content_manifest(candidate)
            actual_changed, actual_changed_files = material_change(baseline, candidate)
        except (OSError, UnicodeError, ValueError):
            return False
        if record["before_manifest"] != before_manifest:
            return False
        if record["after_manifest"] != after_manifest:
            return False
        if changed_files != actual_changed_files or not actual_changed:
            return False
    if status == "no_material_change" and changed:
        return False
    if status == "rejected" and (
        not changed or not isinstance(validation, dict) or validation.get("ok") is not False
    ):
        return False
    if status == "timed_out" and record["timed_out"] is not True:
        return False
    if status == "agent_failed" and (returncode is None or returncode == 0):
        return False
    if status == "interrupted" and duration is not None:
        return False
    if status == "interrupted" and not (
        returncode is None
        and record["timed_out"] is False
        and not changed_files
        and record["before_manifest"] == {}
        and record["after_manifest"] == {}
        and validation is None
    ):
        return False
    return True


def run_once(config: LabConfig) -> dict[str, object]:
    runner_budget(config)
    config.state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    config.state_dir.chmod(0o700)
    spool = config.state_dir / "spool"
    spool.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(config.state_dir / "run.lock"):
        scheduler = SchedulerState(
            config.state_dir / "scheduler.json",
            config.model_pool_version,
            config.models,
        )
        pending = sorted(spool.glob("*.json"))
        if pending:
            return _pending_status(pending, scheduler)
        existing = scheduler.inflight()
        if existing:
            return _recover_interrupted(config, spool, scheduler, existing)
        if not config.opencode.binary.is_file():
            raise RuntimeError(f"OpenCode runtime is missing: {config.opencode.binary}")
        if not config.validation.require_browser:
            raise RuntimeError("browser validation is required for production turns")

        lineage = ensure_lineage(config)
        run_id = new_run_id()
        reservation = scheduler.reserve(run_id)
        run_dir = config.state_dir / "raw" / run_id
        baseline = run_dir / "baseline"
        candidate = run_dir / "candidate"
        screenshots = run_dir / "screenshots"
        run_dir.mkdir(parents=True)
        _safe_copy(lineage, baseline)

        started_at = timestamp()
        returncode: int | None = None
        timed_out = False
        duration = 0.0
        infrastructure_error: str | None = None
        with tempfile.TemporaryDirectory(prefix="agent-farm-turn-") as temporary:
            stage = Path(temporary) / "site"
            _safe_copy(baseline, stage)
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
                browser=True,
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
            "raw_archive": f"raw/{run_id}",
        }
        if accepted:
            fsync_tree(candidate)
        atomic_write_json(run_dir / "record.json", record)
        atomic_write_json(spool / f"{run_id}.json", record)
        scheduler.complete(run_id)
        return record
