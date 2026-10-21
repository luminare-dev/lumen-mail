"""Read-only facts about a Roundcube installation (version, Elastic sources, served file types).

Nothing here writes to the Roundcube tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import PARENT_SKIN, SKIN_NAME
from .util import LumenError, tree_digest

VERSION_RE = re.compile(r"""define\(\s*['"]RCMAIL_VERSION['"]\s*,\s*['"]([^'"]+)['"]\s*\)""")
SUPPORTED_TYPES_RE = re.compile(r"SUPPORTED_TYPES\s*=\s*\[(.*?)\];", re.DOTALL)
TYPE_KEY_RE = re.compile(r"""['"]([a-z0-9]+)['"]\s*=>""")
# What Elastic's look depends on: its LESS sources and templates (stamp: elastic_digest).
ELASTIC_DIGEST_PATTERNS = ("styles/**/*.less", "templates/**/*")


@dataclass(frozen=True)
class Roundcube:
    root: Path

    @classmethod
    def at(cls, root: str | Path) -> "Roundcube":
        rc = cls(Path(root).resolve())
        rc.check()
        return rc

    @property
    def iniset(self) -> Path:
        return self.root / "program" / "include" / "iniset.php"

    @property
    def skins_dir(self) -> Path:
        return self.root / "skins"

    @property
    def elastic_dir(self) -> Path:
        return self.skins_dir / PARENT_SKIN

    @property
    def skin_dir(self) -> Path:
        """Where our skin lives once installed."""
        return self.skins_dir / SKIN_NAME

    def check(self) -> None:
        problems = []
        if not self.iniset.is_file():
            problems.append(f"{self.iniset} is missing (is {self.root} a Roundcube root?)")
        if not self.elastic_dir.is_dir():
            problems.append(f"{self.elastic_dir} is missing (Lumen extends the Elastic skin)")
        if problems:
            raise LumenError(f"{self.root} is not a usable Roundcube installation", problems)

    def version(self) -> str:
        try:
            text = self.iniset.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise LumenError(f"cannot read {self.iniset}: {exc.strerror}") from exc
        m = VERSION_RE.search(text)
        if not m:
            raise LumenError(f"cannot find RCMAIL_VERSION in {self.iniset}")
        return m.group(1)

    def elastic_digest(self) -> str:
        return tree_digest(self.elastic_dir, ELASTIC_DIGEST_PATTERNS)

    def static_types(self) -> set[str] | None:
        """File extensions public_html/static.php serves (Roundcube 1.7+), or None without it.

        Skin assets are served through static.php in 1.7; a url() to any other type answers 404.
        """
        path = self.root / "public_html" / "static.php"
        if not path.is_file():
            return None
        m = SUPPORTED_TYPES_RE.search(path.read_text(encoding="utf-8", errors="replace"))
        if not m:
            return None
        types = set(TYPE_KEY_RE.findall(m.group(1)))
        return types or None
