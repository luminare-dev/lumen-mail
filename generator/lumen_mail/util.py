"""Small helpers shared by the commands (hashing, file walking, messages)."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Iterable


class LumenError(Exception):
    """An error with a message meant for the operator (printed without a traceback)."""

    exit_code = 1

    def __init__(self, message: str, details: Iterable[str] = ()):
        super().__init__(message)
        self.details = list(details)

    def render(self) -> str:
        lines = [f"error: {self}"]
        lines += [f"  - {d}" for d in self.details]
        return "\n".join(lines)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def short_hash(path: Path, length: int = 10) -> str:
    """The cache-buster value for a file: the first characters of its sha256."""
    return sha256_file(path)[:length]


def walk_files(root: Path) -> list[Path]:
    """Every regular file under root (symlinks to files included), as sorted relative paths."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            if full.is_file():
                out.append(full.relative_to(root))
    return sorted(out, key=lambda p: p.as_posix())


def tree_digest(root: Path, patterns: Iterable[str]) -> str:
    """sha256 over the relative path and content of every file matching one of the globs."""
    files: set[Path] = set()
    for pattern in patterns:
        files.update(p for p in root.glob(pattern) if p.is_file())
    h = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix().encode()
        h.update(len(rel).to_bytes(4, "big") + rel)
        data = path.read_bytes()
        h.update(len(data).to_bytes(8, "big") + data)
    return "sha256:" + h.hexdigest()


def info(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(message, file=sys.stderr)
