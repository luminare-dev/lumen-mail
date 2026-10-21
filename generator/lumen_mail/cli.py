"""Command line: python3 -m lumen_mail <command> ... (or <prefix>/bin/lumen-mail <command> ...)

Commands: build, verify, install, check, sync, status, rollback, resume, request-rebuild,
uninstall, install-runtime. docs/cli.md describes every option.

Exit codes:
   0  ok (check: everything current)
   1  error (sync: the rebuild failed, the active build stays)
   2  usage
   3  Elastic drift: the installed Elastic lacks a file, marker or variable Lumen relies on
   4  LESS compile error
   5  refused (uninstall while the system skin is lumen; install-runtime over a foreign folder)
   6  not installed (check)
  10  sync needed (check)
  75  try again later: another run holds the lock, the Roundcube tree is incomplete, too little
      memory for the compile, or back-off after a failed rebuild (the sync unit treats 75 as success;
      while webmail is down because the system skin is lumen and no usable skins/lumen exists,
      sync exits 1 instead)

Run as root, every command except verify and install-runtime continues as the Roundcube owner
(privileges.py): the owner of <roundcube>/skins, or --owner.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable

from . import privileges
from .build import BuildOptions, build
from .fsops import resolve_owner
from .lifecycle import DEFAULT_MIN_AVAILABLE_MB, EXIT_SYNC_NEEDED, Lifecycle
from .log import Log
from .roundcube import Roundcube
from .runtime import DEFAULT_PREFIX, install_runtime
from .sources import Sources
from .state import BusyError, StatePaths
from .util import LumenError
from .verify import verify

Command = Callable[[argparse.Namespace], int]
Configure = Callable[[argparse.ArgumentParser], None]
COMMANDS: dict[str, tuple[Command, Configure, str]] = {}


def register(name: str, fn: Command, configure: Configure, help_text: str) -> None:
    COMMANDS[name] = (fn, configure, help_text)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def add_source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--source", help="lumen-mail sources (default: this checkout or runtime, or $LUMEN_MAIL_SOURCE)")
    p.add_argument("--node-modules", help="node_modules with less and clean-css (default: <source>/node_modules)")


def add_palette_args(p: argparse.ArgumentParser) -> None:
    # Every build includes the command palette; there is deliberately no option to leave it out.
    p.add_argument("--palette", help="the built command palette (default: <source>/palette/dist/lumen-palette.js, "
                                     "or $LUMEN_MAIL_PALETTE)")


def add_common(p: argparse.ArgumentParser, roundcube: bool = True) -> None:
    if roundcube:
        p.add_argument("--roundcube", default=os.environ.get("LUMEN_MAIL_ROUNDCUBE"),
                       help="Roundcube root, the folder with program/ and skins/ ($LUMEN_MAIL_ROUNDCUBE)")
    p.add_argument("--state-dir", help="state folder (default $LUMEN_MAIL_STATE_DIR, $STATE_DIRECTORY or "
                                       "/var/lib/lumen-mail)")
    add_source_args(p)
    p.add_argument("-q", "--quiet", action="store_true", help="only warnings and errors")
    p.add_argument("-v", "--verbose", action="store_true", help="also debug messages and compiler output")


OWNER_HELP = ("as root: the user this command continues as, and so the owner of every file it writes: 'auto' "
              "(the owner of <roundcube>/skins; refused if that is root), 'user:group', or '' to stay root and "
              "change no owner ($LUMEN_MAIL_OWNER)")


def add_owner(p: argparse.ArgumentParser) -> None:
    p.add_argument("--owner", default=os.environ.get("LUMEN_MAIL_OWNER", "auto"), help=OWNER_HELP)


def add_writer(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true", help="show what would happen; write nothing")
    add_owner(p)
    p.add_argument("--keep", type=int, default=5, help="backups to keep (default 5)")
    p.add_argument("--lock-timeout", type=float, default=env_float("LUMEN_MAIL_LOCK_TIMEOUT", 30.0),
                   help="seconds to wait for another run to finish (default 30), then exit 75")


def add_builder(p: argparse.ArgumentParser) -> None:
    add_palette_args(p)
    p.add_argument("--compiler", help="compiler command speaking compile.mjs's protocol (tests; $LUMEN_MAIL_COMPILER)")
    p.add_argument("--node", help="node binary (default: node from PATH, or $LUMEN_MAIL_NODE)")
    p.add_argument("--work-dir", help="where the build's temporary mirror tree goes (default: $TMPDIR)")


SOURCES_HINT = ["run the installed runtime (/opt/lumen-mail/bin/lumen-mail, see install-runtime), whose files every "
                "user can read, or pass --source with such a folder"]


def sources_from(args: argparse.Namespace) -> Sources:
    try:
        sources = Sources.locate(getattr(args, "source", None), getattr(args, "node_modules", None),
                                 getattr(args, "palette", None))
    except PermissionError as exc:
        raise LumenError(f"cannot read the lumen-mail sources as {privileges.user_name(os.geteuid())}: {exc}",
                         SOURCES_HINT) from exc
    # After a drop from root the sources may be out of reach (a checkout in /root): say so at once.
    version = sources.root / "version.txt"
    if not os.access(version, os.R_OK) and (not os.access(sources.root, os.X_OK) or os.path.lexists(version)):
        raise LumenError(f"cannot read the lumen-mail sources in {sources.root} as "
                         f"{privileges.user_name(os.geteuid())}", SOURCES_HINT)
    return sources


# Commands that continue as the Roundcube owner when started as root, and those among them that
# write (they refuse a tree that belongs to root and prepare the state folder first).
AS_OWNER = {"build", "install", "check", "sync", "status", "rollback", "resume", "request-rebuild", "uninstall"}
WRITERS = {"install", "sync", "rollback", "resume", "request-rebuild", "uninstall"}


def continue_as_owner(args: argparse.Namespace) -> None:
    """Started as root: prepare the state folder, then drop to the Roundcube owner (privileges.py)."""
    if os.geteuid() != 0 or args.command not in AS_OWNER or not getattr(args, "roundcube", None):
        return
    writer = args.command in WRITERS
    owner = privileges.target_owner(Path(args.roundcube).absolute(), getattr(args, "owner", "auto"), strict=writer)
    if owner is None:
        return
    if writer and not getattr(args, "dry_run", False):
        privileges.prepare_state_root(StatePaths.locate(args.state_dir).root, owner)
    privileges.drop_to(owner)
    # From here on every file is written by its owner: no chown.
    args.owner = ""


def lifecycle_from(args: argparse.Namespace) -> Lifecycle:
    if not getattr(args, "roundcube", None):
        raise UsageError("--roundcube is required (or set $LUMEN_MAIL_ROUNDCUBE)")
    return Lifecycle(
        roundcube=Path(args.roundcube).absolute(),
        state=StatePaths.locate(args.state_dir),
        sources=sources_from(args),
        log=Log(quiet=args.quiet, verbose=args.verbose),
        owner_spec=getattr(args, "owner", "auto"),
        keep=max(1, getattr(args, "keep", 5)),
        dry_run=getattr(args, "dry_run", False),
        compiler=getattr(args, "compiler", None),
        node=getattr(args, "node", None),
        work_dir=Path(args.work_dir) if getattr(args, "work_dir", None) else None,
        lock_timeout=getattr(args, "lock_timeout", 30.0),
        wait=getattr(args, "wait", 300.0),
        settle=getattr(args, "settle", 5.0),
        min_available_mb=getattr(args, "min_available_mb", DEFAULT_MIN_AVAILABLE_MB),
        config=Path(args.config) if getattr(args, "config", None) else None,
    )


class UsageError(LumenError):
    exit_code = 2


# ---------------------------------------------------------------------------- build / verify
def cmd_build(args: argparse.Namespace) -> int:
    result = build(BuildOptions(
        roundcube=Path(args.roundcube), out=Path(args.out), sources=sources_from(args),
        compiler=args.compiler, node=args.node,
        work_dir=Path(args.work_dir) if args.work_dir else None, quiet=args.quiet,
    ))
    if args.print_stamp:
        print(json.dumps(result.stamp, indent=2, sort_keys=True))
    return 0


def configure_build(p: argparse.ArgumentParser) -> None:
    p.add_argument("--roundcube", required=True, help="Roundcube root (the folder with program/ and skins/)")
    p.add_argument("--out", required=True, help="output folder for the skin (must not exist or be empty)")
    add_source_args(p)
    add_palette_args(p)
    p.add_argument("--compiler", help="compiler command speaking compile.mjs's protocol (tests; $LUMEN_MAIL_COMPILER)")
    p.add_argument("--node", help="node binary (default: node from PATH, or $LUMEN_MAIL_NODE)")
    p.add_argument("--work-dir", help="where the temporary mirror tree goes (default: next to --out)")
    p.add_argument("--print-stamp", action="store_true", help="print the stamp as JSON on stdout")
    add_owner(p)
    p.add_argument("-q", "--quiet", action="store_true")


def cmd_verify(args: argparse.Namespace) -> int:
    rc = Roundcube.at(args.roundcube)
    sources = None if args.no_source else sources_from(args)
    problems = verify(Path(args.skin), rc, sources=sources, exact=not args.allow_mismatch)
    for p in problems:
        print(f"FAIL {p}")
    if problems:
        print(f"{len(problems)} problem(s) in {args.skin}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"ok: {args.skin} is a valid Lumen build for Roundcube {rc.version()} at {rc.root}")
    return 0


def configure_verify(p: argparse.ArgumentParser) -> None:
    p.add_argument("skin", help="the skin folder (a build output or <roundcube>/skins/lumen)")
    p.add_argument("--roundcube", required=True, help="Roundcube root the skin is checked against")
    add_source_args(p)
    p.add_argument("--no-source", action="store_true", help="do not compare the stamp with the source version")
    p.add_argument("--allow-mismatch", action="store_true",
                   help="accept a build made for another release of Elastic (a release package)")
    p.add_argument("-q", "--quiet", action="store_true")


# ---------------------------------------------------------------------------- lifecycle
def cmd_install(args: argparse.Namespace) -> int:
    lc = lifecycle_from(args)
    return lc.install(from_dir=Path(args.from_dir).absolute() if args.from_dir else None,
                      allow_mismatch=args.allow_mismatch)


def configure_install(p: argparse.ArgumentParser) -> None:
    add_common(p)
    add_writer(p)
    add_builder(p)
    p.add_argument("--from", dest="from_dir", help="install this built skin folder (for example from a release "
                                                    "package) instead of building")
    p.add_argument("--allow-mismatch", action="store_true",
                   help="with --from: accept a build made for another release of the same Roundcube series")


def emit_report(args: argparse.Namespace, report: dict, lines: list[str]) -> None:
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.quiet:
        for line in lines:
            print(line)


def cmd_check(args: argparse.Namespace) -> int:
    lc = lifecycle_from(args)
    code, report = lc.check()
    report["exit_code"] = code
    head = {"ok": "ok: skins/lumen is current", "sync-needed": "sync needed",
            "not-installed": "not installed"}.get(report.get("status", ""), report.get("status", ""))
    if report.get("installed"):
        head += f" ({report['installed']})"
    lines = [head] + [f"  - {r}" for r in report.get("reasons", [])]
    if report.get("hold"):
        lines.append(f"  held by a rollback since {report['hold'].get('since')} (resume clears it)")
    if report.get("last_failure"):
        f = report["last_failure"]
        lines.append(f"  last rebuild failed {f.get('last_attempt')} (attempt {f.get('attempts')}): {f.get('error')}")
    if report.get("deferred"):
        lines.append(f"  rebuild deferred: {deferral_text(report['deferred'])}")
    emit_report(args, report, lines)
    return code


def deferral_text(deferred: dict) -> str:
    kind = {"memory": "too little memory for the compile"}.get(deferred.get("kind", ""), deferred.get("kind", "?"))
    return f"{kind} since {deferred.get('since')}"


def add_config_arg(p: argparse.ArgumentParser, why: str) -> None:
    p.add_argument("--config", help=f"Roundcube config file, read only for its 'skin' setting ({why}; "
                                    "default <roundcube>/config/config.inc.php)")


def configure_check(p: argparse.ArgumentParser) -> None:
    add_common(p)
    add_owner(p)
    add_palette_args(p)
    add_config_arg(p, "a missing build is urgent when the system skin is lumen")
    p.add_argument("--json", action="store_true", help="print the report as JSON")


def cmd_sync(args: argparse.Namespace) -> int:
    return lifecycle_from(args).sync(rebuild=args.rebuild)


def configure_sync(p: argparse.ArgumentParser) -> None:
    add_common(p)
    add_writer(p)
    add_builder(p)
    add_config_arg(p, "with no build and no last good copy, sync builds one when the system skin is lumen")
    p.add_argument("--rebuild", action="store_true", help="rebuild even if the stamp is current")
    p.add_argument("--wait", type=float, default=env_float("LUMEN_MAIL_WAIT", 300.0),
                   help="seconds to wait for a complete Roundcube tree (default 300)")
    p.add_argument("--settle", type=float, default=env_float("LUMEN_MAIL_SETTLE", 5.0),
                   help="seconds the tree must be unchanged before a rebuild (default 5)")
    p.add_argument("--min-available-mb", type=int,
                   default=int(env_float("LUMEN_MAIL_MIN_AVAILABLE_MB", DEFAULT_MIN_AVAILABLE_MB)),
                   help=f"MemAvailable needed before the compiler starts (default {DEFAULT_MIN_AVAILABLE_MB}; 0 turns "
                        "the check off; while webmail is down a lower emergency floor applies)")


def cmd_status(args: argparse.Namespace) -> int:
    lc = lifecycle_from(args)
    info = lc.status()
    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0
    sk, lg, ss, ck = info["skin"], info["last_good"], info["sync_state"], info["check"]
    print(f"lumen-mail {info['lumen_mail_version']} (sources {info['sources']})")
    print(f"Roundcube:   {info['roundcube']} ({info['roundcube_version'] or 'incomplete or missing'})")
    print(f"System skin: {info['system_skin']}")
    print(f"skins/lumen: {sk['build'] if sk['intact'] else 'missing or damaged: ' + '; '.join(sk['problems'])}")
    print(f"Last good:   {lg['build'] if lg['intact'] else 'missing or damaged'} ({lg['path']})")
    print(f"Backups:     {len(info['backups'])}" + (f", newest {info['backups'][-1]}" if info["backups"] else ""))
    print(f"Check:       {ck['status']} (exit {ck['exit_code']})")
    for reason in ck["reasons"]:
        print(f"  - {reason}")
    if ss["hold"]:
        print(f"Hold:        since {ss['hold'].get('since')} (rollback to {ss['hold'].get('backup')})")
    if ss["failure"]:
        f = ss["failure"]
        print(f"Last failure: {f.get('last_attempt')}, attempt {f.get('attempts')}, exit {f.get('exit_code')}: "
              f"{f.get('error')}; next attempt after {f.get('next_attempt')}")
    if ss["deferred"]:
        print(f"Deferred:    {deferral_text(ss['deferred'])}")
    if ss["rebuild_requested"]:
        print("Rebuild:     requested; the next sync run rebuilds")
    if ss["uninstalled"]:
        print(f"Uninstalled: {ss['uninstalled']}")
    return 0


def configure_status(p: argparse.ArgumentParser) -> None:
    add_common(p)
    add_owner(p)
    add_palette_args(p)
    add_config_arg(p, "shown as the system skin")
    p.add_argument("--json", action="store_true", help="print the status as JSON")


def cmd_rollback(args: argparse.Namespace) -> int:
    return lifecycle_from(args).rollback(args.backup)


def configure_rollback(p: argparse.ArgumentParser) -> None:
    add_common(p)
    add_writer(p)
    p.add_argument("--backup", help="name of the backup folder (default: the newest intact one)")


def cmd_resume(args: argparse.Namespace) -> int:
    return lifecycle_from(args).resume()


def configure_resume(p: argparse.ArgumentParser) -> None:
    add_common(p)
    add_writer(p)


def cmd_request_rebuild(args: argparse.Namespace) -> int:
    return lifecycle_from(args).request_rebuild()


def cmd_uninstall(args: argparse.Namespace) -> int:
    return lifecycle_from(args).uninstall(force=args.force)


def configure_uninstall(p: argparse.ArgumentParser) -> None:
    add_common(p)
    add_writer(p)
    add_config_arg(p, "uninstall refuses while it is lumen")
    p.add_argument("--force", action="store_true", help="remove the skin even if the system skin is (or may be) lumen")


def cmd_install_runtime(args: argparse.Namespace) -> int:
    sources = sources_from(args)
    owner = resolve_owner(args.owner, Path("/")) if args.owner != "auto" else (0, 0)
    return install_runtime(sources, Path(args.prefix), Log(quiet=args.quiet, verbose=args.verbose),
                           dry_run=args.dry_run, force=args.force, python=args.python, owner=owner)


def configure_install_runtime(p: argparse.ArgumentParser) -> None:
    p.add_argument("--prefix", default=str(DEFAULT_PREFIX), help=f"where the runtime goes (default {DEFAULT_PREFIX})")
    add_source_args(p)
    add_palette_args(p)
    p.add_argument("--python", help="python3 the wrapper runs (default /usr/bin/python3)")
    p.add_argument("--owner", default="auto", help="owner of the files: 'auto' (root:root when run as root), "
                                                   "'user:group' or ''")
    p.add_argument("--force", action="store_true", help="replace a folder that is not a lumen-mail runtime")
    p.add_argument("--dry-run", action="store_true", help="show what would happen; write nothing")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")


register("build", cmd_build, configure_build, "assemble skins/lumen from our sources and the installed Elastic")
register("verify", cmd_verify, configure_verify, "check a built skin folder against a Roundcube installation")
register("install", cmd_install, configure_install,
         "build (or take --from), verify and swap skins/lumen in atomically; keep backups and a last good copy")
register("check", cmd_check, configure_check, "exit 0 if skins/lumen is current, 10 if sync has work to do")
register("sync", cmd_sync, configure_sync,
         "restore skins/lumen after a Roundcube update at once, then rebuild it if the stamp is stale")
register("status", cmd_status, configure_status, "show the installed build, the last good copy and the sync state")
register("rollback", cmd_rollback, configure_rollback,
         "put the newest (or a named) backup back and hold it until resume or install")
register("resume", cmd_resume, configure_resume, "clear the hold that rollback set")
register("request-rebuild", cmd_request_rebuild, configure_resume, "make the next sync run rebuild skins/lumen")
register("uninstall", cmd_uninstall, configure_uninstall,
         "move skins/lumen to the backups (refused while the system skin is lumen)")
register("install-runtime", cmd_install_runtime, configure_install_runtime,
         "copy what sync needs (generator, sources, compiler) into a folder such as /opt/lumen-mail")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=os.environ.get("LUMEN_MAIL_PROG", "python3 -m lumen_mail").rsplit("/", 1)[-1],
                                 description="Build, install and maintain the Lumen skin for Roundcube Webmail.",
                                 epilog="Exit codes: 0 ok, 1 error, 2 usage, 3 Elastic drift, 4 compile error, "
                                        "5 refused, 6 not installed, 10 sync needed, 75 try again later.")
    ap.add_argument("--version", action="store_true", help="print the lumen-mail version and exit")
    sub = ap.add_subparsers(dest="command", metavar="command")
    for name, (_fn, configure, help_text) in COMMANDS.items():
        configure(sub.add_parser(name, help=help_text, description=help_text))
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    if args.version:
        sources = Sources.locate()
        print(f"lumen-mail {sources.version} ({sources.root})")
        return 0
    if not args.command:
        ap.print_usage(sys.stderr)
        return 2
    fn = COMMANDS[args.command][0]
    try:
        continue_as_owner(args)
        return fn(args)
    except BusyError as exc:
        if args.command != "sync":
            print(exc.render(), file=sys.stderr)
        else:
            # Another run (path unit, timer or an admin) is doing the work: not a fault.
            Log(quiet=getattr(args, "quiet", False)).notice(str(exc))
        return exc.exit_code
    except LumenError as exc:
        print(exc.render(), file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


__all__ = ["main", "parser", "EXIT_SYNC_NEEDED"]
