"""Lumen's wrapper templates: assembly (build) and the "wrapper only" rule (verify).

Lumen never copies an Elastic template. Where it needs to add something to a page, it ships a
template of the same name that contains only:

  * Roundcube conditions:      <roundcube:if condition="..." />, elseif, else, endif
  * label registrations:       <roundcube:add_label name="..." />
  * script tags for our files: <script src="/lumen.js" ...></script>
  * exactly one include of Elastic's template of the same name, as the last element:
        <roundcube:include file="includes/footer.html" skinpath="skins/elastic" />

The skinpath attribute is not optional: without it Roundcube would resolve the include to the
wrapper itself and recurse until PHP runs out of memory.

Optional blocks in the source are delimited by <!--lumen:NAME--> ... <!--/lumen:NAME-->; the
build keeps or drops each block (the palette block needs the palette bundle) and removes the
markers, so the installed templates contain no comments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import PARENT_SKIN
from .util import LumenError

BLOCK_RE = re.compile(r"[ \t]*<!--lumen:([a-z-]+)-->[ \t]*\n(.*?)[ \t]*<!--/lumen:\1-->[ \t]*\n", re.DOTALL)
TOKEN_RE = re.compile(
    r"(?P<rc><roundcube:(?P<tag>[a-z_]+)(?P<attrs>(?:\s+[a-z_-]+=\"[^\"]*\")*)\s*/>)"
    r"|(?P<script><script(?P<sattrs>(?:\s+[a-z-]+(?:=\"[^\"]*\")?)*)\s*></script>)"
    r"|(?P<space>\s+)",
    re.IGNORECASE,
)
ATTR_RE = re.compile(r"([a-z_-]+)(?:=\"([^\"]*)\")?", re.IGNORECASE)
LABEL_RE = re.compile(r"^(lumen\.[a-z0-9_]+|[a-z0-9_]+)$")
ALLOWED_SCRIPT_ATTRS = {"src", "defer"}


def assemble(source: str, keep: set[str]) -> str:
    """Keep or drop each optional block, remove the markers."""
    def repl(m: re.Match) -> str:
        return m.group(2) if m.group(1) in keep else ""

    out = BLOCK_RE.sub(repl, source)
    if "<!--" in out:
        raise LumenError("a wrapper template contains a malformed <!--lumen:...--> block or another HTML comment")
    return out


@dataclass
class WrapperReport:
    scripts: list[dict[str, str]]
    labels: list[str]
    include: str | None


def parse_attrs(text: str) -> dict[str, str]:
    return {m.group(1).lower(): (m.group(2) if m.group(2) is not None else "") for m in ATTR_RE.finditer(text)}


def check_wrapper(rel: str, text: str) -> tuple[WrapperReport, list[str]]:
    """Check one installed template (rel = path below templates/, e.g. includes/footer.html)."""
    problems: list[str] = []
    scripts: list[dict[str, str]] = []
    labels: list[str] = []
    include: str | None = None
    depth = 0
    pos = 0
    for m in TOKEN_RE.finditer(text):
        if m.start() != pos:
            break
        pos = m.end()
        if m.group("space"):
            continue
        if include is not None:
            problems.append(f"templates/{rel}: nothing may follow the include of Elastic's template")
        if m.group("rc"):
            tag = m.group("tag").lower()
            attrs = parse_attrs(m.group("attrs") or "")
            if tag in ("if", "elseif"):
                if set(attrs) != {"condition"}:
                    problems.append(f"templates/{rel}: <roundcube:{tag}> must have only a condition attribute")
                depth += tag == "if"
                if tag == "elseif" and depth == 0:
                    problems.append(f"templates/{rel}: elseif without if")
            elif tag in ("else", "endif"):
                if attrs:
                    problems.append(f"templates/{rel}: <roundcube:{tag}> takes no attributes")
                if depth == 0:
                    problems.append(f"templates/{rel}: {tag} without if")
                if tag == "endif":
                    depth = max(0, depth - 1)
            elif tag == "add_label":
                name = attrs.get("name", "")
                if set(attrs) != {"name"} or not LABEL_RE.match(name):
                    problems.append(f"templates/{rel}: <roundcube:add_label> needs one plain name attribute")
                labels.append(name)
            elif tag == "include":
                want = {"file": rel, "skinpath": f"skins/{PARENT_SKIN}"}
                if attrs != want:
                    problems.append(f"templates/{rel}: the include must be exactly "
                                    f"file=\"{rel}\" skinpath=\"skins/{PARENT_SKIN}\" (found {attrs})")
                if depth:
                    problems.append(f"templates/{rel}: the include of Elastic's template must not be conditional")
                include = attrs.get("file")
            else:
                problems.append(f"templates/{rel}: <roundcube:{tag}> is not allowed in a wrapper template")
        elif m.group("script"):
            attrs = parse_attrs(m.group("sattrs") or "")
            bad = [a for a in attrs if a not in ALLOWED_SCRIPT_ATTRS and not a.startswith("data-src-")]
            if bad:
                problems.append(f"templates/{rel}: script attribute(s) {bad} are not allowed")
            src = attrs.get("src", "")
            if not src.startswith("/") or ".." in src or not src.endswith(".js"):
                problems.append(f"templates/{rel}: script src {src!r} must be a /path/to/file.js inside the skin")
            for key, value in attrs.items():
                if key.startswith("data-src-") and (not value.startswith("/") or ".." in value):
                    problems.append(f"templates/{rel}: {key}={value!r} must be a /path inside the skin")
            scripts.append(attrs)
    if pos != len(text):
        snippet = text[pos:pos + 60].replace("\n", "\\n")
        problems.append(f"templates/{rel}: markup that is not a wrapper construct at offset {pos}: {snippet!r}")
    if depth:
        problems.append(f"templates/{rel}: {depth} <roundcube:if> block(s) not closed")
    if include is None:
        problems.append(f"templates/{rel}: missing the include of Elastic's {rel} (a wrapper must include it last)")
    return WrapperReport(scripts, labels, include), problems


def template_files(skin_dir: Path) -> list[str]:
    base = skin_dir / "templates"
    if not base.is_dir():
        return []
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
