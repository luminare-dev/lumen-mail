"""build: assemble skins/lumen from our sources and the installed Elastic.

1. Drift check: every Elastic file, marker and variable Lumen relies on is still there.
2. Mirror tree in a temporary directory next to the output:
       <tmp>/skins/elastic  -> symlink to <roundcube>/skins/elastic (read-only use)
       <tmp>/skins/lumen/   our static files, our LESS and two entry files in styles/
   less runs with rewriteUrls "off", like Elastic's own build: Elastic writes every url()
   relative to its styles/ folder, and data-uri() reads files relative to the entry. For the
   compile only, Elastic's images are linked into <tmp>/skins/lumen/images so that its
   data-uri() icons are embedded as in Elastic's own stylesheet.
3. Compile styles.css/.min.css and embed.css/.min.css. Each local url() is then resolved the way
   Roundcube looks up skin files: in skins/lumen first, then in skins/elastic (rewritten to
   ../../elastic/...). It gets a ?v=<sha256 prefix> cache-buster (Roundcube serves skin files
   with a one-month Expires header), its target must exist and be a type static.php serves, and
   every file gets the licence banner.
4. Write the stamp (lumen-build.stamp), move the result into place and run verify on it.

The command palette (palette/dist/lumen-palette.js, built by Vite beforehand) is part of every
build: there is no switch to leave it out, so no build, install or release package can ship
without it by accident. Tests use a stub bundle (tests/fixtures/lumen-palette.js).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import posixpath
import shutil
import string
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import PARENT_SKIN, PROJECT_URL, SKIN_NAME, STAMP_NAME, STAMP_SCHEMA
from .compiler import CompileJob, compiler_command, run_compiler
from .cssurls import CssUrl, resolve, rewrite_urls
from .elastic import check_drift
from .roundcube import Roundcube
from .sources import LESS_FILES, Sources
from .templates import assemble
from .util import LumenError, info, sha256_file, short_hash, walk_files

ENTRIES = {
    # output name: LESS entry written into the mirror tree
    "styles": "@import \"../../elastic/styles/styles.less\";\n"
              "@import \"lumen-tokens.less\";\n"
              "@import \"lumen-variables.less\";\n"
              "@import \"lumen.less\";\n",
    "embed": "@import \"../../elastic/styles/embed.less\";\n"
             "@import \"lumen-tokens.less\";\n"
             "@import \"lumen-variables.less\";\n"
             "@import \"lumen-embed.less\";\n",
}
CSS_OUTPUTS = ("styles/styles.css", "styles/styles.min.css", "styles/embed.css", "styles/embed.min.css")
PALETTE_FILE = "lumen-palette.js"
# Copied from the source root into every build (and so into every release package).
# THIRD_PARTY_NOTICES.md carries React's MIT licence for the bundled command palette.
LEGAL_FILES = ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")
BANNER = """/*! Lumen {lumen_version} for Roundcube Webmail {roundcube_version}: {name}
 * Compiled on this server from two sources:
 *  - the Roundcube "Elastic" skin by Aleksander Machniak and The Roundcube Dev Team,
 *    licensed under CC BY-SA 3.0 (https://creativecommons.org/licenses/by-sa/3.0/);
 *  - the Lumen sources, Copyright (c) 2026 Paul Pasaurek, MIT licence ({project_url}).
 * This compiled file is an adaptation of Elastic and is licensed under CC BY-SA 3.0.
 * Not affiliated with or endorsed by the Roundcube project. Credits: skins/lumen/README.md
 */
