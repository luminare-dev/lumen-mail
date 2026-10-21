"""Command line: python3 -m lumen_mail <command> ...

Exit codes: 0 ok, 1 error, 2 usage, 3 Elastic drift (the installed Elastic changed in a way the
build does not support), 4 compile error. Each command is one function registered in COMMANDS,
so new commands (install, check, sync, status, uninstall, install-runtime) plug in the same way.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from .build import BuildOptions, build
from .roundcube import Roundcube
from .sources import Sources
from .util import LumenError
from .verify import verify

Command = Callable[[argparse.Namespace], int]
Configure = Callable[[argparse.ArgumentParser], None]
COMMANDS: dict[str, tuple[Command, Configure, str]] = {}


def register(name: str, fn: Command, configure: Configure, help_text: str) -> None:
    COMMANDS[name] = (fn, configure, help_text)


def add_source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--source", help="lumen-mail sources (default: this checkout, or $LUMEN_MAIL_SOURCE)")
    p.add_argument("--node-modules", help="node_modules with less and clean-css (default: <source>/node_modules)")


def sources_from(args: argparse.Namespace) -> Sources:
    return Sources.locate(getattr(args, "source", None), getattr(args, "node_modules", None),
                          getattr(args, "palette", None))


def cmd_build(args: argparse.Namespace) -> int:
    result = build(BuildOptions(
        roundcube=Path(args.roundcube), out=Path(args.out), sources=sources_from(args),
        palette=not args.no_palette, compiler=args.compiler, node=args.node,
        work_dir=Path(args.work_dir) if args.work_dir else None, quiet=args.quiet,
    ))
    if args.print_stamp:
        print(json.dumps(result.stamp, indent=2, sort_keys=True))
    return 0


def configure_build(p: argparse.ArgumentParser) -> None:
    p.add_argument("--roundcube", required=True, help="Roundcube root (the folder with program/ and skins/)")
    p.add_argument("--out", required=True, help="output folder for the skin (must not exist or be empty)")
    add_source_args(p)
    p.add_argument("--palette", help="the built command palette (default: <source>/palette/dist/lumen-palette.js)")
    p.add_argument("--no-palette", action="store_true", help="build without the command palette")
    p.add_argument("--compiler", help="compiler command speaking compile.mjs's protocol (tests; $LUMEN_MAIL_COMPILER)")
    p.add_argument("--node", help="node binary (default: node from PATH, or $LUMEN_MAIL_NODE)")
    p.add_argument("--work-dir", help="where the temporary mirror tree goes (default: next to --out)")
    p.add_argument("--print-stamp", action="store_true", help="print the stamp as JSON on stdout")
    p.add_argument("-q", "--quiet", action="store_true")


def cmd_verify(args: argparse.Namespace) -> int:
    rc = Roundcube.at(args.roundcube)
    sources = None if args.no_source else sources_from(args)
    problems = verify(Path(args.skin), rc, sources=sources)
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
    p.add_argument("-q", "--quiet", action="store_true")


register("build", cmd_build, configure_build, "assemble skins/lumen from our sources and the installed Elastic")
register("verify", cmd_verify, configure_verify, "check a built skin folder against a Roundcube installation")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python3 -m lumen_mail",
                                 description="Build and verify the Lumen skin for Roundcube Webmail.")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")
    for name, (_fn, configure, help_text) in COMMANDS.items():
        configure(sub.add_parser(name, help=help_text, description=help_text))
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    fn = COMMANDS[args.command][0]
    try:
        return fn(args)
    except LumenError as exc:
        print(exc.render(), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
