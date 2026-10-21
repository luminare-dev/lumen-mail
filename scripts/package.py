#!/usr/bin/env python3
"""Build the Lumen release package for Roundcube installs without a build step.

    python3 scripts/package.py fetch --dest DIR [--archive FILE]
        download the pinned official Roundcube release (github.com/roundcube/roundcubemail), check
        its sha256 and extract it to DIR (DIR is then a Roundcube root). --archive uses a local
        copy instead of downloading; the checksum is checked either way.
    python3 scripts/package.py build --roundcube ROOT --out dist
        build skins/lumen against ROOT's Elastic, verify it and write
        dist/lumen-<version>-roundcube-<roundcube version>.tar.gz and .zip; add both to
        dist/SHA256SUMS. Both archives hold one folder, lumen/, to extract into <roundcube>/skins/.
    python3 scripts/package.py release --out dist
        fetch into a temporary folder, then build (what the release workflow runs).

Reproducible: the archive entries are sorted, owned by 0:0 with modes 755/644, and dated
SOURCE_DATE_EPOCH (default: the time of the last git commit), which is also the stamp's built_at;
gzip stores no name and no time. The same commit, Roundcube release and compiler versions give
the same bytes. Python standard library only; the compile needs Node and `npm ci` (package.json),
and every package includes the command palette, built first with `npm run build:palette`.

The compiled CSS in the package is an adaptation of Roundcube's Elastic skin and is licensed under
CC BY-SA 3.0; lumen/README.md, lumen/LICENSE and lumen/NOTICE state every licence.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail.build import BuildOptions, build  # noqa: E402
from lumen_mail.roundcube import Roundcube  # noqa: E402
from lumen_mail.sources import Sources  # noqa: E402
from lumen_mail.util import LumenError, walk_files  # noqa: E402
from lumen_mail.verify import verify  # noqa: E402

# The official release the CI builds and tests against (sha256 read from the downloaded archive on
# 2026-10-21; the release page publishes no checksum file).
ROUNDCUBE_VERSION = "1.7.3"
ROUNDCUBE_SHA256 = "08916e7902c9afae7e57a4303de09f0110159823563b7b73d2bd18607aabf276"
ROUNDCUBE_URL = "https://github.com/roundcube/roundcubemail/releases/download/{v}/roundcubemail-{v}.tar.gz"
TOP = "lumen"
DOWNLOAD_TIMEOUT = 120
MAX_DOWNLOAD = 64 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    if not url.startswith("https://"):
        raise SystemExit(f"error: refusing to download over a non-HTTPS URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "lumen-mail-package"})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, dest.open("wb") as fh:  # noqa: S310
        size = 0
        for chunk in iter(lambda: resp.read(1 << 16), b""):
            size += len(chunk)
            if size > MAX_DOWNLOAD:
                raise SystemExit(f"error: {url} is larger than {MAX_DOWNLOAD} bytes")
            fh.write(chunk)


def extract_release(archive: Path, dest: Path) -> Path:
    """Extract a Roundcube release archive without its top folder. tarfile's "data" filter refuses
    absolute paths, "..", links that leave the folder and device files; modes are sanitised."""
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"error: {dest} exists and is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            members = []
            for m in tar.getmembers():
                parts = m.name.split("/", 1)
                if len(parts) < 2 or not parts[1]:
                    continue
                m.name = parts[1]
                if m.islnk() or m.issym():
                    continue      # a release archive needs no links; skipping them is the safe default
                members.append(m)
            tar.extractall(dest, members=members, filter="data")
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    if not (dest / "program" / "include" / "iniset.php").is_file():
        raise SystemExit(f"error: {archive} does not look like a Roundcube release (no program/include/iniset.php)")
    return dest


def fetch(dest: Path, version: str, sha256: str, archive: Path | None) -> Path:
    with tempfile.TemporaryDirectory(prefix="lumen-roundcube-") as tmp:
        if archive is None:
            archive = Path(tmp) / f"roundcubemail-{version}.tar.gz"
            url = ROUNDCUBE_URL.format(v=version)
            print(f"downloading {url}", file=sys.stderr)
            download(url, archive)
        actual = sha256_file(archive)
        if actual != sha256:
            raise SystemExit(f"error: sha256 of {archive.name} is {actual}, expected {sha256}")
        print(f"sha256 ok: {actual}  {archive.name}", file=sys.stderr)
        return extract_release(archive, dest)


def source_date_epoch() -> int:
    value = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if value.isdigit():
        return int(value)
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%ct"], capture_output=True, text=True,
                             check=True, timeout=30).stdout.strip()
        if out.isdigit():
            return int(out)
    except (OSError, subprocess.SubprocessError):
        pass
    return int(_dt.datetime.now(_dt.timezone.utc).timestamp())


def _entries(skin: Path) -> list[tuple[str, Path | None]]:
    """(archive name, file or None for a folder), sorted, folders before their content."""
    names: dict[str, Path | None] = {f"{TOP}/": None}
    for rel in walk_files(skin):
        parts = rel.parts
        for i in range(1, len(parts)):
            names[f"{TOP}/{'/'.join(parts[:i])}/"] = None
        names[f"{TOP}/{rel.as_posix()}"] = skin / rel
    return sorted(names.items())


def write_tar_gz(skin: Path, dest: Path, epoch: int) -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, path in _entries(skin):
            info = tarfile.TarInfo(name.rstrip("/"))
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if path is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            else:
                data = path.read_bytes()
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
    with dest.open("wb") as fh, gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())


def write_zip(skin: Path, dest: Path, epoch: int) -> None:
    when = _dt.datetime.fromtimestamp(max(epoch, 315532800), _dt.timezone.utc).timetuple()[:6]
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, path in _entries(skin):
            info = zipfile.ZipInfo(name, date_time=when)
            info.create_system = 3
            if path is None:
                info.external_attr = (0o40755 << 16) | 0x10
                zf.writestr(info, b"")
            else:
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, path.read_bytes())


def update_sums(out: Path, files: list[Path]) -> Path:
    sums = out / "SHA256SUMS"
    lines: dict[str, str] = {}
    if sums.is_file():
        for line in sums.read_text(encoding="utf-8").splitlines():
            digest, _, name = line.partition("  ")
            if name:
                lines[name] = digest
    for f in files:
        lines[f.name] = sha256_file(f)
    sums.write_text("".join(f"{d}  {n}\n" for n, d in sorted(lines.items())), encoding="utf-8")
    return sums


def build_package(roundcube: Path, out: Path, version: str | None = None, compiler: str | None = None,
                  node_modules: str | None = None, palette: str | None = None) -> list[Path]:
    """Build the release package. The command palette is always included (no option leaves it out)."""
    sources = Sources.locate(ROOT, node_modules, palette)
    sources.require_palette()
    version = version or sources.version
    epoch = source_date_epoch()
    os.environ["SOURCE_DATE_EPOCH"] = str(epoch)
    rc = Roundcube.at(roundcube)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lumen-package-") as tmp:
        skin = Path(tmp) / TOP
        build(BuildOptions(roundcube=rc.root, out=skin, sources=sources, compiler=compiler,
                           work_dir=Path(tmp), quiet=True,
                           now=_dt.datetime.fromtimestamp(epoch, _dt.timezone.utc)))
        problems = verify(skin, rc, sources)
        if problems:
            raise LumenError("the package build does not pass verify", problems)
        base = f"lumen-{version}-roundcube-{rc.version()}"
        tgz, zipf = out / f"{base}.tar.gz", out / f"{base}.zip"
        write_tar_gz(skin, tgz, epoch)
        write_zip(skin, zipf, epoch)
    sums = update_sums(out, [tgz, zipf])
    return [tgz, zipf, sums]


def _add_pin_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--archive", type=Path, help="use this local archive instead of downloading")
    p.add_argument("--roundcube-version", default=ROUNDCUBE_VERSION)
    p.add_argument("--sha256", default=ROUNDCUBE_SHA256, help="expected sha256 of the release archive")


def _add_build_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", type=Path, default=ROOT / "dist")
    p.add_argument("--version", help="package version (default: version.txt)")
    p.add_argument("--palette", help="the built command palette (default: palette/dist/lumen-palette.js)")
    p.add_argument("--compiler", help="compiler command (tests)")
    p.add_argument("--node-modules", help="node_modules with less and clean-css (default: ./node_modules)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download, check and extract the pinned Roundcube release")
    f.add_argument("--dest", type=Path, required=True)
    _add_pin_args(f)
    b = sub.add_parser("build", help="build the package from an extracted Roundcube")
    b.add_argument("--roundcube", type=Path, required=True)
    _add_build_args(b)
    r = sub.add_parser("release", help="fetch into a temporary folder, then build")
    _add_pin_args(r)
    _add_build_args(r)
    args = ap.parse_args(argv)
    if args.command in ("fetch", "release") and (args.roundcube_version != ROUNDCUBE_VERSION) != (
            args.sha256 != ROUNDCUBE_SHA256):
        raise SystemExit("error: --roundcube-version and --sha256 must be changed together")
    try:
        if args.command == "fetch":
            print(fetch(args.dest, args.roundcube_version, args.sha256, args.archive))
            return 0
        if args.command == "build":
            files = build_package(args.roundcube, args.out, args.version, args.compiler, args.node_modules,
                                  args.palette)
        else:
            with tempfile.TemporaryDirectory(prefix="lumen-release-") as tmp:
                rc = fetch(Path(tmp) / "roundcube", args.roundcube_version, args.sha256, args.archive)
                files = build_package(rc, args.out, args.version, args.compiler, args.node_modules, args.palette)
    except LumenError as exc:
        print(exc.render(), file=sys.stderr)
        return exc.exit_code
    for path in files:
        print(f"{sha256_file(path)}  {path.stat().st_size:>9}  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