"""


@dataclass
class BuildOptions:
    roundcube: Path
    out: Path
    sources: Sources
    compiler: str | None = None
    node: str | None = None
    work_dir: Path | None = None
    quiet: bool = False
    now: _dt.datetime | None = None


@dataclass
class BuildResult:
    out: Path
    stamp: dict
    sizes: dict[str, int] = field(default_factory=dict)


def build(opts: BuildOptions) -> BuildResult:
    rc = Roundcube.at(opts.roundcube)
    sources = opts.sources
    sources.check()
    check_drift(rc, sources)
    sources.require_palette()
    out = opts.out.resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise LumenError(f"{out} already exists and is not an empty directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    work_parent = opts.work_dir or out.parent
    work_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".lumen-build-", dir=work_parent))
    try:
        mirror = work / "skins"
        mirror.mkdir()
        os.symlink(rc.elastic_dir, mirror / PARENT_SKIN, target_is_directory=True)
        skin = mirror / SKIN_NAME
        lumen_version = sources.version
        roundcube_version = rc.version()
        info(f"lumen-mail {lumen_version}: building against Roundcube {roundcube_version} at {rc.root}", opts.quiet)
        assemble_static(sources, skin, lumen_version=lumen_version, roundcube_version=roundcube_version)
        styles = skin / "styles"
        styles.mkdir(exist_ok=True)
        for name in LESS_FILES:
            shutil.copy2(sources.less_dir / name, styles / name)
        jobs = []
        for out_name, entry_text in ENTRIES.items():
            entry = styles / f"lumen-entry-{out_name}.less"
            entry.write_text(entry_text, encoding="utf-8")
            jobs.append(CompileJob(entry, styles / f"{out_name}.css", styles / f"{out_name}.min.css"))
        helpers = link_elastic_images(rc.elastic_dir, skin)
        command = compiler_command(sources, opts.compiler, opts.node)
        try:
            result = run_compiler(command, jobs, sources.node_modules)
        finally:
            for link in helpers:
                link.unlink()
        for res in result.get("results", []):
            for warning in res.get("warnings", []):
                info(f"  compiler warning ({Path(res.get('entry', '?')).name}): {warning}", opts.quiet)
        static_types = rc.static_types()
        for rel in CSS_OUTPUTS:
            path = skin / rel
            css = path.read_text(encoding="utf-8")
            css = finalize_css(css, rel, mirror, static_types)
            banner = BANNER.format(lumen_version=lumen_version, roundcube_version=roundcube_version,
                                   name=f"skins/{SKIN_NAME}/{rel}", project_url=PROJECT_URL)
            path.write_text(banner + css, encoding="utf-8")
        for name in LESS_FILES:
            (styles / name).unlink()
        for job in jobs:
            job.entry.unlink()
        now = (opts.now or source_date() or _dt.datetime.now(_dt.timezone.utc)).replace(microsecond=0)
        stamp = {
            "schema": STAMP_SCHEMA,
            "skin": SKIN_NAME,
            "lumen_version": lumen_version,
            "roundcube_version": roundcube_version,
            "elastic_digest": rc.elastic_digest(),
            "source_digest": sources.digest(),
            "palette": True,
            "built_at": now.isoformat().replace("+00:00", "Z"),
            "compiler": result.get("versions", {}),
            "files": {p.as_posix(): sha256_file(skin / p) for p in walk_files(skin)},
        }
        (skin / STAMP_NAME).write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sizes = {rel: (skin / rel).stat().st_size for rel in CSS_OUTPUTS}
        if out.exists():
            out.rmdir()
        shutil.move(str(skin), str(out))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    from .verify import verify  # local import: verify imports build's constants

    problems = verify(out, rc, sources=sources)
    if problems:
        raise LumenError(f"the build in {out} does not pass verify", problems)
    for rel, size in sizes.items():
        info(f"  {rel}: {size} bytes", opts.quiet)
    info(f"built {out}", opts.quiet)
    return BuildResult(out=out, stamp=stamp, sizes=sizes)


def source_date() -> _dt.datetime | None:
    """SOURCE_DATE_EPOCH (reproducible builds), if set."""
    value = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if not value.isdigit():
        return None
    return _dt.datetime.fromtimestamp(int(value), _dt.timezone.utc)


def assemble_static(sources: Sources, skin: Path, lumen_version: str, roundcube_version: str) -> None:
    """Copy our static skin files and the palette bundle; assemble wrapper templates; render the README."""
    src = sources.skin_dir
    for rel in walk_files(src):
        target = skin / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel.parts[0] == "templates" and rel.suffix == ".html":
            text = (src / rel).read_text(encoding="utf-8")
            target.write_text(assemble(text, keep=set()), encoding="utf-8")
        elif rel.as_posix() == "README.md":
            text = string.Template((src / rel).read_text(encoding="utf-8"))
            target.write_text(text.substitute(lumen_version=lumen_version, roundcube_version=roundcube_version),
                              encoding="utf-8")
        else:
            shutil.copy2(src / rel, target)
    for name in LEGAL_FILES:
        shutil.copy2(sources.root / name, skin / name)
    shutil.copy2(sources.palette, skin / PALETTE_FILE)


def link_elastic_images(elastic: Path, skin: Path) -> list[Path]:
    """Temporarily link Elastic's images into the mirror skin, for data-uri() during the compile."""
    links: list[Path] = []
    src = elastic / "images"
    if not src.is_dir():
        return links
    for rel in walk_files(src):
        target = skin / "images" / rel
        if target.exists() or target.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(src / rel, target)
        links.append(target)
    return links


def finalize_css(css: str, rel: str, mirror: Path, static_types: set[str] | None) -> str:
    """Resolve each local url() (Lumen first, then Elastic), add the cache-buster, check it."""
    folder = posixpath.dirname(rel)
    lumen_base = f"skins/{SKIN_NAME}/{folder}"
    elastic_base = f"skins/{PARENT_SKIN}/{folder}"
    root = mirror.parent
    problems: list[str] = []

    def fix(url: CssUrl) -> str | None:
        if url.is_absolute_path:
            problems.append(f"{rel}: url({url.value}) is absolute; it would point at the web server root")
            return None
        if not url.is_local:
            return None
        path, query, frag = url.parts()
        ours, theirs = resolve(lumen_base, path), resolve(elastic_base, path)
        if ours.startswith(f"skins/{SKIN_NAME}/") and (root / ours).is_file():
            target, new_path = ours, path
        elif theirs.startswith(f"skins/{PARENT_SKIN}/") and (root / theirs).is_file():
            target, new_path = theirs, posixpath.relpath(theirs, lumen_base)
        else:
            problems.append(f"{rel}: url({url.value}) exists neither as {ours} nor as {theirs}")
            return None
        file = root / target
        ext = file.suffix.lstrip(".").lower()
        if static_types is not None and ext not in static_types:
            problems.append(f"{rel}: url({url.value}): Roundcube's static.php does not serve .{ext} files")
        query = "&".join([q for q in query.split("&") if q and not q.startswith("v=")] + [f"v={short_hash(file)}"])
        return new_path + "?" + query + ("#" + frag if frag else "")

    out = rewrite_urls(css, fix)
    if problems:
        raise LumenError("the compiled CSS has url() references that would not work", problems)
    return out
