"""Running as root: do the root-only step, then continue as the Roundcube owner.

On KeyHelp the Roundcube owner (keyhelp) also runs the webmail's PHP, so whoever compromises the
webmail can change everything under the Roundcube root and in the state folder: plant symbolic
links, or put an @plugin into Elastic's LESS. A run as root must therefore neither follow links
in those trees nor run code from them.

So when lumen-mail starts as root, it does only this as root:

  * work out the Roundcube owner: the owner of <roundcube>/skins (lstat, never a link; the
    Roundcube path itself must not contain a symbolic link);
  * for commands that write: create the state folder if needed (its parent must belong to root
    and be writable only by root), refuse it if it is a symbolic link, and give it and its
    contents to the owner through file descriptors that never follow a link;

and then drops to the owner's uid and gid with no supplementary groups. Every later step,
including the LESS compile, has exactly the owner's rights, and no chown is needed any more.

A tree that belongs to root is refused for commands that write unless --owner names the owner
(for example --owner root:root on a server where root owns Roundcube). --owner '' keeps root
without changing any owner (not recommended). install-runtime always stays root.
"""

from __future__ import annotations

import grp
import os
import pwd
import stat
from pathlib import Path

from .util import LumenError

EXIT_REFUSED = 5


class PrivilegeError(LumenError):
    exit_code = EXIT_REFUSED


def parse_owner(spec: str) -> tuple[int, int]:
    user, _, group = spec.partition(":")
    try:
        uid = int(user) if user.isdigit() else pwd.getpwnam(user).pw_uid
        if group:
            gid = int(group) if group.isdigit() else grp.getgrnam(group).gr_gid
        else:
            gid = pwd.getpwuid(uid).pw_gid
    except KeyError as exc:
        raise LumenError(f"--owner {spec!r}: unknown user or group") from exc
    return uid, gid


def user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def target_owner(roundcube: Path, spec: str, strict: bool) -> tuple[int, int] | None:
    """The (uid, gid) a root run continues as, or None to stay root.

    ``strict`` (commands that write): a tree that belongs to root or cannot be read is refused
    instead of keeping root.
    """
    if spec == "":
        return None
    if spec != "auto":
        uid, gid = parse_owner(spec)
        return None if uid == 0 else (uid, gid)
    real = os.path.realpath(roundcube)
    if real != os.path.normpath(str(roundcube)):
        raise PrivilegeError(f"{roundcube} contains a symbolic link (it leads to {real})",
                             [f"pass the real path: --roundcube {real}"])
    probe = roundcube / "skins"
    try:
        st = os.lstat(probe)
    except FileNotFoundError:
        # During an update skins/ may be gone for a moment: the Roundcube root has the same owner.
        probe = roundcube
        try:
            st = os.lstat(probe)
        except FileNotFoundError:
            if strict:
                raise LumenError(f"{roundcube} does not exist (--roundcube)") from None
            return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise PrivilegeError(f"{probe} is not a plain folder (a symbolic link?); refusing to run as root")
    if st.st_uid == 0:
        if strict:
            raise PrivilegeError(
                f"{probe} belongs to root, so lumen-mail cannot tell which user should own the skin",
                ["pass --owner with the user that owns your Roundcube files (for example --owner www-data:www-data)",
                 "or --owner root:root if root really owns them"])
        return None
    return st.st_uid, st.st_gid


def prepare_state_root(root: Path, owner: tuple[int, int]) -> None:
    """As root: create the state folder if needed and give it (and its contents) to ``owner``.

    Never follows a symbolic link: the folder itself is opened with O_NOFOLLOW, its contents are
    changed through directory descriptors (os.fwalk), links are left alone, and a file with more
    than one hard link is skipped.
    """
    parent = root.parent
    try:
        pst = os.lstat(parent)
    except FileNotFoundError:
        parent.mkdir(parents=True, mode=0o755)
        pst = os.lstat(parent)
    if stat.S_ISLNK(pst.st_mode) or pst.st_uid != 0 or pst.st_mode & 0o022:
        raise PrivilegeError(f"the state folder's parent {parent} must be a folder that only root can change",
                             ["use the default /var/lib/lumen-mail or pass --state-dir in such a folder"])
    try:
        os.mkdir(root, 0o750)
    except FileExistsError:
        pass
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(root, flags)
    except OSError as exc:
        raise PrivilegeError(f"the state folder {root} is not a plain folder (a symbolic link?): {exc.strerror}",
                             [f"remove it and run the command again: rm {root}"]) from exc
    try:
        st = os.fstat(fd)
        if (st.st_uid, st.st_gid) != owner:
            os.fchown(fd, *owner)
        for _dirpath, dirnames, filenames, dirfd in os.fwalk(".", dir_fd=fd, follow_symlinks=False):
            for name in dirnames + filenames:
                est = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
                if stat.S_ISLNK(est.st_mode) or (stat.S_ISREG(est.st_mode) and est.st_nlink > 1):
                    continue
                if (est.st_uid, est.st_gid) != owner:
                    os.chown(name, *owner, dir_fd=dirfd, follow_symlinks=False)
    finally:
        os.close(fd)


def drop_to(owner: tuple[int, int]) -> None:
    """Become ``owner`` for good: no supplementary groups, then gid, then uid."""
    uid, gid = owner
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    if os.getuid() != uid or os.geteuid() != uid or os.getgid() != gid:
        raise PrivilegeError("could not drop root privileges")
    try:
        home = pwd.getpwuid(uid).pw_dir
    except KeyError:
        home = "/"
    os.environ["HOME"] = home
    os.environ["USER"] = os.environ["LOGNAME"] = user_name(uid)
