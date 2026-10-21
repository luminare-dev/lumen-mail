"""Where the build finds its own inputs.

The same layout is used in a git checkout and in the runtime copy that install-runtime writes
(for example /opt/lumen-mail), so the sync job never depends on the checkout:

    <root>/version.txt                 project version (release-please)
    <root>/LICENSE, NOTICE, THIRD_PARTY_NOTICES.md   copied into every build
    <root>/src/less/                   our LESS: tokens, Elastic variable overrides, component layer
    <root>/skin/                       our static skin files (templates, images, fonts, ...)
    <root>/palette/dist/lumen-palette.js   the built command palette (required; npm run build:palette,
                                           or --palette FILE, e.g. from a release package); in a
                                           checkout (with palette/src) it must have been built from
                                           that checkout's sources (palette_inputs_digest)
    <root>/node_modules/               the pinned compiler (less, clean-css)
    <root>/generator/lumen_mail/       this package (compile.mjs lives next to the Python files)

Every location can be overridden: --source / LUMEN_MAIL_SOURCE for the root, --node-modules /
LUMEN_MAIL_NODE_MODULES, --palette / LUMEN_MAIL_PALETTE.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .util import LumenError, tree_digest

PACKAGE_DIR = Path(__file__).resolve().parent

LESS_FILES = ("lumen-tokens.less", "lumen-variables.less", "lumen.less", "lumen-embed.less")

# What the palette bundle is built from; the same list and digest as scripts/palette-inputs.mjs,
# which writes it into the bundle's banner ("sources sha256:<hex>").
PALETTE_INPUTS = ("palette/src", "palette/vite.config.js", "package.json")
PALETTE_DEFAULT = Path("palette") / "dist" / "lumen-palette.js"
_BANNER_DIGEST = re.compile(r"\bsources (sha256:[0-9a-f]{64})\b")


def palette_inputs_digest(root: Path) -> str:
    """sha256 over the palette's inputs in a checkout: "<path>\\0<sha256>\\n" per file, sorted by path."""
    found: list[str] = []
    for rel in PALETTE_INPUTS:
        path = root / rel
        if path.is_file():
            found.append(rel)
        elif path.is_dir():
            found += [p.relative_to(root).as_posix() for p in path.rglob("*") if p.is_file()]
    outer = hashlib.sha256()
    for rel in sorted(found):
        inner = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        outer.update(f"{rel}\0{inner}\n".encode("utf-8"))
    return "sha256:" + outer.hexdigest()


def bundle_digest(bundle: Path) -> str | None:
    """The "sources sha256:..." named in a palette bundle's banner, if any."""
    with bundle.open("rb") as fh:
        head = fh.read(1024).decode("utf-8", "replace")
    end = head.find("*/")
    match = _BANNER_DIGEST.search(head[: end if end >= 0 else len(head)])
    return match.group(1) if match else None


@dataclass(frozen=True)
class Sources:
    root: Path
    node_modules: Path = field(default=None)  # type: ignore[assignment]
    palette: Path = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.node_modules is None:
            object.__setattr__(self, "node_modules", self.root / "node_modules")
        if self.palette is None:
            object.__setattr__(self, "palette", self.root / "palette" / "dist" / "lumen-palette.js")

    @classmethod
    def locate(cls, root: str | os.PathLike | None = None, node_modules: str | os.PathLike | None = None,
               palette: str | os.PathLike | None = None) -> "Sources":
        root = root or os.environ.get("LUMEN_MAIL_SOURCE") or PACKAGE_DIR.parent.parent
        node_modules = node_modules or os.environ.get("LUMEN_MAIL_NODE_MODULES")
        palette = palette or os.environ.get("LUMEN_MAIL_PALETTE")
        return cls(Path(root).resolve(),
                   Path(node_modules).resolve() if node_modules else None,  # type: ignore[arg-type]
                   Path(palette).resolve() if palette else None)  # type: ignore[arg-type]

    @property
    def less_dir(self) -> Path:
        return self.root / "src" / "less"

    @property
    def skin_dir(self) -> Path:
        return self.root / "skin"

    @property
    def compile_script(self) -> Path:
        return PACKAGE_DIR / "compile.mjs"

    @property
    def version(self) -> str:
        path = self.root / "version.txt"
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise LumenError(f"cannot read the project version from {path}: {exc.strerror}") from exc
        if not value:
            raise LumenError(f"{path} is empty")
        return value

    def check(self) -> None:
        wanted = [self.less_dir / name for name in LESS_FILES] + [self.skin_dir / "meta.json"]
        wanted += [self.root / name for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")]
        missing = [str(p) for p in wanted if not p.is_file()]
        if missing:
            raise LumenError(f"the lumen-mail sources at {self.root} are incomplete", [f"missing {m}" for m in missing])

    def require_palette(self) -> None:
        if not self.palette.is_file():
            raise LumenError(f"the command palette bundle {self.palette} is missing (every build includes it)", [
                "build it in the lumen-mail checkout: npm ci --ignore-scripts --no-audit --no-fund && "
                "npm run build:palette",
                "or use the lumen-palette.js of a release package of the same version: --palette FILE "
                "(or $LUMEN_MAIL_PALETTE)",
            ])
        stale = self.stale_palette()
        if stale:
            raise LumenError(f"the command palette bundle {self.palette} is out of date: {stale}", [
                "rebuild it in this checkout: npm run build:palette",
                "a bundle given with --palette FILE (or $LUMEN_MAIL_PALETTE) is taken as it is",
            ])

    def stale_palette(self) -> str | None:
        """Why the default bundle of a checkout does not match the checkout's palette sources.

        Only for <root>/palette/dist/lumen-palette.js next to palette/src: a runtime copy (which
        has no palette sources) and a bundle given explicitly are taken as they are.
        """
        if self.palette != self.root / PALETTE_DEFAULT or not (self.root / "palette" / "src").is_dir():
            return None
        built = bundle_digest(self.palette)
        if built is None:
            return "its banner names no source digest (built by an older lumen-mail)"
        current = palette_inputs_digest(self.root)
        if built != current:
            return f"built from other sources ({built[:19]}...) than this checkout's ({current[:19]}...)"
        return None

    def digest(self) -> str:
        """sha256 over everything the build reads from us (detects a changed runtime copy)."""
        patterns = ["version.txt", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "src/less/*.less", "skin/**/*",
                    "generator/lumen_mail/*.py", "generator/lumen_mail/compile.mjs"]
        digest = tree_digest(self.root, patterns)
        if self.palette.is_file():
            h = hashlib.sha256((digest + "\0").encode())
            h.update(self.palette.read_bytes())
            digest = "sha256:" + h.hexdigest()
        return digest
