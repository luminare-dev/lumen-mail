#!/usr/bin/env python3
"""Check that the shared token code is still a copy of the Hydrodactyl theme's (shared.lock).

The token schema and CSS compiler (core.ts) and the presets come from
luminare-dev/lumen-hydrodactyl-theme, so one token file imports in every Lumen theme. The copies
are byte for byte. shared.lock names the source commit and the sha256 of every source file; this
script

  verify   (default) checks the local copies against the hashes in shared.lock (offline);
  fetch    downloads the source files at the locked commit and checks them against the lock too;
  update   rewrites shared.lock from a local checkout: --from ../lumen-hydrodactyl-theme

Python standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "shared.lock"
SOURCE_REPO = "luminare-dev/lumen-hydrodactyl-theme"

# local path -> path in the source repository
FILES = {
    "tokens/core.ts": "overlay/files/resources/scripts/lumen/core.ts",
    "tokens/presets/luminare.json": "overlay/files/resources/lumen/presets/luminare.json",
    "tokens/presets/graphite.json": "overlay/files/resources/lumen/presets/graphite.json",
    "tokens/presets/aurora.json": "overlay/files/resources/lumen/presets/aurora.json",
    "tokens/presets/contrast.json": "overlay/files/resources/lumen/presets/contrast.json",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_lock() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


def verify(lock: dict) -> list[str]:
    problems = []
    for local, source in FILES.items():
        expected = lock["files"].get(source)
        path = ROOT / local
        if expected is None:
            problems.append(f"{source}: not in shared.lock")
            continue
        if not path.is_file():
            problems.append(f"{local}: missing")
            continue
        got = sha(path.read_bytes())
        if got != expected:
            problems.append(f"{local}: differs from {SOURCE_REPO}@{lock['commit'][:7]}:{source}")
    return problems


def fetch(lock: dict) -> list[str]:
    problems = []
    for source in FILES.values():
        url = f"https://raw.githubusercontent.com/{SOURCE_REPO}/{lock['commit']}/{source}"
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 (fixed https URL)
            data = response.read()
        if sha(data) != lock["files"].get(source):
            problems.append(f"{source}: shared.lock does not match {SOURCE_REPO}@{lock['commit'][:7]}")
    return problems


def update(source_root: Path) -> None:
    commit = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    files = {src: sha((source_root / src).read_bytes()) for src in FILES.values()}
    LOCK.write_text(
        json.dumps({"repository": SOURCE_REPO, "commit": commit, "files": files}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"shared.lock -> {commit}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", default="verify", choices=["verify", "fetch", "update"])
    parser.add_argument("--from", dest="source", type=Path, help="local checkout of the source repo (update)")
    args = parser.parse_args(argv)

    if args.action == "update":
        if not args.source:
            parser.error("update needs --from")
        update(args.source)
        return 0

    lock = load_lock()
    problems = verify(lock)
    if args.action == "fetch":
        problems += fetch(lock)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if not problems:
        print(f"shared code matches {SOURCE_REPO}@{lock['commit'][:12]}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
