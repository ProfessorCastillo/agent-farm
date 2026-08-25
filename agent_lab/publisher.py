from __future__ import annotations

import hashlib
import json
import math
import re
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .config import LabConfig
from .lineage import update_lineage
from .runner import exclusive_lock, timestamp
from .state import atomic_write_json
from .validation import content_manifest, validate_site


_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}\Z")
_SAFE_COMMIT = re.compile(r"[0-9a-f]{40,64}\Z")
_SAFE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}\Z")
_PUBLIC_STATUSES = {
    "accepted",
    "agent_failed",
    "infrastructure_error",
    "interrupted",
    "no_material_change",
    "rejected",
    "timed_out",
}


def _git_env(key: Path, known_hosts: Path) -> dict[str, str]:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": (
            f"ssh -i {shlex.quote(str(key))} -o IdentitiesOnly=yes "
            f"-o {shlex.quote(f'UserKnownHostsFile={known_hosts}')} "
            "-o StrictHostKeyChecking=accept-new -o BatchMode=yes"
        ),
    }
    return env


def _git(
    cwd: Path,
    env: dict[str, str],
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def _git_bytes(
    cwd: Path,
    env: dict[str, str],
    *args: str,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=True,
    )


def _committed_site_manifest(
    cwd: Path,
    env: dict[str, str],
    commit: str,
    site_name: str,
) -> dict[str, dict[str, object]]:
    result = _git(
        cwd,
        env,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        commit,
        "--",
        site_name,
    )
    prefix = f"{site_name}/"
    manifest: dict[str, dict[str, object]] = {}
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        try:
            metadata, path = entry.split("\t", 1)
            mode, object_type, object_id = metadata.split(" ", 2)
        except ValueError as exc:
            raise RuntimeError("committed site contains an unreadable Git tree entry") from exc
        if object_type != "blob" or mode != "100644" or not path.startswith(prefix):
            raise RuntimeError("committed site contains an unsupported Git tree entry")
        relative = path[len(prefix) :]
        if not relative or relative in manifest:
            raise RuntimeError("committed site contains an invalid Git tree path")
        content = _git_bytes(cwd, env, "cat-file", "blob", object_id).stdout
        manifest[relative] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }
    return manifest


def _ahead_behind(cwd: Path, env: dict[str, str], remote_ref: str, local_ref: str) -> tuple[int, int]:
    result = _git(
        cwd,
        env,
        "rev-list",
        "--left-right",
        "--count",
        f"{remote_ref}...{local_ref}",
    ).stdout.split()
    return int(result[0]), int(result[1])


