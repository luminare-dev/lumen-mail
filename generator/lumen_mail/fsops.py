"""File-system steps of install, sync and uninstall: atomic swaps, copies, modes, backups.

Rules:
  * a new skin folder is assembled next to its destination on the same mount and put in place
    with one rename; an existing folder is swapped with renameat2(RENAME_EXCHANGE), so
    skins/lumen never disappears, even for a moment;
  * rename(2) does not work across mount points, even on the same file system (EXDEV). Inside
    the systemd unit, the Roundcube root and the state folder are separate bind mounts, so
    staging lives in <roundcube>/.lumen-mail/ and moves into the state folder are copies;
  * nothing is ever deleted in place: a replaced skin goes to <state>/backups/.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import datetime as _dt
import errno
import grp
import os
import pwd
import re
import shutil
import sys
from pathlib import Path

from .util import LumenError

_RENAME_EXCHANGE = 2
_AT_FDCWD = -100
BACKUP_NAME_RE = re.compile(r"^\d{8}T\d{12}Z-[a-z-]+$")
_libc = None


def _renameat2():
    global _libc
    if not sys.platform.startswith("linux"):
        return None
    if _libc is None:
        name = ctypes.util.find_library("c")
        _libc = ctypes.CDLL(name, use_errno=True) if name else False
    if not _libc:
        return None
    fn = getattr(_libc, "renameat2", None)
    if fn is not None:
        fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        fn.restype = ctypes.c_int
    return fn


def exchange(a: Path, b: Path) -> bool:
    """Atomically swap two existing paths. False if the kernel or file system cannot."""
    fn = _renameat2()
    if fn is None:
        return False
    if fn(_AT_FDCWD, os.fsencode(a), _AT_FDCWD, os.fsencode(b), _RENAME_EXCHANGE) == 0:
        return True
    err = ctypes.get_errno()
    if err in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
        return False
    raise OSError(err, os.strerror(err), f"{a} <-> {b}")


def swap_in(new: Path, target: Path) -> Path | None:
    """Put ``new`` at ``target``. Returns where the previous ``target`` tree is now (the old
    path of ``new``, inside the staging folder), or None if there was none."""
    if not os.path.lexists(target):
        os.rename(new, target)
        return None
    if exchange(new, target):
        return new
    parked = new.with_name(new.name + ".previous")
    os.rename(target, parked)          # fallback without renameat2: a gap of microseconds
    os.rename(new, target)
    return parked


def copy_tree(src: Path, dest: Path) -> None:
    """Copy a skin folder (regular files and folders only; symlinks are refused)."""
    for dirpath, dirnames, filenames in os.walk(src):
        for name in dirnames + filenames:
            if os.path.islink(os.path.join(dirpath, name)):
                raise LumenError(f"{os.path.join(dirpath, name)} is a symlink; a skin folder must not contain any")
    shutil.copytree(src, dest, symlinks=True, copy_function=shutil.copy2)


def move_tree(src: Path, dest: Path) -> None:
    """Move a folder; across mount points this is a copy and a delete (shutil.move)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(dest):
        raise LumenError(f"{dest} already exists; refusing to overwrite it")
    shutil.move(str(src), str(dest))


def remove_tree(path: Path) -> None:
    if os.path.islink(path) or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def set_tree_modes(tree: Path, owner: tuple[int, int] | None) -> None:
    """Folders 755, files 644, and the owner if one is given (needs root)."""
    for dirpath, _dirnames, filenames in os.walk(tree):
        os.chmod(dirpath, 0o755)
        if owner:
            os.chown(dirpath, *owner)
        for name in filenames:
            path = os.path.join(dirpath, name)
            os.chmod(path, 0o644)
            if owner:
                os.chown(path, *owner)


def chown_path(path: Path, owner: tuple[int, int] | None) -> None:
    if owner:
        os.chown(path, *owner)


def resolve_owner(spec: str, reference: Path) -> tuple[int, int] | None:
    """The owner for files lumen-mail writes, or None to keep "whoever runs us".

    "auto" (default): when running as root, the owner of ``reference`` (the Roundcube skins
    folder, keyhelp:keyhelp on KeyHelp); otherwise None. "" never changes ownership.
    "user:group" sets that owner and needs root (unless it is the current user).
    """
    if not spec:
        return None
    if spec == "auto":
        if os.geteuid() != 0:
            return None
        probe = reference
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        st = probe.stat()
        return st.st_uid, st.st_gid
    user, _, group = spec.partition(":")
    try:
        uid = int(user) if user.isdigit() else pwd.getpwnam(user).pw_uid
        gid = int(group) if group.isdigit() else grp.getgrnam(group).gr_gid if group else pwd.getpwuid(uid).pw_gid
    except KeyError as exc:
        raise LumenError(f"--owner {spec!r}: unknown user or group") from exc
    if os.geteuid() != 0 and uid != os.geteuid():
        raise LumenError(f"--owner {spec!r}: changing the owner needs root (run as root, or pass --owner '')")
    return uid, gid


def stamp_name(now: _dt.datetime, reason: str) -> str:
    return now.astimezone(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + reason


def list_backups(backups: Path) -> list[Path]:
    """Backup folders, oldest first (the names start with a UTC time stamp)."""
    if not backups.is_dir():
        return []
    return sorted((p for p in backups.iterdir() if p.is_dir() and BACKUP_NAME_RE.match(p.name)),
                  key=lambda p: p.name)


def rotate_backups(backups: Path, keep: int) -> list[Path]:
    """Delete the oldest backup folders beyond ``keep``. Returns the deleted ones."""
    folders = list_backups(backups)
    doomed = folders[:-keep] if keep > 0 else folders
    for path in doomed:
        shutil.rmtree(path, ignore_errors=True)
    return doomed
