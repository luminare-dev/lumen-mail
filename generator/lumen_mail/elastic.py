"""Drift detection: does the installed Elastic still have everything Lumen relies on?

Lumen copies nothing from Elastic. It compiles Elastic's LESS with our variable overrides, wraps
one Elastic template and swaps Elastic's default logo at run time. Each of those relies on a
file, a variable or a marker in Elastic; when a Roundcube update changes one of them, the build
must stop with a message that names it instead of producing a skin that silently looks wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .roundcube import Roundcube
from .sources import LESS_FILES, Sources
from .util import LumenError


class DriftError(LumenError):
    exit_code = 3


# (path in skins/elastic, why Lumen needs it)
REQUIRED_FILES = (
    ("meta.json", "Lumen's meta.json extends this skin"),
    ("styles/styles.less", "entry of the main stylesheet that Lumen compiles"),
    ("styles/embed.less", "entry of embed.css (editor and message frames)"),
    ("styles/variables.less", "defines the layout variables Lumen overrides"),
    ("styles/colors.less", "defines the colour variables Lumen overrides"),
    ("styles/mixins.less", "defines the .font-family mixin Lumen extends"),
    ("styles/global.less", "imported by both entries"),
    ("templates/includes/footer.html", "wrapped by Lumen's templates/includes/footer.html"),
    ("templates/includes/layout.html", "page head that links /styles/styles.css"),
    ("templates/includes/menu.html", "task menu with the logo that lumen.js replaces"),
    ("templates/login.html", "login page with the logo that lumen.js replaces"),
    ("images/logo.svg", "Elastic's default logo: lumen.js and lumen.less recognise it by this path"),
)

# Files that must NOT exist in Elastic. Templates of Elastic (layout.html) resolve their assets
# Elastic-first: Lumen's styles/styles.css is only used because Elastic ships styles.min.css
# without a styles.css (rcmail_output_html::file_callback adds the including skin's path first).
MUST_NOT_EXIST = (
    ("styles/styles.css", "Elastic's layout.html would load Elastic's stylesheet instead of Lumen's"),
)

# (path, literal text that must occur, why)
MARKERS = (
    ("templates/includes/footer.html", "</body>", "Lumen's footer wrapper places its scripts before Elastic's footer"),
    ("templates/includes/footer.html", 'src="/ui.js"', "lumen.js must run before Elastic's ui.js starts"),
    ("templates/includes/layout.html", 'href="/styles/styles.css"', "the stylesheet Lumen replaces"),
    ("templates/includes/menu.html", 'name="logo"', "the menu logo that lumen.js replaces"),
    ("templates/includes/menu.html", 'src="/images/logo.svg"', "the default logo path lumen.js recognises"),
    ("templates/login.html", 'name="logo"', "the login logo that lumen.js replaces"),
    ("templates/login.html", 'src="/images/logo.svg"', "the default logo path lumen.js recognises"),
    ("templates/login.html", 'id="login-form"', "the login card styled by lumen.less"),
    ("styles/mixins.less", ".font-family", "Lumen extends this mixin to set Sora"),
    ("styles/styles.less", '@import "dark"', "Elastic's dark mode, which Lumen recolours"),
)

VAR_DEF_RE = re.compile(r"^\s*@([A-Za-z_][\w-]*)\s*:", re.MULTILINE)
VAR_USE_RE = re.compile(r"@@?\{?([A-Za-z_][\w-]*)\}?")
# at-rules and LESS-internal names that look like variables
NOT_VARIABLES = {
    "import", "media", "font-face", "supports", "keyframes", "plugin", "charset", "namespace", "page",
    "document", "layer", "container", "property", "counter-style", "-webkit-keyframes",
    "value", "key", "index", "name", "mode", "arguments", "rest",
}


@dataclass
class VariableRef:
    name: str
    file: str
    line: int
    kind: str  # "set" or "used"


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def elastic_variables(elastic_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in sorted((elastic_dir / "styles").rglob("*.less")):
        names.update(VAR_DEF_RE.findall(_strip_comments(path.read_text(encoding="utf-8", errors="replace"))))
    return names


def our_variable_refs(less_dir: Path) -> list[VariableRef]:
    """Non-Lumen variables our LESS sets (Elastic overrides) or reads (Elastic breakpoints ...)."""
    refs: list[VariableRef] = []
    for name in LESS_FILES:
        path = less_dir / name
        text = _strip_comments(path.read_text(encoding="utf-8"))
        defined_here = set()
        for m in VAR_DEF_RE.finditer(text):
            var = m.group(1)
            if var.startswith("lm-") or var in NOT_VARIABLES:
                continue
            defined_here.add(var)
            refs.append(VariableRef(var, f"src/less/{name}", text.count("\n", 0, m.start()) + 1, "set"))
        for m in VAR_USE_RE.finditer(text):
            var = m.group(1)
            if var.startswith("lm-") or var in NOT_VARIABLES or var in defined_here:
                continue
            # skip definitions (the regex also sees "@name:" itself)
            after = text[m.end():m.end() + 2].lstrip()
            if after.startswith(":") and not m.group(0).startswith("@{"):
                continue
            refs.append(VariableRef(var, f"src/less/{name}", text.count("\n", 0, m.start()) + 1, "used"))
    return refs


def check_drift(rc: Roundcube, sources: Sources) -> None:
    """Raise DriftError listing every missing file, marker or variable."""
    elastic = rc.elastic_dir
    problems: list[str] = []
    for rel, why in REQUIRED_FILES:
        if not (elastic / rel).is_file():
            problems.append(f"skins/elastic/{rel} is missing ({why})")
    for rel, why in MUST_NOT_EXIST:
        if (elastic / rel).exists():
            problems.append(f"skins/elastic/{rel} exists now: {why}")
    if not ((elastic / "ui.js").is_file() or (elastic / "ui.min.js").is_file()):
        problems.append("skins/elastic/ui.js is missing (Elastic's UI script, which lumen.js prepares)")
    for rel, marker, why in MARKERS:
        path = elastic / rel
        if path.is_file() and marker not in path.read_text(encoding="utf-8", errors="replace"):
            problems.append(f"skins/elastic/{rel} no longer contains {marker!r} ({why})")
    if (elastic / "styles").is_dir():
        known = elastic_variables(elastic)
        seen: set[tuple[str, str]] = set()
        for ref in our_variable_refs(sources.less_dir):
            if ref.name in known or (ref.name, ref.kind) in seen:
                continue
            seen.add((ref.name, ref.kind))
            verb = "sets" if ref.kind == "set" else "uses"
            problems.append(f"Elastic no longer defines @{ref.name}, which {ref.file}:{ref.line} {verb}")
    if problems:
        raise DriftError("the installed Elastic skin changed in a way Lumen does not support yet", problems)
