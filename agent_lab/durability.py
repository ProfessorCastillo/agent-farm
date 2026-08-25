from __future__ import annotations

import os
from pathlib import Path


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_tree(root: Path) -> None:
    """Durably flush a regular, symlink-free directory tree."""

    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"cannot fsync a non-directory tree: {root}")
    directories: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        directories.append(current)
        for dirname in dirnames:
            child = current / dirname
            if child.is_symlink():
                raise RuntimeError(f"cannot fsync a tree containing a symlink: {child}")
        for filename in filenames:
            path = current / filename
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f"cannot fsync a non-regular file: {path}")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for directory in reversed(directories):
        fsync_directory(directory)