def _dirty_paths(cwd: Path, env: dict[str, str]) -> set[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(
            line
            for line in _git(cwd, env, *args).stdout.splitlines()
            if line
        )
    return paths


def _inside_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _recover_automation_changes(
    cwd: Path,
    env: dict[str, str],
    *,
    allowed_roots: tuple[str, ...],
) -> None:
    dirty = _dirty_paths(cwd, env)
    if not dirty:
        return
    unexpected = sorted(
        path
        for path in dirty
        if not any(_inside_prefix(path, root) for root in allowed_roots)
    )
    if unexpected:
        raise RuntimeError(
            "automation worktree contains unexpected uncommitted changes: "
            + ", ".join(unexpected)
        )

    # These are dedicated automation worktrees. A prior publisher may have
    # stopped between replacement/write, add, and commit. Restore only the
    # publisher-owned paths, then reconstruct them from the durable spool.
    for root in allowed_roots:
        _git(
            cwd,
            env,
            "restore",
            "--staged",
            "--worktree",
            "--",
            root,
            check=False,
        )
    _git(cwd, env, "clean", "-fd", "--", *allowed_roots)
    remaining = _dirty_paths(cwd, env)
    if remaining:
        raise RuntimeError(
            "could not recover publisher-owned uncommitted changes: "
            + ", ".join(sorted(remaining))
        )


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _git_directory(path: Path, env: dict[str, str]) -> Path | None:
    result = _git(path, env, "rev-parse", "--git-dir", check=False)
    if result.returncode:
        return None
    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = path / git_dir
    return git_dir.resolve()


def _has_git_locks(path: Path, env: dict[str, str]) -> bool:
    git_dir = _git_directory(path, env)
    if git_dir is None or not git_dir.is_dir():
        return True
    try:
        lock_files = any(
            candidate.is_file() or candidate.is_symlink()
            for candidate in git_dir.rglob("*.lock")
        )
        worktree_locks = (git_dir / "locked").is_file() or any(
            candidate.is_file()
            for candidate in (git_dir / "worktrees").glob("*/locked")
        )
        return lock_files or worktree_locks
    except OSError:
        return True


def _main_checkout_is_valid(config: LabConfig, checkout: Path, env: dict[str, str]) -> bool:
    if checkout.is_symlink() or not checkout.is_dir() or not (checkout / ".git").is_dir():
        return False
    top = _git(checkout, env, "rev-parse", "--show-toplevel", check=False)
    if top.returncode or Path(top.stdout.strip()).resolve() != checkout.resolve():
        return False
    origin = _git(checkout, env, "remote", "get-url", "origin", check=False)
    if origin.returncode or origin.stdout.strip() != config.publish.remote:
        return False
    return not _has_git_locks(checkout, env)


def _clone_checkout(config: LabConfig, checkout: Path, env: dict[str, str]) -> None:
    checkout.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", config.publish.remote, str(checkout)],
        cwd=config.state_dir,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def _rebuild_checkout(config: LabConfig, checkout: Path, env: dict[str, str]) -> None:
    if _path_exists(checkout):
        _quarantine(checkout)
    _clone_checkout(config, checkout, env)
    if not _main_checkout_is_valid(config, checkout, env):
        raise RuntimeError("fresh publisher checkout failed repository identity checks")


def _ensure_checkout(config: LabConfig, env: dict[str, str]) -> Path:
    checkout = config.state_dir / "repository"
    if not _main_checkout_is_valid(config, checkout, env):
        _rebuild_checkout(config, checkout, env)

    site_name = config.site_dir.name
    try:
        _git(checkout, env, "switch", config.publish.main_branch)
        _recover_automation_changes(
            checkout,
            env,
            allowed_roots=(site_name, f".{site_name}.incoming", f".{site_name}.previous"),
        )
    except (RuntimeError, subprocess.CalledProcessError):
        _rebuild_checkout(config, checkout, env)
        _git(checkout, env, "switch", config.publish.main_branch)

    _git(checkout, env, "fetch", "--prune", "origin")
    behind, ahead = _ahead_behind(
        checkout,
        env,
        f"origin/{config.publish.main_branch}",
        config.publish.main_branch,
    )
    if ahead:
        # Local commits are reconstructible from the durable spool. Never
        # publish a clean commit merely because it was left in this checkout.
        _rebuild_checkout(config, checkout, env)
        _git(checkout, env, "switch", config.publish.main_branch)
        _git(checkout, env, "fetch", "--prune", "origin")
        behind, ahead = _ahead_behind(
            checkout,
            env,
            f"origin/{config.publish.main_branch}",
            config.publish.main_branch,
        )
    if ahead:
        raise RuntimeError("fresh publisher checkout is unexpectedly ahead of origin")
    if behind:
        _git(checkout, env, "merge", "--ff-only", f"origin/{config.publish.main_branch}")
    return checkout


def _clear_worktree(path: Path) -> None:
    for item in path.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def _resolved_git_common_dir(path: Path, env: dict[str, str]) -> Path | None:
    result = _git(path, env, "rev-parse", "--git-common-dir", check=False)
    if result.returncode:
        return None
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = path / common
    return common.resolve()


def _current_branch(path: Path, env: dict[str, str]) -> str | None:
    result = _git(path, env, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _quarantine(path: Path) -> Path:
    candidate = path.with_name(f"{path.name}.quarantine")
    sequence = 1
    while _path_exists(candidate):
        candidate = path.with_name(f"{path.name}.quarantine-{sequence}")
        sequence += 1
    path.rename(candidate)
    return candidate


def _observation_worktree_is_valid(
    observations: Path,
    checkout: Path,
    branch: str,
    env: dict[str, str],
) -> bool:
    if observations.is_symlink() or not observations.is_dir():
        return False
    checkout_common = _resolved_git_common_dir(checkout, env)
    observations_common = (
        _resolved_git_common_dir(observations, env)
        if (observations / ".git").is_file()
        else None
    )
    if observations_common is None or observations_common != checkout_common:
        return False
    if _current_branch(observations, env) != branch:
        return False
    if _has_git_locks(observations, env):
        return False
    return _git(observations, env, "rev-parse", "--verify", "HEAD", check=False).returncode == 0


def _quarantine_observations(
    observations: Path,
    checkout: Path,
    env: dict[str, str],
) -> None:
    if _path_exists(observations):
        _git(checkout, env, "worktree", "unlock", str(observations), check=False)
        _quarantine(observations)
    _git(checkout, env, "worktree", "prune", "--expire", "now")


def _create_observations(
    observations: Path,
    checkout: Path,
    branch: str,
    env: dict[str, str],
    *,
    remote_exists: bool,
) -> None:
    if remote_exists:
        _git(
            checkout,
            env,
            "worktree",
            "add",
            "-B",
            branch,
            str(observations),
            f"origin/{branch}",
        )
        return

    _git(checkout, env, "update-ref", "-d", f"refs/heads/{branch}", check=False)
    _git(checkout, env, "worktree", "add", "--detach", str(observations), "HEAD")
    _git(observations, env, "switch", "--orphan", branch)
    _clear_worktree(observations)
    (observations / "README.md").write_text(
        "# Agent Farm observations\n\n"
        "Compact, append-only records from the autonomous website experiment.\n",
        encoding="utf-8",
    )
    _git(observations, env, "add", "--", "README.md")
    _git(
        observations,
        env,
        "-c",
        "user.name=Agent Farm Observer",
        "-c",
        "user.email=agent-farm@local",
        "commit",
        "-m",
        "initialize observations branch",
    )


def _ensure_observations(
    config: LabConfig,
    checkout: Path,
    env: dict[str, str],
) -> Path:
    observations = config.state_dir / "observations-worktree"
    branch = config.observations_branch
    _git(checkout, env, "worktree", "prune", "--expire", "now")
    remote_exists = (
        _git(
            checkout,
            env,
            "show-ref",
            "--verify",
            f"refs/remotes/origin/{branch}",
            check=False,
        ).returncode
        == 0
    )

    if _path_exists(observations) and not _observation_worktree_is_valid(
        observations, checkout, branch, env
    ):
        _quarantine_observations(observations, checkout, env)

    if _path_exists(observations):
        try:
            _recover_automation_changes(
                observations,
                env,
                allowed_roots=("README.md", "runs"),
            )
        except (RuntimeError, subprocess.CalledProcessError):
            _quarantine_observations(observations, checkout, env)

    if _path_exists(observations):
        if not remote_exists:
            _quarantine_observations(observations, checkout, env)
        else:
            behind, ahead = _ahead_behind(observations, env, f"origin/{branch}", branch)
            if ahead:
                _quarantine_observations(observations, checkout, env)
            elif behind:
                _git(observations, env, "merge", "--ff-only", f"origin/{branch}")

    if not _path_exists(observations):
        _create_observations(
            observations,
            checkout,
            branch,
            env,
            remote_exists=remote_exists,
        )
    return observations


def _replace_site(checkout: Path, candidate: Path, site_name: str) -> None:
    destination = checkout / site_name
    incoming = checkout / f".{site_name}.incoming"
    previous = checkout / f".{site_name}.previous"
    if incoming.exists() or previous.exists():
        raise RuntimeError("stale atomic site replacement directory exists")
    shutil.copytree(candidate, incoming)
    if destination.exists():
        destination.rename(previous)
    try:
        incoming.rename(destination)
    except Exception:
        if previous.exists():
            previous.rename(destination)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def _commit_if_needed(
    cwd: Path,
    env: dict[str, str],
    message: str,
    author_name: str,
    run_id: str,
) -> str | None:
    if not _git(cwd, env, "diff", "--cached", "--quiet", check=False).returncode:
        subject = _git(cwd, env, "log", "-1", "--format=%s").stdout.strip()
        if run_id in subject and subject == message:
            return _git(cwd, env, "rev-parse", "HEAD").stdout.strip()
        return None
    _git(
        cwd,
        env,
        "-c",
        f"user.name={author_name}",
        "-c",
        "user.email=agent-farm@local",
        "commit",
        "-m",
        message,
    )
    return _git(cwd, env, "rev-parse", "HEAD").stdout.strip()


def _safe_integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _safe_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _safe_identifier(value: object) -> str | None:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        return None
    return value


def _safe_timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _safe_manifest(value: object) -> dict[str, dict[str, int | str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, int | str]] = {}
    entries = sorted(
        ((path, metadata) for path, metadata in value.items() if isinstance(path, str)),
        key=lambda item: item[0],
    )
    for path, metadata in entries:
        if len(path) > 512 or any(ord(char) < 32 for char in path):
            continue
        relative = PurePosixPath(path)
        if relative.is_absolute() or not relative.parts or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            continue
        if not isinstance(metadata, dict):
            continue
        digest = metadata.get("sha256")
        size = _safe_integer(metadata.get("bytes"))
        if not isinstance(digest, str) or not _SAFE_SHA256.fullmatch(digest):
            continue
        if size is None or size < 0:
            continue
        result[path] = {"sha256": digest, "bytes": size}
    return result


def _manifest_summary(value: object) -> dict[str, int | str]:
    manifest = _safe_manifest(value)
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return {
        "file_count": len(manifest),
        "total_bytes": sum(int(metadata["bytes"]) for metadata in manifest.values()),
        "tree_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _validation_summary(value: object) -> dict[str, int | bool | None]:
    source = value if isinstance(value, dict) else {}
    static_errors = source.get("static_errors")
    browser_errors = source.get("browser_errors")
    screenshots = source.get("screenshots")
    return {
        "ok": source.get("ok") if isinstance(source.get("ok"), bool) else None,
        "checked_files": _safe_integer(source.get("checked_files")),
        "checked_pages": _safe_integer(source.get("checked_pages")),
        "total_bytes": _safe_integer(source.get("total_bytes")),
        "static_error_count": len(static_errors) if isinstance(static_errors, list) else 0,
        "browser_error_count": len(browser_errors) if isinstance(browser_errors, list) else 0,
        "screenshot_count": len(screenshots) if isinstance(screenshots, list) else 0,
    }


def _compact_record(
    record: dict[str, Any],
    main_commit: str | None,
    *,
    expected_opencode_version: str | None = None,
) -> dict[str, Any]:
    changed_files = record.get("changed_files")
    status = record.get("status")
    version = record.get("opencode_version")
    return {
        "schema_version": 2,
        "run_id": _safe_identifier(record.get("run_id")),
        "started_at": _safe_timestamp(record.get("started_at")),
        "finished_at": _safe_timestamp(record.get("finished_at")),
        "published_at": _safe_timestamp(record.get("published_at")),
        "model": _safe_identifier(record.get("model")),
        "pool_version": _safe_integer(record.get("pool_version")),
        "epoch": _safe_integer(record.get("epoch")),
        "epoch_seed": _safe_integer(record.get("epoch_seed")),
        "epoch_position": _safe_integer(record.get("epoch_position")),
        "opencode_version": _safe_identifier(version)
        if version == expected_opencode_version
        else None,
        "duration_seconds": _safe_number(record.get("duration_seconds")),
        "returncode": _safe_integer(record.get("returncode")),
        "timed_out": record.get("timed_out")
        if isinstance(record.get("timed_out"), bool)
        else None,
        "status": status if status in _PUBLIC_STATUSES else None,
        "accepted": record.get("accepted")
        if isinstance(record.get("accepted"), bool)
        else None,
        "changed_file_count": len(changed_files) if isinstance(changed_files, list) else 0,
        "before": _manifest_summary(record.get("before_manifest")),
        "after": _manifest_summary(record.get("after_manifest")),
        "validation": _validation_summary(record.get("validation")),
        "main_commit": main_commit
        if isinstance(main_commit, str) and _SAFE_COMMIT.fullmatch(main_commit)
        else None,
    }


def _remote_ref_exists(cwd: Path, env: dict[str, str], branch: str) -> bool:
    return (
        _git(
            cwd,
            env,
            "show-ref",
            "--verify",
            f"refs/remotes/origin/{branch}",
            check=False,
        ).returncode
        == 0
    )


def _expected_refspecs_needing_push(
    checkout: Path,
    env: dict[str, str],
    expected_refs: tuple[tuple[str, str], ...],
) -> list[str]:
    changed: list[str] = []
    for branch, expected_commit in expected_refs:
        if not _remote_ref_exists(checkout, env, branch):
            changed.append(f"{expected_commit}:refs/heads/{branch}")
            continue
        remote = _git(checkout, env, "rev-parse", f"origin/{branch}").stdout.strip()
        if expected_commit != remote:
            changed.append(f"{expected_commit}:refs/heads/{branch}")
    return changed


def _assert_prepared_tips(
    receipt: dict[str, Any],
    checkout: Path,
    observations: Path,
    env: dict[str, str],
    config: LabConfig,
) -> None:
    observation_head = _git(observations, env, "rev-parse", "HEAD").stdout.strip()
    if observation_head != receipt["observation_commit"]:
        raise RuntimeError("observations branch changed after publication preparation")

    main_head = _git(checkout, env, "rev-parse", "HEAD").stdout.strip()
    expected_main = receipt.get("main_commit")
    if expected_main is None:
        expected_main = _git(
            checkout,
            env,
            "rev-parse",
            f"origin/{config.publish.main_branch}",
        ).stdout.strip()
    if main_head != expected_main:
        raise RuntimeError("main branch changed after publication preparation")


def _structured_sha256(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _publication_receipt(record: dict[str, Any]) -> dict[str, Any] | None:
    value = record.get("_publication")
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise RuntimeError("pending publication has an invalid internal receipt")
    main_commit = value.get("main_commit")
    observation_commit = value.get("observation_commit")
    observation_sha256 = value.get("observation_sha256")
    candidate = value.get("candidate")
    if main_commit is not None and (
        not isinstance(main_commit, str) or not _SAFE_COMMIT.fullmatch(main_commit)
    ):
        raise RuntimeError("pending publication receipt has an invalid main commit")
    if not isinstance(observation_commit, str) or not _SAFE_COMMIT.fullmatch(
        observation_commit
    ):
        raise RuntimeError("pending publication receipt has an invalid observation commit")
    if not isinstance(observation_sha256, str) or not _SAFE_SHA256.fullmatch(
        observation_sha256
    ):
        raise RuntimeError("pending publication receipt has an invalid observation digest")
    if candidate is not None:
        if not isinstance(candidate, dict):
            raise RuntimeError("pending publication receipt has an invalid candidate digest")
        if set(candidate) != {"file_count", "total_bytes", "tree_sha256"}:
            raise RuntimeError("pending publication receipt has an invalid candidate digest")
        file_count = _safe_integer(candidate.get("file_count"))
        total_bytes = _safe_integer(candidate.get("total_bytes"))
        if (
            file_count is None
            or file_count < 0
            or total_bytes is None
            or total_bytes < 0
        ):
            raise RuntimeError("pending publication receipt has an invalid candidate digest")
        tree = candidate.get("tree_sha256")
        if not isinstance(tree, str) or not _SAFE_SHA256.fullmatch(tree):
            raise RuntimeError("pending publication receipt has an invalid candidate digest")
    return value


def _is_ancestor(cwd: Path, env: dict[str, str], commit: str, branch: str) -> bool:
    if not _remote_ref_exists(cwd, env, branch):
        return False
    return (
        _git(
            cwd,
            env,
            "merge-base",
            "--is-ancestor",
            commit,
            f"origin/{branch}",
            check=False,
        ).returncode
        == 0
    )


def _sync_worktree_to_remote(
    cwd: Path,
    env: dict[str, str],
    branch: str,
) -> None:
    behind, ahead = _ahead_behind(cwd, env, f"origin/{branch}", branch)
    if ahead:
        raise RuntimeError(f"automation branch is unexpectedly ahead after push: {branch}")
    if behind:
        _git(cwd, env, "merge", "--ff-only", f"origin/{branch}")


def _receipt_is_remote(
    receipt: dict[str, Any],
    checkout: Path,
    observations: Path,
    env: dict[str, str],
    config: LabConfig,
) -> bool:
    expected: list[bool] = []
    main_commit = receipt.get("main_commit")
    if isinstance(main_commit, str):
        expected.append(
            _is_ancestor(checkout, env, main_commit, config.publish.main_branch)
        )
    expected.append(
        _is_ancestor(
            observations,
            env,
            str(receipt["observation_commit"]),
            config.observations_branch,
        )
    )
    if all(expected):
        return True
    if any(expected):
        raise RuntimeError("atomic publication receipt is present on only one remote branch")
    return False


def _confirm_publication(
    receipt: dict[str, Any],
    record: dict[str, Any],
    candidate: Path,
    observation_path: Path,
    checkout: Path,
    observations: Path,
    env: dict[str, str],
    config: LabConfig,
) -> bool:
    if record["accepted"]:
        candidate_summary = _manifest_summary(content_manifest(candidate))
        if receipt.get("candidate") != candidate_summary:
            raise RuntimeError("accepted candidate changed after its publication was prepared")
    elif receipt.get("candidate") is not None:
        raise RuntimeError("rejected publication receipt unexpectedly names a candidate")

    _git(checkout, env, "fetch", "--prune", "origin")
    if not _receipt_is_remote(receipt, checkout, observations, env, config):
        return False

    _sync_worktree_to_remote(checkout, env, config.publish.main_branch)
    _sync_worktree_to_remote(observations, env, config.observations_branch)

    if not observation_path.is_file():
        raise RuntimeError("confirmed observation record is missing from the remote branch")
    try:
        public_record = json.loads(observation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("confirmed observation record is unreadable") from exc
    if _structured_sha256(public_record) != receipt["observation_sha256"]:
        raise RuntimeError("confirmed observation record changed on the remote branch")

    if record["accepted"]:
        target_site = checkout / config.site_dir.name
        if not target_site.is_dir() or content_manifest(target_site) != content_manifest(
            candidate
        ):
            raise RuntimeError("current remote site no longer matches the accepted candidate")
    return True


def _finalize_publication(
    record: dict[str, Any],
    receipt: dict[str, Any],
    run_dir: Path,
    spool_path: Path,
    checkout: Path,
    config: LabConfig,
) -> dict[str, Any]:
    main_commit = receipt.get("main_commit")
    final_record = dict(record)
    final_record.pop("_publication", None)
    final_record["main_commit"] = main_commit
    atomic_write_json(run_dir / "record.json", final_record)
    if record["accepted"]:
        update_lineage(config, checkout / config.site_dir.name)
    spool_path.unlink()
    return {
        "status": "published",
        "run_id": str(record["run_id"]),
        "accepted": bool(record["accepted"]),
        "main_commit": main_commit,
    }


def publish_next(config: LabConfig, *, browser: bool = True) -> dict[str, Any]:
    config.state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    config.state_dir.chmod(0o700)
    spool = config.state_dir / "spool"
    with exclusive_lock(config.state_dir / "publish.lock"):
        pending = sorted(spool.glob("*.json"))
        if not pending:
            return {"status": "idle", "message": "no publication is pending"}
        if not config.publish.deploy_key.is_file():
            raise RuntimeError(f"dedicated deploy key is missing: {config.publish.deploy_key}")
        if config.publish.deploy_key.stat().st_mode & 0o077:
            raise RuntimeError("deploy key permissions must be 0600")

        spool_path = pending[0]
        record: dict[str, Any] = json.loads(spool_path.read_text(encoding="utf-8"))
        run_value = record.get("run_id")
        if not isinstance(run_value, str) or not _RUN_ID.fullmatch(run_value):
            raise RuntimeError("pending publication has an invalid run ID")
        if spool_path.stem != run_value:
            raise RuntimeError("pending publication filename does not match its run ID")
        if not isinstance(record.get("accepted"), bool):
            raise RuntimeError("pending publication has an invalid accepted flag")
        if record.get("model") not in config.models:
            raise RuntimeError("pending publication names a model outside the configured pool")
        if "published_at" not in record:
            record["published_at"] = timestamp()
            atomic_write_json(spool_path, record)
        run_id = run_value
        try:
            started = datetime.fromisoformat(str(record["started_at"]))
        except (KeyError, ValueError) as exc:
            raise RuntimeError("pending publication has an invalid start timestamp") from exc
        run_dir = config.state_dir / "raw" / run_id
        candidate = run_dir / "candidate"
        env = _git_env(
            config.publish.deploy_key,
            config.state_dir / "github-known-hosts",
        )
        checkout = _ensure_checkout(config, env)
        observations = _ensure_observations(config, checkout, env)

        relative = Path("runs") / f"{started:%Y}" / f"{started:%m}" / f"{run_id}.json"
        observation_path = observations / relative
        receipt = _publication_receipt(record)
        if receipt is not None and _confirm_publication(
            receipt,
            record,
            candidate,
            observation_path,
            checkout,
            observations,
            env,
            config,
        ):
            return _finalize_publication(
                record,
                receipt,
                run_dir,
                spool_path,
                checkout,
                config,
            )

        main_commit: str | None = None
        validated_candidate_manifest: dict[str, dict[str, object]] | None = None
        if record.get("accepted"):
            candidate_before_validation = content_manifest(candidate)
            report = validate_site(
                candidate,
                config.validation,
                run_dir / "publisher-screenshots",
                browser=browser,
            )
            validated_candidate_manifest = content_manifest(candidate)
            if validated_candidate_manifest != candidate_before_validation:
                raise RuntimeError("accepted candidate changed during publisher validation")
            if not report.ok:
                raise RuntimeError("publisher revalidation rejected an accepted candidate")

            target_site = checkout / config.site_dir.name
            if (
                not target_site.exists()
                or content_manifest(target_site) != validated_candidate_manifest
            ):
                _replace_site(checkout, candidate, config.site_dir.name)
                if content_manifest(target_site) != validated_candidate_manifest:
                    raise RuntimeError("copied site does not match the validated candidate")
                _git(checkout, env, "add", "--", config.site_dir.name)
            author = str(record["model"]).replace("/", "-")[:60]
            main_commit = _commit_if_needed(
                checkout,
                env,
                f"website turn {run_id}: {record['model']}",
                f"Agent Farm ({author})",
                run_id,
            )
            committed_site = _committed_site_manifest(
                checkout,
                env,
                main_commit
                if main_commit is not None
                else _git(checkout, env, "rev-parse", "HEAD").stdout.strip(),
                config.site_dir.name,
            )
            if committed_site != validated_candidate_manifest:
                raise RuntimeError("committed site does not match the validated candidate")

        compact = _compact_record(
            record,
            main_commit,
            expected_opencode_version=config.opencode.version,
        )
        if observation_path.exists():
            existing = json.loads(observation_path.read_text(encoding="utf-8"))
            if existing != compact:
                raise RuntimeError(f"observation record already exists with different content: {relative}")
        else:
            observation_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(observation_path, compact)
            _git(observations, env, "add", "--", relative.as_posix())
        observation_commit = _commit_if_needed(
            observations,
            env,
            f"record website turn {run_id}",
            "Agent Farm Observer",
            run_id,
        )
        if observation_commit is None:
            raise RuntimeError("could not attribute the observation commit to the pending run")

        receipt = {
            "schema_version": 1,
            "main_commit": main_commit,
            "observation_commit": observation_commit,
            "observation_sha256": _structured_sha256(compact),
            "candidate": _manifest_summary(validated_candidate_manifest)
            if record["accepted"]
            else None,
        }
        record["_publication"] = receipt
        atomic_write_json(spool_path, record)

        _assert_prepared_tips(receipt, checkout, observations, env, config)
        expected_refs: list[tuple[str, str]] = [
            (config.observations_branch, observation_commit)
        ]
        if main_commit is not None:
            expected_refs.insert(0, (config.publish.main_branch, main_commit))
        changed_refspecs = _expected_refspecs_needing_push(
            checkout,
            env,
            tuple(expected_refs),
        )
        if changed_refspecs:
            _git(checkout, env, "push", "--atomic", "origin", *changed_refspecs)
        if not _confirm_publication(
            receipt,
            record,
            candidate,
            observation_path,
            checkout,
            observations,
            env,
            config,
        ):
            raise RuntimeError("atomic publication did not reach the remote")
        return _finalize_publication(
            record,
            receipt,
            run_dir,
            spool_path,
            checkout,
            config,
        )
