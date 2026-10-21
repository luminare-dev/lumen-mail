"""install, check, sync, status, rollback, resume, request-rebuild and uninstall.

KeyHelp removes the whole Roundcube tree when it updates Roundcube ("rm -rf <roundcube>/*",
extract the new release, rewrite config.inc.php, chown -R; about two seconds). While Lumen is the
system skin, webmail shows an error page from the moment skins/lumen is gone until it is back.
sync therefore works in two steps:

1. Fast restore. As soon as the new tree is extracted (program/include/iniset.php and
   skins/elastic/meta.json exist), a missing or damaged skins/lumen is replaced by the last good
   build from the state folder: copy into <roundcube>/.lumen-mail/ (same mount), one rename.
   No Node, no compile; it takes milliseconds. The restored build may be stale but works.
2. Rebuild. If the stamp no longer matches (Roundcube version, Elastic digest, lumen-mail version
   or sources), sync waits until the tree has stopped changing (KeyHelp has finished), checks the
   back-off and the free memory, builds into staging, verifies, swaps it in with one atomic
   rename and saves it as the new last good build. A failed rebuild keeps the active build, is
   logged as an error and backs off (10 min, 30 min, 1 h, 2 h, then every 6 h) until the inputs
   change.

A run that finds everything current writes nothing and logs only at info level. Every run that
writes holds the lock, so a path-triggered run, a timer run and a manual install never overlap.

Exit codes (also in docs/cli.md): 0 ok; 1 error (sync: the rebuild failed, the active build
stays); 2 usage; 3 Elastic drift; 4 compile error; 5 refused (uninstall while the system skin is
lumen); 6 not installed; 10 sync needed (check); 75 try again later (lock busy, Roundcube tree
incomplete, too little memory, back-off after a failed rebuild).
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import re
import shlex
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from . import SKIN_NAME, STAMP_NAME
from .build import BuildOptions, build
from .elastic import check_drift
from .fsops import (chown_path, copy_tree, exchange, list_backups, move_tree, remove_tree, resolve_owner,
                    rotate_backups, set_tree_modes, stamp_name, swap_in)
from .log import Log
from .phpconfig import system_skin
from .roundcube import Roundcube
from .sources import PACKAGE_DIR, Sources
from .state import DEFAULT_STATE_DIR, StatePaths, SyncState, iso, locked, parse_iso
from .util import LumenError, sha256_file
from .verify import verify

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_DRIFT = 3
EXIT_COMPILE = 4
EXIT_REFUSED = 5
EXIT_NOT_INSTALLED = 6
EXIT_SYNC_NEEDED = 10
EXIT_TEMPFAIL = 75

SCRATCH_NAME = ".lumen-mail"          # in the Roundcube root: outside skins/, survives "rm -rf <root>/*"
BACKOFF_SECONDS = (600, 1800, 3600, 7200, 21600)
MAX_PASSES = 4
POLL_SECONDS = 0.05
SETTLE_POLL_SECONDS = 0.25
# What the stability check watches. Directories count by inode only: our own renames change
# their mtime. config.inc.php is replaced by --config when given.
FINGERPRINT_FILES = (
    "program/include/iniset.php",
    "config/config.inc.php",
    "public_html/static.php",
    "skins/elastic/meta.json",
    "skins/elastic/styles/styles.less",
    "skins/elastic/templates/includes/footer.html",
)
FINGERPRINT_DIRS = ("program", "skins", "skins/elastic")
_LEFTOVER_STATE_RE = re.compile(r"^\.(last-good\.(new|old)-\d+|sync-state\.json\.\d+\.tmp)$")


class RefusedError(LumenError):
    exit_code = EXIT_REFUSED


def mem_available_mb(path: str = "/proc/meminfo") -> int | None:
    try:
        with open(path, encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def read_stamp(skin: Path) -> dict | None:
    try:
        data = json.loads((skin / STAMP_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def integrity_problems(skin: Path, limit: int = 5) -> list[str]:
    """Is the folder a complete build? Every file listed in the stamp exists with its hash."""
    if not skin.is_dir() or skin.is_symlink():
        return [f"{skin} is missing"]
    stamp = read_stamp(skin)
    if stamp is None:
        return [f"{skin / STAMP_NAME} is missing or unreadable"]
    files = stamp.get("files")
    if not isinstance(files, dict) or not files:
        return [f"{skin / STAMP_NAME} has no file list"]
    problems: list[str] = []
    for rel, digest in sorted(files.items()):
        if rel.startswith("/") or ".." in Path(rel).parts:
            problems.append(f"{STAMP_NAME} lists an unsafe path {rel!r}")
        else:
            try:
                if sha256_file(skin / rel) != digest:
                    problems.append(f"{rel} differs from the build")
            except OSError:
                problems.append(f"{rel} is missing")
        if len(problems) >= limit:
            break
    return problems


def describe(stamp: dict | None) -> str:
    if not stamp:
        return "no build"
    return (f"Lumen {stamp.get('lumen_version', '?')} for Roundcube {stamp.get('roundcube_version', '?')}, "
            f"built {stamp.get('built_at', '?')}")


@dataclass(frozen=True)
class Wanted:
    """What a current build must have been made from."""

    roundcube_version: str
    elastic_digest: str
    lumen_version: str
    source_digest: str
    palette: bool

    def key(self) -> str:
        return "|".join([self.roundcube_version, self.elastic_digest, self.lumen_version, self.source_digest,
                         str(self.palette)])


def stale_reasons(stamp: dict | None, want: Wanted) -> list[str]:
    if not stamp:
        return ["skins/lumen has no stamp"]
    reasons = []
    if stamp.get("roundcube_version") != want.roundcube_version:
        reasons.append(f"built for Roundcube {stamp.get('roundcube_version')}, installed is {want.roundcube_version}")
    if stamp.get("elastic_digest") != want.elastic_digest:
        reasons.append("the Elastic sources changed since the build")
    if stamp.get("lumen_version") != want.lumen_version:
        reasons.append(f"built by lumen-mail {stamp.get('lumen_version')}, the sources are {want.lumen_version}")
    elif stamp.get("source_digest") != want.source_digest:
        if bool(stamp.get("palette")) != want.palette:
            reasons.append("the command palette bundle was " + ("added" if want.palette else "removed"))
        else:
            reasons.append("the lumen-mail sources changed since the build")
    return reasons


@dataclass
class Lifecycle:
    roundcube: Path
    state: StatePaths
    sources: Sources
    log: Log = field(default_factory=Log)
    owner_spec: str = "auto"
    keep: int = 5
    dry_run: bool = False
    palette: str = "auto"                 # "auto": use the bundle when present; "require"; "none"
    compiler: str | None = None
    node: str | None = None
    work_dir: Path | None = None          # the build's temporary mirror tree (default: $TMPDIR)
    lock_timeout: float = 30.0
    wait: float = 300.0                   # how long sync waits for a complete Roundcube tree
    settle: float = 5.0                   # quiet seconds before a rebuild
    min_available_mb: int = 400           # MemAvailable needed before the compiler starts (0: off)
    config: Path | None = None            # config.inc.php (default <roundcube>/config/config.inc.php)
    prog: str = ""
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], _dt.datetime] = lambda: _dt.datetime.now(_dt.timezone.utc)
    meminfo: Callable[[], int | None] = mem_available_mb
    _owner: tuple[int, int] | None | str = field(default="unset", repr=False)

    # ------------------------------------------------------------------ paths and facts
    @property
    def skins_dir(self) -> Path:
        return self.roundcube / "skins"

    @property
    def skin_dir(self) -> Path:
        return self.skins_dir / SKIN_NAME

    @property
    def scratch(self) -> Path:
        return self.roundcube / SCRATCH_NAME

    @property
    def config_path(self) -> Path:
        return self.config or self.roundcube / "config" / "config.inc.php"

    def owner(self) -> tuple[int, int] | None:
        if self._owner == "unset":
            self._owner = resolve_owner(self.owner_spec, self.skins_dir)
        return self._owner  # type: ignore[return-value]

    def command(self, *args: str) -> str:
        prog = self.prog or os.environ.get("LUMEN_MAIL_PROG") or \
            f"PYTHONPATH={shlex.quote(str(PACKAGE_DIR.parent))} python3 -m lumen_mail"
        parts = [prog, *args, "--roundcube", shlex.quote(str(self.roundcube))]
        if self.state.root != DEFAULT_STATE_DIR:
            parts += ["--state-dir", shlex.quote(str(self.state.root))]
        return " ".join(parts)

    def extracted(self) -> bool:
        """The Roundcube tree is there again (enough to restore a build into it)."""
        return ((self.roundcube / "program" / "include" / "iniset.php").is_file()
                and (self.skins_dir / "elastic" / "meta.json").is_file())

    def fingerprint(self) -> tuple:
        out: list = []
        for rel in FINGERPRINT_FILES:
            path = self.config_path if rel == "config/config.inc.php" else self.roundcube / rel
            try:
                st = os.stat(path)
                out.append((st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
            except OSError:
                out.append(None)
        for rel in FINGERPRINT_DIRS:
            try:
                out.append(os.stat(self.roundcube / rel).st_ino)
            except OSError:
                out.append(None)
        return tuple(out)

    def palette_wanted(self) -> bool:
        if self.palette == "none":
            return False
        if self.palette == "require":
            if not self.sources.palette.is_file():
                raise LumenError(f"the command palette bundle {self.sources.palette} is missing")
            return True
        return self.sources.palette.is_file()

    def wanted(self, rc: Roundcube) -> Wanted:
        palette = self.palette_wanted()
        return Wanted(rc.version(), rc.elastic_digest(), self.sources.version, self.sources.digest(palette), palette)

    def last_good_ok(self) -> bool:
        return self.state.last_good.is_dir() and not integrity_problems(self.state.last_good)

    # ------------------------------------------------------------------ writing helpers
    def ensure_state_root(self) -> None:
        root = self.state.root
        created = not root.exists()
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LumenError(f"cannot create the state folder {root}: {exc.strerror}",
                             ["run as root once (install), or pass --state-dir"]) from exc
        if created:
            os.chmod(root, 0o750)
        owner = self.owner()
        if owner and (root.stat().st_uid, root.stat().st_gid) != owner:
            os.chown(root, *owner)

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        self.ensure_state_root()
        with locked(self.state.lock, self.lock_timeout):
            with contextlib.suppress(OSError):
                chown_path(self.state.lock, self.owner())
            yield

    def cleanup_leftovers(self) -> None:
        """Remove what an interrupted run left behind (only while holding the lock)."""
        if self.scratch.is_dir():
            for child in sorted(self.scratch.iterdir()):
                self.log.notice(f"removing {child}, left over from an interrupted run")
                remove_tree(child)
            with contextlib.suppress(OSError):
                self.scratch.rmdir()
        if self.state.root.is_dir():
            for child in self.state.root.iterdir():
                if _LEFTOVER_STATE_RE.match(child.name):
                    remove_tree(child)

    def new_run_dir(self) -> Path:
        self.scratch.mkdir(mode=0o700, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="run-", dir=self.scratch))

    def finish_run(self, run: Path) -> None:
        remove_tree(run)
        with contextlib.suppress(OSError):
            self.scratch.rmdir()

    def backup(self, tree: Path, reason: str) -> Path:
        self.ensure_state_root()
        dest = self.state.backups / stamp_name(self.now(), reason) / SKIN_NAME
        move_tree(tree, dest)
        owner = self.owner()
        if owner:
            set_tree_modes(dest.parent, owner)
            chown_path(self.state.backups, owner)
        rotate_backups(self.state.backups, self.keep)
        return dest

    def put_in_place(self, staged: Path, reason: str) -> Path | None:
        """Swap ``staged`` into skins/lumen; the previous folder goes to the backups."""
        set_tree_modes(staged, self.owner())
        old = swap_in(staged, self.skin_dir)
        if old is None:
            return None
        try:
            return self.backup(old, reason)
        except OSError as exc:
            self.log.warning(f"could not keep the replaced skins/lumen as a backup: {exc}")
            return None

    def save_last_good(self, tree: Path) -> None:
        self.ensure_state_root()
        pid = os.getpid()
        tmp = self.state.root / f".last-good.new-{pid}"
        remove_tree(tmp)
        copy_tree(tree, tmp)
        set_tree_modes(tmp, self.owner())
        target = self.state.last_good
        if not os.path.lexists(target):
            os.rename(tmp, target)
        elif exchange(tmp, target):
            remove_tree(tmp)
        else:
            old = self.state.root / f".last-good.old-{pid}"
            os.rename(target, old)
            os.rename(tmp, target)
            remove_tree(old)

    def build_staged(self, rc: Roundcube, run: Path, palette: bool) -> Path:
        out = run / SKIN_NAME
        build(BuildOptions(roundcube=rc.root, out=out, sources=self.sources, palette=palette,
                           compiler=self.compiler, node=self.node,
                           work_dir=self.work_dir or Path(tempfile.gettempdir()), quiet=not self.log.verbose))
        return out

    def restore_last_good(self) -> float:
        start = self.clock()
        run = self.new_run_dir()
        try:
            staged = run / SKIN_NAME
            copy_tree(self.state.last_good, staged)
            self.put_in_place(staged, "replaced-broken")
        finally:
            self.finish_run(run)
        return self.clock() - start

    def restore_with_retry(self, deadline: float) -> float | None:
        """Restore; retry while skins/ is not writable yet (KeyHelp's chown -R still pending)."""
        last: OSError | None = None
        while True:
            try:
                seconds = self.restore_last_good()
                self.log.notice(f"restored skins/lumen from the last good build in {seconds:.3f} s "
                                f"({describe(read_stamp(self.skin_dir))})")
                return seconds
            except (PermissionError, FileNotFoundError) as exc:
                last = exc
            if self.clock() >= deadline:
                self.log.error(f"could not restore skins/lumen: {last}")
                return None
            self.sleep(0.2)

    def write_notes(self, text: str) -> None:
        self.ensure_state_root()
        path = self.state.rollback_notes
        path.write_text(text, encoding="utf-8")
        os.chmod(path, 0o644)
        with contextlib.suppress(OSError):
            chown_path(path, self.owner())

    def undo_notes(self, backup: Path | None) -> str:
        lines = ["Undo:"]
        if backup is not None:
            lines.append(f"  {self.command('rollback')}")
            lines.append(f"      puts the previous build back ({backup.parent.name}) and holds it")
        lines += [
            "  Back to Elastic: select Elastic as the system skin first (KeyHelp: Configuration -> Webmail ->",
            "  Interface skin; elsewhere $config['skin'] = 'elastic';), then",
            f"  {self.command('uninstall')}",
        ]
        if backup is not None:
            lines += ["  Without lumen-mail (as root):",
                      f"  mv {shlex.quote(str(self.skin_dir))} {shlex.quote(str(self.state.root))}/lumen.replaced && "
                      f"cp -a {shlex.quote(str(backup))} {shlex.quote(str(self.skin_dir))}"]
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------ install
    def install(self, from_dir: Path | None = None, allow_mismatch: bool = False) -> int:
        rc = Roundcube.at(self.roundcube)
        palette = self.palette_wanted() if from_dir is None else False
        current = read_stamp(self.skin_dir)
        if self.dry_run:
            if from_dir is None:
                check_drift(rc, self.sources)
                what = f"build Lumen {self.sources.version} against Roundcube {rc.version()} at {rc.root}" \
                       f" ({'with' if palette else 'without'} the command palette)"
            else:
                problems = verify(from_dir, rc, None, exact=not allow_mismatch)
                for p in problems:
                    self.log.warning(f"{from_dir}: {p}")
                what = f"copy {from_dir} ({describe(read_stamp(from_dir))})"
            owner = self.owner()
            print(f"dry run: would {what}")
            print(f"dry run: would put it at {self.skin_dir} with one rename"
                  + (f", moving the current build ({describe(current)}) to {self.state.backups}/" if current or
                     os.path.lexists(self.skin_dir) else ""))
            print(f"dry run: folders 755, files 644, owner {':'.join(map(str, owner)) if owner else 'unchanged'}")
            print(f"dry run: would save the last good copy in {self.state.last_good} and keep {self.keep} backups")
            return EXIT_OK
        with self.lock():
            self.cleanup_leftovers()
            run = self.new_run_dir()
            try:
                if from_dir is not None:
                    staged = run / SKIN_NAME
                    copy_tree(from_dir, staged)
                    problems = verify(staged, rc, None, exact=not allow_mismatch)
                    if problems:
                        raise LumenError(f"{from_dir} does not pass verify against {rc.root}", problems)
                else:
                    staged = self.build_staged(rc, run, palette)
                backup = self.put_in_place(staged, "replaced-install")
                self.save_last_good(self.skin_dir)
            finally:
                self.finish_run(run)
            state = SyncState.load(self.state)
            state.failure = state.deferred = state.hold = None
            state.uninstalled = None
            state.save(self.state, self.owner())
            with contextlib.suppress(FileNotFoundError):
                self.state.rebuild_request.unlink()
            notes = self.undo_notes(backup)
            self.write_notes(notes)
        problems = verify(self.skin_dir, rc, None if from_dir else self.sources, exact=not allow_mismatch)
        if problems:
            self.log.error("the installed skins/lumen does not pass verify:\n" + "\n".join(f"  - {p}" for p in problems))
            print(notes, end="")
            return EXIT_ERROR
        self.log.notice(f"installed {self.skin_dir} ({describe(read_stamp(self.skin_dir))})")
        if backup:
            self.log.notice(f"the previous build is in {backup}")
        print(notes, end="")
        return EXIT_OK

    # ------------------------------------------------------------------ check / status
    def check(self) -> tuple[int, dict]:
        report: dict = {"roundcube": str(self.roundcube), "skin": str(self.skin_dir), "state": str(self.state.root)}
        if not self.roundcube.is_dir():
            raise LumenError(f"{self.roundcube} does not exist (--roundcube)")
        state = SyncState.load(self.state)
        reasons: list[str] = []
        if not self.extracted():
            reasons.append("the Roundcube tree is incomplete (an update may be running)")
            report.update(status="sync-needed", reasons=reasons)
            return EXIT_SYNC_NEEDED, report
        skin_problems = integrity_problems(self.skin_dir)
        last_good = self.state.last_good.is_dir()
        if skin_problems and not os.path.lexists(self.skin_dir) and not last_good:
            report.update(status="not-installed", reasons=["no skins/lumen and no last good build"])
            return EXIT_NOT_INSTALLED, report
        stamp = read_stamp(self.skin_dir)
        report["installed"] = describe(stamp) if not skin_problems else None
        if skin_problems:
            reasons += [f"skins/lumen: {p}" for p in skin_problems]
        else:
            rc = Roundcube.at(self.roundcube)
            want = self.wanted(rc)
            report["roundcube_version"] = want.roundcube_version
            if state.hold:
                report["hold"] = state.hold
            else:
                reasons += stale_reasons(stamp, want)
            if not self.last_good_ok() or read_stamp(self.state.last_good) != stamp:
                reasons.append("the last good copy is missing or differs from skins/lumen")
        if self.state.rebuild_request.exists() and not state.hold:
            reasons.append("a rebuild was requested")
        if state.failure:
            report["last_failure"] = {k: state.failure.get(k) for k in ("attempts", "last_attempt", "next_attempt",
                                                                          "error", "exit_code")}
        if state.deferred:
            report["deferred"] = state.deferred
        report["reasons"] = reasons
        report["status"] = "ok" if not reasons else "sync-needed"
        return (EXIT_OK if not reasons else EXIT_SYNC_NEEDED), report

    def status(self) -> dict:
        info: dict = {"roundcube": str(self.roundcube), "state": str(self.state.root),
                      "sources": str(self.sources.root)}
        try:
            info["lumen_mail_version"] = self.sources.version
        except LumenError as exc:
            info["lumen_mail_version"] = f"unknown ({exc})"
        try:
            info["roundcube_version"] = Roundcube.at(self.roundcube).version()
        except LumenError:
            info["roundcube_version"] = None
        try:
            skin = system_skin(self.roundcube, self.config)
            info["system_skin"] = skin.printable if skin.certain else f"{skin.printable} (uncertain)"
        except OSError as exc:
            info["system_skin"] = f"unknown (cannot read {self.config_path}: {exc.strerror})"
        problems = integrity_problems(self.skin_dir)
        info["skin"] = {"path": str(self.skin_dir), "intact": not problems,
                        "build": describe(read_stamp(self.skin_dir)) if not problems else None,
                        "problems": problems}
        lg_problems = integrity_problems(self.state.last_good) if self.state.last_good.exists() else ["missing"]
        info["last_good"] = {"path": str(self.state.last_good), "intact": not lg_problems,
                             "build": describe(read_stamp(self.state.last_good)) if not lg_problems else None}
        info["backups"] = [p.name for p in list_backups(self.state.backups)]
        state = SyncState.load(self.state)
        info["sync_state"] = {"failure": state.failure, "deferred": state.deferred, "hold": state.hold,
                              "uninstalled": state.uninstalled,
                              "rebuild_requested": self.state.rebuild_request.exists()}
        try:
            code, report = self.check()
            info["check"] = {"exit_code": code, "status": report.get("status"), "reasons": report.get("reasons", [])}
        except LumenError as exc:
            info["check"] = {"exit_code": exc.exit_code, "status": "error", "reasons": [str(exc)]}
        return info

    # ------------------------------------------------------------------ sync
    def sync(self, rebuild: bool = False) -> int:
        if self.dry_run:
            return self._sync_dry_run(rebuild)
        if not self.roundcube.is_dir():
            raise LumenError(f"{self.roundcube} does not exist (--roundcube)")
        with self.lock():
            self.cleanup_leftovers()
            code = EXIT_OK
            for _ in range(MAX_PASSES):
                before = self.fingerprint()
                code = self._sync_pass(rebuild)
                rebuild = False
                if code != EXIT_OK or self.fingerprint() == before:
                    return code
                self.log.info("the Roundcube tree changed during this run; checking again")
            return code

    def _sync_dry_run(self, rebuild: bool) -> int:
        code, report = self.check()
        if rebuild and code == EXIT_OK:
            code, report["reasons"] = EXIT_SYNC_NEEDED, ["a rebuild was requested (--rebuild)"]
        if code == EXIT_OK:
            print("dry run: nothing to do; skins/lumen is current")
        elif code == EXIT_NOT_INSTALLED:
            print("dry run: nothing to do; Lumen is not installed here")
        else:
            for reason in report.get("reasons", []):
                print(f"dry run: {reason}")
            if integrity_problems(self.skin_dir) and self.last_good_ok():
                print(f"dry run: would restore skins/lumen from {self.state.last_good} "
                      f"({describe(read_stamp(self.state.last_good))})")
            print("dry run: would rebuild if the stamp is stale (after the tree is quiet for "
                  f"{self.settle:g} s and with at least {self.min_available_mb} MB of memory available)")
        return EXIT_OK

    def _wait_until(self, condition: Callable[[], bool], deadline: float) -> bool:
        while not condition():
            if self.clock() >= deadline:
                return False
            self.sleep(POLL_SECONDS)
        return True

    def _wait_settled(self, deadline: float) -> bool:
        """Wait until the watched files have not changed for ``settle`` seconds. A skins/lumen that
        disappears meanwhile (the update is still running) is restored again at once."""
        last = self.fingerprint()
        since = self.clock()
        while True:
            if (self.extracted() and not (self.skin_dir / STAMP_NAME).is_file() and self.last_good_ok()):
                if self.restore_with_retry(deadline) is None:
                    return False
            if self.clock() - since >= self.settle and self.extracted():
                return True
            if self.clock() >= deadline:
                return False
            self.sleep(SETTLE_POLL_SECONDS)
            current = self.fingerprint()
            if current != last:
                last, since = current, self.clock()

    def _sync_pass(self, force: bool) -> int:
        state = SyncState.load(self.state)
        deadline = self.clock() + self.wait
        if not self._wait_until(self.extracted, deadline):
            self.log.warning(f"the Roundcube tree at {self.roundcube} is still incomplete after {self.wait:g} s "
                             "(program/include/iniset.php or skins/elastic/meta.json missing); next run checks again")
            return EXIT_TEMPFAIL
        skin_problems = integrity_problems(self.skin_dir)
        if skin_problems:
            if self.last_good_ok():
                if self.restore_with_retry(deadline) is None:
                    return EXIT_TEMPFAIL
                skin_problems = []
            elif state.uninstalled or (not os.path.lexists(self.skin_dir) and not self.state.last_good.exists()):
                self.log.info("Lumen is not installed here (no skins/lumen and no last good build); nothing to do")
                return EXIT_OK
            else:
                self.log.warning("skins/lumen is missing or damaged and the last good build cannot be used: "
                                 + "; ".join(skin_problems + integrity_problems(self.state.last_good, limit=2)))
        elif state.uninstalled and not self.state.last_good.exists():
            self.log.info("skins/lumen is back after an uninstall; run install to manage it again")
            return EXIT_OK
        if state.hold and not skin_problems:
            self.log.info(f"a rollback holds the current build ({describe(read_stamp(self.skin_dir))}); "
                          "rebuilds resume after install or resume")
            return EXIT_OK
        rc = Roundcube.at(self.roundcube)
        want = self.wanted(rc)
        stamp = read_stamp(self.skin_dir) if not skin_problems else None
        reasons = ["skins/lumen is damaged"] if skin_problems else stale_reasons(stamp, want)
        if force:
            reasons.append("a rebuild was requested (--rebuild)")
        if self.state.rebuild_request.exists():
            reasons.append("a rebuild was requested (request-rebuild)")
        if not reasons:
            self._adopt_or_refresh_last_good(rc, stamp)
            if state.failure or state.deferred:
                state.failure = state.deferred = None
                state.save(self.state, self.owner())
            self.log.info(f"skins/lumen is current ({describe(stamp)})")
            return EXIT_OK
        return self._rebuild(state, reasons, deadline, forced=force or self.state.rebuild_request.exists())

    def _adopt_or_refresh_last_good(self, rc: Roundcube, stamp: dict | None) -> None:
        if self.last_good_ok() and read_stamp(self.state.last_good) == stamp:
            return
        problems = verify(self.skin_dir, rc, self.sources)
        if problems:
            self.log.warning("skins/lumen is current but does not pass verify, so it is not saved as the last good "
                             "build: " + "; ".join(problems[:5]))
            return
        self.save_last_good(self.skin_dir)
        self.log.notice(f"saved skins/lumen as the last good build ({describe(stamp)})")

    def _blocked(self, state: SyncState, want: Wanted, forced: bool) -> bool:
        """True (and logged) when the back-off or the memory check holds the rebuild back."""
        now = self.now()
        if state.failure and state.failure.get("key") == want.key() and not forced:
            next_attempt = parse_iso(state.failure.get("next_attempt"))
            if next_attempt and now < next_attempt:
                self.log.info(f"the last rebuild for these inputs failed; the next attempt is after {iso(next_attempt)}")
                return True
        available = self.meminfo()
        if self.min_available_mb and available is not None and available < self.min_available_mb:
            reason = (f"only {available} MB of memory available, the compile needs {self.min_available_mb} MB; "
                      "the active build stays")
            first = (state.deferred or {}).get("kind") != "memory"
            state.deferred = {"kind": "memory", "reason": reason,
                              "since": iso(now) if first else (state.deferred or {}).get("since")}
            state.save(self.state, self.owner())
            self.log.emit("notice" if first else "info", f"rebuild deferred: {reason}")
            return True
        return False

    def _rebuild(self, state: SyncState, reasons: list[str], deadline: float, forced: bool) -> int:
        self.log.info("rebuild needed: " + "; ".join(reasons))
        # Cheap checks first: a deferred or backed-off rebuild must not hold the lock while settling.
        if self._blocked(state, self.wanted(Roundcube.at(self.roundcube)), forced):
            return EXIT_TEMPFAIL
        if not self._wait_settled(deadline):
            self.log.warning(f"the Roundcube tree at {self.roundcube} kept changing for {self.wait:g} s; "
                             "the rebuild waits for the next run")
            return EXIT_TEMPFAIL
        rc = Roundcube.at(self.roundcube)
        want = self.wanted(rc)
        key = want.key()
        if self._blocked(state, want, forced):
            return EXIT_TEMPFAIL
        start = self.clock()
        inputs = (want.roundcube_version, want.elastic_digest)
        run = self.new_run_dir()
        try:
            try:
                staged = self.build_staged(rc, run, want.palette)
            except (LumenError, OSError) as exc:
                error = exc if isinstance(exc, LumenError) else LumenError(f"the build stopped: {exc}")
                self._record_failure(state, key, error)
                return error.exit_code
            try:
                after = Roundcube.at(self.roundcube)
                changed = (after.version(), after.elastic_digest()) != inputs
            except LumenError:
                changed = True
            if changed:
                self.log.notice("Roundcube changed while the skin was being built; the build is discarded and the "
                                "next run starts again")
                return EXIT_TEMPFAIL
            backup = self.put_in_place(staged, "replaced-stale")
            self.save_last_good(self.skin_dir)
        finally:
            self.finish_run(run)
        state.failure = state.deferred = None
        state.save(self.state, self.owner())
        with contextlib.suppress(FileNotFoundError):
            self.state.rebuild_request.unlink()
        where = f"; the previous build is in {backup}" if backup else ""
        self.log.notice(f"rebuilt skins/lumen for Roundcube {want.roundcube_version} (Lumen {want.lumen_version}) "
                        f"in {self.clock() - start:.1f} s{where}")
        return EXIT_OK

    def _record_failure(self, state: SyncState, key: str, exc: LumenError) -> None:
        previous = state.failure if state.failure and state.failure.get("key") == key else {}
        attempts = int(previous.get("attempts", 0)) + 1
        delay = BACKOFF_SECONDS[min(attempts, len(BACKOFF_SECONDS)) - 1]
        now = self.now()
        next_attempt = now + _dt.timedelta(seconds=delay)
        state.failure = {"key": key, "attempts": attempts, "last_attempt": iso(now), "next_attempt": iso(next_attempt),
                         "error": str(exc), "details": exc.details[:20], "exit_code": exc.exit_code}
        state.deferred = None
        state.save(self.state, self.owner())
        active = describe(read_stamp(self.skin_dir)) if not integrity_problems(self.skin_dir) else "none"
        lines = [f"rebuild failed (exit {exc.exit_code}): {exc}"] + [f"  - {d}" for d in exc.details[:20]]
        lines.append(f"skins/lumen keeps the active build ({active}); attempt {attempts}, the next one is after "
                     f"{iso(next_attempt)} or as soon as the inputs change")
        self.log.error("\n".join(lines))

    # ------------------------------------------------------------------ rollback / resume / request
    def rollback(self, name: str | None = None) -> int:
        candidates = [b for b in list_backups(self.state.backups) if not integrity_problems(b / SKIN_NAME)]
        if name:
            candidates = [b for b in candidates if b.name == name]
        if not candidates:
            raise LumenError("no intact backup to roll back to" + (f" named {name}" if name else ""),
                             [f"backups: {self.state.backups}"])
        chosen = candidates[-1]
        stamp = read_stamp(chosen / SKIN_NAME)
        if self.dry_run:
            print(f"dry run: would put {chosen / SKIN_NAME} ({describe(stamp)}) at {self.skin_dir} and hold it")
            return EXIT_OK
        with self.lock():
            self.cleanup_leftovers()
            run = self.new_run_dir()
            try:
                staged = run / SKIN_NAME
                copy_tree(chosen / SKIN_NAME, staged)
                backup = self.put_in_place(staged, "replaced-rollback")
                self.save_last_good(self.skin_dir)
            finally:
                self.finish_run(run)
            state = SyncState.load(self.state)
            state.hold = {"since": iso(self.now()), "backup": chosen.name}
            state.failure = state.deferred = None
            state.save(self.state, self.owner())
            self.write_notes(self.undo_notes(backup))
        self.log.notice(f"rolled back skins/lumen to {chosen.name} ({describe(stamp)})")
        self.log.notice(f"sync keeps this build (restores it, does not rebuild) until: {self.command('resume')}")
        return EXIT_OK

    def resume(self) -> int:
        if self.dry_run:
            print("dry run: would clear the hold so that sync rebuilds again")
            return EXIT_OK
        with self.lock():
            state = SyncState.load(self.state)
            had = state.hold
            state.hold = None
            state.save(self.state, self.owner())
        self.log.notice("automatic rebuilds resumed" if had else "there was no hold; nothing changed")
        return EXIT_OK

    def request_rebuild(self) -> int:
        if self.dry_run:
            print(f"dry run: would create {self.state.rebuild_request}")
            return EXIT_OK
        with self.lock():
            self.state.rebuild_request.write_text(iso(self.now()) + "\n", encoding="utf-8")
            with contextlib.suppress(OSError):
                chown_path(self.state.rebuild_request, self.owner())
        self.log.notice("the next sync run rebuilds skins/lumen (systemctl start lumen-mail-sync.service runs it now)")
        return EXIT_OK

    # ------------------------------------------------------------------ uninstall
    def uninstall(self, force: bool = False) -> int:
        blocked = None
        try:
            skin = system_skin(self.roundcube, self.config)
            if not skin.certain:
                blocked = (f"cannot tell the system skin from {skin.source}: the 'skin' setting is not a plain "
                           "string assignment that lumen-mail can read")
            elif skin.value == SKIN_NAME:
                blocked = "the configured system skin is lumen; without skins/lumen every webmail page would fail"
        except OSError as exc:
            blocked = f"cannot read {self.config_path} to confirm that the system skin is not lumen ({exc.strerror})"
        if blocked:
            if not force:
                raise RefusedError(blocked, ["select another system skin first (KeyHelp: Configuration -> Webmail -> "
                                             "Interface skin; elsewhere $config['skin'] = 'elastic';)",
                                             "or pass --force if you know what you are doing"])
            self.log.warning(f"{blocked} (continuing because of --force)")
        present = os.path.lexists(self.skin_dir)
        has_last_good = self.state.last_good.exists()
        if not present and not has_last_good:
            self.log.notice("Lumen is not installed here; nothing to remove")
            return EXIT_OK
        if self.dry_run:
            print(f"dry run: would move {self.skin_dir if present else self.state.last_good} to "
                  f"{self.state.backups}/<time>-uninstall/ and stop sync from restoring it")
            return EXIT_OK
        with self.lock():
            self.cleanup_leftovers()
            dest = self.state.backups / stamp_name(self.now(), "uninstall") / SKIN_NAME
            if present:
                move_tree(self.skin_dir, dest)
                if has_last_good:
                    remove_tree(self.state.last_good)
            else:
                move_tree(self.state.last_good, dest)
            owner = self.owner()
            if owner:
                set_tree_modes(dest.parent, owner)
            state = SyncState.load(self.state)
            state.uninstalled = iso(self.now())
            state.failure = state.deferred = state.hold = None
            state.save(self.state, owner)
            with contextlib.suppress(FileNotFoundError):
                self.state.rebuild_request.unlink()
            rotate_backups(self.state.backups, max(self.keep, 1))
            self.write_notes(f"Undo the uninstall:\n  {self.command('install')}\n"
                             f"  or copy the removed build back: cp -a {shlex.quote(str(dest))} "
                             f"{shlex.quote(str(self.skin_dir))}\n")
        self.log.notice(f"removed skins/lumen; the build is kept in {dest}")
        self.log.warning("users who chose Lumen in Settings -> Preferences -> User Interface now get the system skin")
        print("Stop the sync units as well: systemctl disable --now lumen-mail-sync.path lumen-mail-sync.timer")
        return EXIT_OK

