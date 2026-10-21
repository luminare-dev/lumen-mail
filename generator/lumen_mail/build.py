"""build: assemble skins/lumen from our sources and the installed Elastic.

1. Drift check: every Elastic file, marker and variable Lumen relies on is still there.
2. Mirror tree in a temporary directory next to the output:
       <tmp>/skins/elastic  -> symlink to <roundcube>/skins/elastic (read-only use)
       <tmp>/skins/lumen/   our static files, our LESS and two entry files
   The LESS compiler rewrites every url() relative to the entry (skins/lumen/styles/), so a
   reference into Elastic comes out as ../../elastic/fonts/... and is valid once the skin sits
   at <roundcube>/skins/lumen, next to Elastic.
3. Compile styles.css/.min.css and embed.css/.min.css; add a ?v=<sha256 prefix> cache-buster
   to every local url() (Roundcube serves skin files with a one-month Expires header), check
   that each target exists and is a type static.php serves, and add the licence banner.
4. Write the stamp (lumen-build.stamp), move the result into place and run verify on it.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
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
    palette: bool = True
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
    if opts.palette and not sources.palette.is_file():
        raise LumenError(f"the command palette bundle {sources.palette} is missing",
                         ["build it first (npm run build:palette), or pass --no-palette to build without it"])
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
        assemble_static(sources, skin, palette=opts.palette, lumen_version=lumen_version,
                        roundcube_version=roundcube_version)
        styles = skin / "styles"
        styles.mkdir(exist_ok=True)
        for name in LESS_FILES:
            shutil.copy2(sources.less_dir / name, styles / name)
        jobs = []
        for out_name, entry_text in ENTRIES.items():
            entry = styles / f"lumen-entry-{out_name}.less"
            entry.write_text(entry_text, encoding="utf-8")
            jobs.append(CompileJob(entry, styles / f"{out_name}.css", styles / f"{out_name}.min.css"))
        command = compiler_command(sources, opts.compiler, opts.node)
        result = run_compiler(command, jobs, sources.node_modules)
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
        now = (opts.now or _dt.datetime.now(_dt.timezone.utc)).replace(microsecond=0)
        stamp = {
            "schema": STAMP_SCHEMA,
            "skin": SKIN_NAME,
            "lumen_version": lumen_version,
            "roundcube_version": roundcube_version,
            "elastic_digest": rc.elastic_digest(),
            "source_digest": sources.digest(include_palette=opts.palette),
            "palette": bool(opts.palette),
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


def assemble_static(sources: Sources, skin: Path, palette: bool, lumen_version: str,
                    roundcube_version: str) -> None:
    """Copy our static skin files; assemble wrapper templates; render the README."""
    src = sources.skin_dir
    for rel in walk_files(src):
        target = skin / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel.parts[0] == "templates" and rel.suffix == ".html":
            text = (src / rel).read_text(encoding="utf-8")
            target.write_text(assemble(text, keep={"palette"} if palette else set()), encoding="utf-8")
        elif rel.as_posix() == "README.md":
            text = string.Template((src / rel).read_text(encoding="utf-8"))
            target.write_text(text.substitute(lumen_version=lumen_version, roundcube_version=roundcube_version),
                              encoding="utf-8")
        else:
            shutil.copy2(src / rel, target)
    if palette:
        shutil.copy2(sources.palette, skin / PALETTE_FILE)


def finalize_css(css: str, rel: str, mirror: Path, static_types: set[str] | None) -> str:
    """Add cache-busters to local url()s and fail on any that would not work once installed."""
    base = f"skins/{SKIN_NAME}/" + os.path.dirname(rel)
    problems: list[str] = []

    def fix(url: CssUrl) -> str | None:
        if url.is_absolute_path:
            problems.append(f"{rel}: url({url.value}) is absolute; it would point at the web server root")
            return None
        if not url.is_local:
            return None
        path, query, frag = url.parts()
        target = resolve(base, path)
        if not (target.startswith(f"skins/{SKIN_NAME}/") or target.startswith(f"skins/{PARENT_SKIN}/")):
            problems.append(f"{rel}: url({url.value}) resolves to {target}, outside skins/{SKIN_NAME} and skins/{PARENT_SKIN}")
            return None
        file = mirror.parent / target
        if not file.is_file():
            problems.append(f"{rel}: url({url.value}) points to {target}, which does not exist")
            return None
        ext = file.suffix.lstrip(".").lower()
        if static_types is not None and ext not in static_types:
            problems.append(f"{rel}: url({url.value}): Roundcube's static.php does not serve .{ext} files")
        query = "&".join([q for q in query.split("&") if q and not q.startswith("v=")] + [f"v={short_hash(file)}"])
        return path + "?" + query + ("#" + frag if frag else "")

    out = rewrite_urls(css, fix)
    if problems:
        raise LumenError("the compiled CSS has url() references that would not work", problems)
    return out
