"""Where the build finds its own inputs.

The same layout is used in a git checkout and in the runtime copy that install-runtime writes
(for example /opt/lumen-mail), so the sync job never depends on the checkout:

    <root>/version.txt                 project version (release-please)
    <root>/src/less/                   our LESS: tokens, Elastic variable overrides, component layer
    <root>/skin/                       our static skin files (templates, images, fonts, ...)
    <root>/palette/dist/lumen-palette.js   the built command palette (optional, see --no-palette)
    <root>/node_modules/               the pinned compiler (less, clean-css)
    <root>/generator/lumen_mail/       this package (compile.mjs lives next to the Python files)

Every location can be overridden: --source / LUMEN_MAIL_SOURCE for the root, --node-modules /
LUMEN_MAIL_NODE_MODULES, --palette / LUMEN_MAIL_PALETTE.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from .util import LumenError, tree_digest

PACKAGE_DIR = Path(__file__).resolve().parent

LESS_FILES = ("lumen-tokens.less", "lumen-variables.less", "lumen.less", "lumen-embed.less")


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
        missing = [str(p) for p in [self.less_dir / name for name in LESS_FILES] + [self.skin_dir / "meta.json"]
                   if not p.is_file()]
        if missing:
            raise LumenError(f"the lumen-mail sources at {self.root} are incomplete", [f"missing {m}" for m in missing])

    def digest(self, include_palette: bool) -> str:
        """sha256 over everything the build reads from us (detects a changed runtime copy)."""
        patterns = ["version.txt", "src/less/*.less", "skin/**/*", "generator/lumen_mail/*.py",
                    "generator/lumen_mail/compile.mjs"]
        digest = tree_digest(self.root, patterns)
        if include_palette and self.palette.is_file():
            h = hashlib.sha256((digest + "\0").encode())
            h.update(self.palette.read_bytes())
            digest = "sha256:" + h.hexdigest()
        return digest
