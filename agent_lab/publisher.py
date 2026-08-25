from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import LabConfig
from .runner import exclusive_lock, timestamp
from .state import atomic_write_json
from .validation import content_manifest, validate_site


def _git_env(key: Path, known_hosts: Path) -> dict[str, str]:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": (
            f"ssh -i {key} -o IdentitiesOnly=yes "
            f"-o UserKnownHostsFile={known_hosts} "
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


def _ensure_checkout(config: LabConfig, env: dict[str, str]) -> Path:
    checkout = config.state_dir / "repository"
    if not (checkout / ".git").exists():
        if checkout.exists():
            raise RuntimeError(f"publisher checkout is not a Git repository: {checkout}")
        checkout.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", config.publish.remote, str(checkout)],
            cwd=config.state_dir,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
    _git(checkout, env, "fetch", "--prune", "origin")
    _git(checkout, env, "switch", config.publish.main_branch)
    if _git(checkout, env, "status", "--porcelain").stdout.strip():
        raise RuntimeError("publisher checkout contains unexpected uncommitted changes")
    behind, ahead = _ahead_behind(
        checkout,
        env,
        f"origin/{config.publish.main_branch}",
        config.publish.main_branch,
    )
    if behind and ahead:
        raise RuntimeError("publisher main branch diverged from origin")
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


def _ensure_observations(
    config: LabConfig,
    checkout: Path,
    env: dict[str, str],
) -> Path:
    observations = config.state_dir / "observations-worktree"
    branch = config.observations_branch
    if not observations.exists():
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
        else:
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
    elif not (observations / ".git").exists():
        raise RuntimeError("observations path is not a Git worktree")

    _git(checkout, env, "fetch", "origin", branch, check=False)
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
    if remote_exists:
        behind, ahead = _ahead_behind(observations, env, f"origin/{branch}", branch)
        if behind and ahead:
            raise RuntimeError("observations branch diverged from origin")
        if behind:
            _git(observations, env, "merge", "--ff-only", f"origin/{branch}")
    if _git(observations, env, "status", "--porcelain").stdout.strip():
        raise RuntimeError("observations worktree contains unexpected uncommitted changes")
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
) -> str:
    if not _git(cwd, env, "diff", "--cached", "--quiet", check=False).returncode:
        return _git(cwd, env, "rev-parse", "HEAD").stdout.strip()
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


def _compact_record(record: dict[str, Any], main_commit: str | None) -> dict[str, Any]:
    keep = {
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
        "final_output_excerpt",
    }
    compact = {key: record.get(key) for key in keep}
    compact["main_commit"] = main_commit
    compact["published_at"] = record["published_at"]
    return compact


def publish_next(config: LabConfig, *, browser: bool = True) -> dict[str, Any]:
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
        if "published_at" not in record:
            record["published_at"] = timestamp()
            atomic_write_json(spool_path, record)
        run_id = str(record["run_id"])
        run_dir = config.state_dir / "raw" / run_id
        candidate = run_dir / "candidate"
        env = _git_env(
            config.publish.deploy_key,
            config.state_dir / "github-known-hosts",
        )
        checkout = _ensure_checkout(config, env)
        observations = _ensure_observations(config, checkout, env)

        main_commit: str | None = None
        if record.get("accepted"):
            report = validate_site(
                candidate,
                config.validation,
                run_dir / "publisher-screenshots",
                browser=browser,
            )
            if not report.ok:
                raise RuntimeError("publisher revalidation rejected an accepted candidate")

            target_site = checkout / config.site_dir.name
            if not target_site.exists() or content_manifest(target_site) != content_manifest(candidate):
                _replace_site(checkout, candidate, config.site_dir.name)
                _git(checkout, env, "add", "--", config.site_dir.name)
            author = str(record.get("model", "unknown")).replace("/", "-")[:60]
            main_commit = _commit_if_needed(
                checkout,
                env,
                f"website turn {run_id}: {record.get('model')}",
                f"Agent Farm ({author})",
            )

        started = datetime.fromisoformat(str(record["started_at"]))
        relative = Path("runs") / f"{started:%Y}" / f"{started:%m}" / f"{run_id}.json"
        observation_path = observations / relative
        compact = _compact_record(record, main_commit)
        if observation_path.exists():
            existing = json.loads(observation_path.read_text(encoding="utf-8"))
            if existing != compact:
                raise RuntimeError(f"observation record already exists with different content: {relative}")
        else:
            observation_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(observation_path, compact)
            _git(observations, env, "add", "--", relative.as_posix())
        _commit_if_needed(
            observations,
            env,
            f"record website turn {run_id}",
            "Agent Farm Observer",
        )

        refs = [config.publish.main_branch, config.observations_branch]
        _git(checkout, env, "push", "--atomic", "origin", *refs)
        record["main_commit"] = main_commit
        atomic_write_json(run_dir / "record.json", record)
        spool_path.unlink()
        return {
            "status": "published",
            "run_id": run_id,
            "accepted": bool(record.get("accepted")),
            "main_commit": main_commit,
        }
