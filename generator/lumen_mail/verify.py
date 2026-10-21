"""verify: check a built skin folder against the Roundcube it is (or will be) installed in.

Checks, each with a message that names the file:
  * meta.json: valid, named Lumen, extends elastic, localization on, only known config keys;
  * every required file exists; nothing in the folder is a copy of an Elastic file;
  * templates are wrappers only (see templates.py) and their Elastic counterpart exists;
  * scripts and data-src-* references in the templates point to files in the skin;
  * compiled CSS: licence banner, every url() resolves at the FINAL location
    (<roundcube>/skins/lumen/styles/), is a type static.php serves and carries ?v=<hash> of the
    current target content;
  * the stamp matches the folder (file hashes) and the Roundcube install (version, Elastic digest)
    and, when the sources are known, the Lumen version.

exact=False (install --from --allow-mismatch, for a release package built against another release
of the same Roundcube series) skips the two checks that tie a build to one Elastic: the stamp's
Roundcube version and Elastic digest, and the cache-busters of url()s into skins/elastic.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from . import PARENT_SKIN, SKIN_NAME, STAMP_NAME, STAMP_SCHEMA
from .build import CSS_OUTPUTS, PALETTE_FILE
from .cssurls import iter_urls, resolve
from .roundcube import Roundcube
from .sources import Sources
from .templates import check_wrapper, template_files
from .util import sha256_file, short_hash, walk_files

REQUIRED = (
    "meta.json",
    "README.md",
    "lumen.js",
    "watermark.html",
    "thumbnail.png",
    "templates/includes/footer.html",
    "localization/en_US.inc",
    "localization/de_DE.inc",
    "fonts/Sora-Variable.woff",
    "fonts/Sora-OFL.txt",
    "LICENSE",
    "NOTICE",
    *CSS_OUTPUTS,
    STAMP_NAME,
)
META_CONFIG_KEYS = {"favicon"}
BANNER_MARK = "This compiled file is an adaptation of Elastic and is licensed under CC BY-SA 3.0."


def verify(skin: Path, rc: Roundcube, sources: Sources | None = None, exact: bool = True) -> list[str]:
    skin = Path(skin)
    problems: list[str] = []
    if not skin.is_dir():
        return [f"{skin} is not a directory"]
    for rel in REQUIRED:
        if not (skin / rel).is_file():
            problems.append(f"{rel} is missing")
    problems += _check_meta(skin)
    problems += _check_no_elastic_copies(skin, rc)
    problems += _check_templates(skin, rc)
    problems += _check_css(skin, rc, exact)
    problems += _check_thumbnail(skin)
    problems += _check_stamp(skin, rc, sources, exact)
    return problems


def _check_meta(skin: Path) -> list[str]:
    path = skin / "meta.json"
    if not path.is_file():
        return []
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return [f"meta.json is not valid JSON: {exc}"]
    problems = []
    if meta.get("name") != "Lumen":
        problems.append(f"meta.json: name is {meta.get('name')!r}, expected 'Lumen'")
    if meta.get("extends") != PARENT_SKIN:
        problems.append(f"meta.json: extends is {meta.get('extends')!r}, expected {PARENT_SKIN!r}")
    if meta.get("localization") is not True:
        problems.append("meta.json: localization must be true (the palette labels live in localization/)")
    for key in ("author", "license", "url"):
        if not meta.get(key):
            problems.append(f"meta.json: {key} is empty")
    unknown = set(meta.get("config", {})) - META_CONFIG_KEYS
    if unknown:
        problems.append(f"meta.json: config keys {sorted(unknown)} are not expected (Elastic's own config is inherited)")
    favicon = meta.get("config", {}).get("favicon")
    if favicon and not (skin / favicon.lstrip("/")).is_file():
        problems.append(f"meta.json: favicon {favicon} does not exist in the skin")
    return problems


def _check_no_elastic_copies(skin: Path, rc: Roundcube) -> list[str]:
    elastic = rc.elastic_dir
    if not elastic.is_dir():
        return [f"{elastic} is missing"]
    elastic_hashes = {sha256_file(elastic / p): p.as_posix() for p in walk_files(elastic)}
    problems = []
    for rel in walk_files(skin):
        digest = sha256_file(skin / rel)
        if digest in elastic_hashes:
            problems.append(f"{rel.as_posix()} is a copy of skins/{PARENT_SKIN}/{elastic_hashes[digest]}")
    return problems


def _check_templates(skin: Path, rc: Roundcube) -> list[str]:
    problems = []
    for rel in template_files(skin):
        text = (skin / "templates" / rel).read_text(encoding="utf-8")
        report, found = check_wrapper(rel, text)
        problems += found
        if not (rc.elastic_dir / "templates" / rel).is_file():
            problems.append(f"templates/{rel} wraps skins/{PARENT_SKIN}/templates/{rel}, which does not exist")
        for attrs in report.scripts:
            for key, value in attrs.items():
                if (key == "src" or key.startswith("data-src-")) and value.startswith("/"):
                    if not (skin / value.lstrip("/")).is_file():
                        problems.append(f"templates/{rel}: {key}={value} does not exist in the skin")
    return problems


def _check_css(skin: Path, rc: Roundcube, exact: bool = True) -> list[str]:
    problems = []
    static_types = rc.static_types()
    for rel in CSS_OUTPUTS:
        path = skin / rel
        if not path.is_file():
            continue
        css = path.read_text(encoding="utf-8")
        if BANNER_MARK not in css[:2000]:
            problems.append(f"{rel}: the licence banner is missing")
        base = f"skins/{SKIN_NAME}/" + str(Path(rel).parent.as_posix())
        for url in iter_urls(css):
            if url.is_absolute_path:
                problems.append(f"{rel}: url({url.value}) is absolute")
                continue
            if not url.is_local:
                continue
            upath, query, _ = url.parts()
            target = resolve(base, upath)
            if target.startswith(f"skins/{SKIN_NAME}/"):
                file = skin / target[len(f"skins/{SKIN_NAME}/"):]
            elif target.startswith(f"skins/{PARENT_SKIN}/"):
                file = rc.root / target
            else:
                problems.append(f"{rel}: url({url.value}) resolves to {target}, outside the two skins")
                continue
            if not file.is_file():
                problems.append(f"{rel}: url({url.value}) points to {target}, which does not exist")
                continue
            ext = file.suffix.lstrip(".").lower()
            if static_types is not None and ext not in static_types:
                problems.append(f"{rel}: url({url.value}): static.php does not serve .{ext} files")
            if not exact and target.startswith(f"skins/{PARENT_SKIN}/"):
                continue
            want = f"v={short_hash(file)}"
            if want not in query.split("&"):
                problems.append(f"{rel}: url({url.value}) lacks the cache-buster {want} (target changed or not stamped)")
    return problems


def _check_thumbnail(skin: Path) -> list[str]:
    path = skin / "thumbnail.png"
    if not path.is_file():
        return []
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return ["thumbnail.png is not a PNG file"]
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) != (64, 64):
        return [f"thumbnail.png is {width}x{height}; the skin chooser shows it at 64x64"]
    return []


def _check_stamp(skin: Path, rc: Roundcube, sources: Sources | None, exact: bool = True) -> list[str]:
    path = skin / STAMP_NAME
    if not path.is_file():
        return []
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return [f"{STAMP_NAME} is not valid JSON: {exc}"]
    problems = []
    if stamp.get("schema") != STAMP_SCHEMA:
        problems.append(f"{STAMP_NAME}: schema {stamp.get('schema')!r}, expected {STAMP_SCHEMA}")
    if exact:
        try:
            rc_version = rc.version()
        except Exception as exc:  # noqa: BLE001 - reported as a problem
            rc_version = None
            problems.append(str(exc))
        if rc_version and stamp.get("roundcube_version") != rc_version:
            problems.append(f"{STAMP_NAME}: built for Roundcube {stamp.get('roundcube_version')}, "
                            f"installed is {rc_version}")
        digest = rc.elastic_digest()
        if stamp.get("elastic_digest") != digest:
            problems.append(f"{STAMP_NAME}: built from different Elastic sources "
                            f"({stamp.get('elastic_digest')} != {digest})")
    if sources is not None:
        try:
            version = sources.version
        except Exception:  # noqa: BLE001
            version = None
        if version and stamp.get("lumen_version") != version:
            problems.append(f"{STAMP_NAME}: built by lumen-mail {stamp.get('lumen_version')}, the sources are {version}")
    files = stamp.get("files")
    if not isinstance(files, dict) or not files:
        problems.append(f"{STAMP_NAME}: no file list")
        return problems
    present = {p.as_posix() for p in walk_files(skin)} - {STAMP_NAME}
    for rel, digest in sorted(files.items()):
        if rel not in present:
            problems.append(f"{rel} is listed in {STAMP_NAME} but missing")
        elif sha256_file(skin / rel) != digest:
            problems.append(f"{rel} differs from the content recorded in {STAMP_NAME}")
    for rel in sorted(present - set(files)):
        problems.append(f"{rel} is not listed in {STAMP_NAME}")
    if stamp.get("palette") and not (skin / PALETTE_FILE).is_file():
        problems.append(f"{PALETTE_FILE} is missing although the stamp says the palette is included")
    if not stamp.get("palette") and (skin / PALETTE_FILE).is_file():
        problems.append(f"{PALETTE_FILE} exists although the stamp says the build has no palette")
    return problems
