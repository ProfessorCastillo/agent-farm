from __future__ import annotations

import fcntl
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import LabConfig
from .durability import fsync_directory, fsync_tree
from .state import atomic_write_json


_TRANSACTION = "replacement.json"
_PREVIOUS = ".site.previous"
_NEXT_PREFIX = ".site.next-"


@contextmanager
def _lineage_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "lineage.lock").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _remove_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _transaction_next(root: Path) -> Path | None:
    marker = root / _TRANSACTION
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("lineage replacement marker is unreadable") from exc
    name = data.get("next") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name.startswith(_NEXT_PREFIX) or Path(name).name != name:
        raise RuntimeError("lineage replacement marker is invalid")
    return root / name


def _recover_locked(root: Path) -> None:
    site = root / "site"
    previous = root / _PREVIOUS
    marker = root / _TRANSACTION
    incoming = _transaction_next(root)

    if incoming is not None:
        if incoming.is_dir() and not incoming.is_symlink():
            _remove_tree(previous)
            if site.exists() or site.is_symlink():
                os.replace(site, previous)
            os.replace(incoming, site)
            fsync_directory(root)
        elif not site.is_dir() and previous.is_dir():
            os.replace(previous, site)
            fsync_directory(root)
        if not site.is_dir() or site.is_symlink():
            raise RuntimeError("lineage replacement cannot be recovered")
        _remove_tree(previous)
        marker.unlink(missing_ok=True)
        fsync_directory(root)
    elif not site.is_dir() and previous.is_dir():
        os.replace(previous, site)
        fsync_directory(root)
    elif site.is_dir():
        _remove_tree(previous)

    if (site.exists() or site.is_symlink()) and (
        not site.is_dir() or site.is_symlink()
    ):
        raise RuntimeError("authoritative lineage site is not a real directory")

    for stale in root.glob(f"{_NEXT_PREFIX}*"):
        _remove_tree(stale)


def _replace_locked(root: Path, source: Path) -> Path:
    if not source.is_dir() or source.is_symlink():
        raise RuntimeError(f"lineage source is not a real directory: {source}")
    incoming = root / f"{_NEXT_PREFIX}{uuid.uuid4().hex}"
    shutil.copytree(source, incoming, symlinks=True)
    fsync_tree(incoming)
    atomic_write_json(root / _TRANSACTION, {"schema_version": 1, "next": incoming.name})
    _recover_locked(root)
    return root / "site"


def ensure_lineage(config: LabConfig) -> Path:
    """Return the authoritative site, seeding it once from the repository baseline."""

    root = config.state_dir / "lineage"
    with _lineage_lock(root):
        _recover_locked(root)
        site = root / "site"
        if not site.is_dir():
            _replace_locked(root, config.site_dir)
        return site


def update_lineage(config: LabConfig, source: Path) -> Path:
    """Durably replace the authoritative site after a successful publication."""

    root = config.state_dir / "lineage"
    with _lineage_lock(root):
        _recover_locked(root)
        return _replace_locked(root, source)
