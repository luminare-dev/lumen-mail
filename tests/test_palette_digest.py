"""The command palette bundle must match the sources of the checkout a build is made from.

palette/vite.config.js writes the digest of the palette's inputs into the bundle's banner
(scripts/palette-inputs.mjs); the generator recomputes it (lumen_mail.sources) and refuses a
stale bundle, so `npm run build:palette` cannot be forgotten after a change to the palette.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fake_roundcube import ROOT

sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail.sources import PALETTE_DEFAULT, Sources, bundle_digest, palette_inputs_digest  # noqa: E402
from lumen_mail.util import LumenError  # noqa: E402

NODE = shutil.which("node")


def bundle_text(digest: str | None) -> str:
    sources = f" | sources {digest}" if digest else ""
    return f"/*! lumen-mail 0.0.0 command palette | MIT{sources} */\n(function(){{}})();\n"


class PaletteDigestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lumen-digest-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "checkout"
        for rel, text in {
            "palette/src/main.ts": "start();\n",
            "palette/src/deep/Palette.tsx": "export const x = 1;\n",
            "palette/vite.config.js": "export default {};\n",
            "package.json": '{"name": "lumen-mail"}\n',
            "README.md": "not an input\n",
        }.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.bundle = self.root / PALETTE_DEFAULT
        self.bundle.parent.mkdir(parents=True)

    def write_bundle(self, digest: str | None) -> None:
        self.bundle.write_text(bundle_text(digest), encoding="utf-8")

    def test_a_bundle_built_from_these_sources_is_accepted(self):
        self.write_bundle(palette_inputs_digest(self.root))
        Sources(self.root).require_palette()

    def test_a_changed_source_makes_the_bundle_stale(self):
        self.write_bundle(palette_inputs_digest(self.root))
        (self.root / "palette/src/deep/Palette.tsx").write_text("export const x = 2;\n", encoding="utf-8")
        with self.assertRaises(LumenError) as ctx:
            Sources(self.root).require_palette()
        text = ctx.exception.render()
        self.assertIn("out of date", text)
        self.assertIn("npm run build:palette", text)

    def test_the_build_config_and_package_json_count_other_files_do_not(self):
        before = palette_inputs_digest(self.root)
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")
        self.assertEqual(palette_inputs_digest(self.root), before)
        for rel in ("palette/vite.config.js", "package.json"):
            (self.root / rel).write_text("changed\n", encoding="utf-8")
            self.assertNotEqual(palette_inputs_digest(self.root), before, rel)
            before = palette_inputs_digest(self.root)

    def test_a_bundle_without_a_digest_is_refused(self):
        self.write_bundle(None)
        with self.assertRaises(LumenError) as ctx:
            Sources(self.root).require_palette()
        self.assertIn("names no source digest", ctx.exception.render())

    def test_only_the_banner_counts(self):
        self.bundle.write_text("/*! lumen-mail */\nvar s = 'sources sha256:" + "0" * 64 + "';\n", encoding="utf-8")
        self.assertIsNone(bundle_digest(self.bundle))

    def test_an_explicit_bundle_is_taken_as_it_is(self):
        other = self.tmp / "release" / "lumen-palette.js"
        other.parent.mkdir()
        other.write_text(bundle_text(None), encoding="utf-8")
        Sources(self.root, palette=other).require_palette()

    def test_a_runtime_copy_without_palette_sources_is_taken_as_it_is(self):
        self.write_bundle(None)
        shutil.rmtree(self.root / "palette" / "src")
        Sources(self.root).require_palette()

    @unittest.skipUnless(NODE, "node is not on the PATH")
    def test_node_and_python_compute_the_same_digest(self):
        script = ROOT / "scripts" / "palette-inputs.mjs"
        for root in (self.root, ROOT):
            out = subprocess.run([NODE, str(script), str(root)], check=True, capture_output=True, text=True,
                                 timeout=60).stdout.strip()
            self.assertEqual(out, palette_inputs_digest(root), root)


if __name__ == "__main__":
    unittest.main()
