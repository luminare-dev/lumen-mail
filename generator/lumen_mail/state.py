"""The state folder (default /var/lib/lumen-mail): last good build, backups, lock, sync state.

    <state>/last-good/          a complete copy of the last skins/lumen that passed verify
    <state>/backups/<ts>-<why>/lumen/   replaced or removed skin folders (the newest 5 are kept)
    <state>/lock                flock(2) lock: one install/sync/rollback/uninstall at a time
    <state>/sync-state.json     failure back-off, deferral reason, hold, uninstalled marker
    <state>/rebuild-requested   written by request-rebuild; the next sync rebuilds and removes it
    <state>/ROLLBACK.txt        the undo commands of the last install, rollback or uninstall

The folder survives everything that happens to the Roundcube tree (KeyHelp's update removes the
whole tree). Location: --state-dir, else $LUMEN_MAIL_STATE_DIR, else $STATE_DIRECTORY (set by
systemd's StateDirectory=), else /var/lib/lumen-mail.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import fcntl
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .util import LumenError

DEFAULT_STATE_DIR = Path("/var/lib/lumen-mail")
STATE_SCHEMA = 1
EXIT_TEMPFAIL = 75


class BusyError(LumenError):
    """Another lumen-mail run holds the lock."""

    exit_code = EXIT_TEMPFAIL


@dataclass(frozen=True)
class StatePaths:
    root: Path

    @classmethod
    def locate(cls, arg: str | os.PathLike | None = None) -> "StatePaths":
        value = arg or os.environ.get("LUMEN_MAIL_STATE_DIR")
        if not value and os.environ.get("STATE_DIRECTORY"):
            value = os.environ["STATE_DIRECTORY"].split(":", 1)[0]
        return cls(Path(value or DEFAULT_STATE_DIR).absolute())

    @property
    def last_good(self) -> Path:
        return self.root / "last-good"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def lock(self) -> Path:
        return self.root / "lock"

    @property
    def sync_state(self) -> Path:
        return self.root / "sync-state.json"

    @property
    def rebuild_request(self) -> Path:
        return self.root / "rebuild-requested"

    @property
    def rollback_notes(self) -> Path:
        return self.root / "ROLLBACK.txt"


@contextlib.contextmanager
def locked(path: Path, timeout: float, what: str = "lumen-mail",
           owner: tuple[int, int] | None = None) -> Iterator[None]:
    """Hold an exclusive flock on ``path``; wait up to ``timeout`` seconds, then raise BusyError.

    The lock file is never followed if it is a symbolic link (O_NOFOLLOW), and its owner is set
    through the descriptor. It may belong to another user: flock works on a descriptor opened
    read-only, so that is the fallback.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | flags, 0o644)
        except PermissionError:
            fd = os.open(path, os.O_RDONLY | flags)
    except OSError as exc:
        if os.path.islink(path):
            raise LumenError(f"the lock file {path} is a symbolic link; refusing to use it",
                             [f"check it and remove it: rm {path}"]) from exc
        raise
    try:
        if owner:
            st = os.fstat(fd)
            if (st.st_uid, st.st_gid) != owner:
                with contextlib.suppress(OSError):
                    os.fchown(fd, *owner)
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise BusyError(f"another {what} run holds {path}; try again later") from None
                time.sleep(0.1)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


def atomic_write(path: Path, text: str, owner: tuple[int, int] | None = None, mode: int = 0o644) -> None:
    """Write ``path`` through a new temporary file in the same folder (never through a link that
    may be at ``path``), set its mode and owner on the descriptor, flush it, rename it into place."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fchmod(fh.fileno(), mode)
            if owner:
                os.fchown(fh.fileno(), *owner)
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def iso(ts: _dt.datetime) -> str:
    return ts.astimezone(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class SyncState:
    """What sync remembers between runs. Written only when something changes."""

    failure: dict[str, Any] | None = None      # {key, attempts, last_attempt, next_attempt, error, exit_code}
    deferred: dict[str, Any] | None = None     # {kind, since, warned?}
    hold: dict[str, Any] | None = None         # {since, backup}
    uninstalled: str | None = None             # ISO time of the uninstall
    _loaded: str = field(default="", repr=False)

    @classmethod
    def load(cls, paths: StatePaths) -> "SyncState":
        try:
            raw = paths.sync_state.read_text(encoding="utf-8")
            data = json.loads(raw)
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            return cls()  # unreadable state is treated as empty; the next write replaces it
        if not isinstance(data, dict):
            return cls()
        state = cls(failure=data.get("failure"), deferred=data.get("deferred"), hold=data.get("hold"),
                    uninstalled=data.get("uninstalled"))
        state._loaded = state._dump()
        return state

    def _dump(self) -> str:
        data = {"schema": STATE_SCHEMA, "failure": self.failure, "deferred": self.deferred, "hold": self.hold,
                "uninstalled": self.uninstalled}
        return json.dumps(data, indent=2, sort_keys=True) + "\n"

    def save(self, paths: StatePaths, owner: tuple[int, int] | None = None) -> bool:
        """Write the file atomically if the content changed. Returns True if it wrote."""
        text = self._dump()
        if text == self._loaded:
            return False
        paths.root.mkdir(parents=True, exist_ok=True)
        atomic_write(paths.sync_state, text, owner)
        self._loaded = text
        return True
