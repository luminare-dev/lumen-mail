"""Tests for install-runtime: the self-contained copy the sync unit runs from."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail.log import Log  # noqa: E402
from lumen_mail.runtime import MANIFEST, compiler_closure, install_runtime  # noqa: E402
from lumen_mail.sources import Sources  # noqa: E402
from lumen_mail.util import LumenError  # noqa: E402

PINS = json.loads((ROOT / "package.json").read_text())["dependencies"]
STUB_PALETTE = ROOT / "tests" / "fixtures" / "lumen-palette.js"


def pkg(base: Path, name: str, version: str = "1.0.0", deps: dict | None = None, optional: dict | None = None) -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "package.json").write_text(json.dumps({"name": name, "version": version, "dependencies": deps or {},
                                                "optionalDependencies": optional or {}}))
    (d / "index.js").write_text(f"// {name}\n")
    return d


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lumen-mail-runtime-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        nm = self.tmp / "node_modules"
        less = pkg(nm, "less", PINS["less"], {"tslib": "^2", "copy-anything": "^2"}, {"mime": "^1", "needle": "^3"})
        pkg(nm, "tslib")
        pkg(nm, "copy-anything", deps={"is-what": "^3"})
        pkg(less / "node_modules", "left-pad")      # nested, but nothing in the closure needs it
        pkg(nm, "is-what", "3.0.0")
        pkg(nm, "mime")
        pkg(nm, "clean-css", PINS["clean-css"], {"source-map": "~0.6"})
        pkg(nm, "source-map")
        pkg(nm, "react")                              # a dev dependency: must not be copied
        (nm / ".bin").mkdir()
        self.sources = Sources(ROOT, node_modules=nm, palette=STUB_PALETTE)
        self.prefix = self.tmp / "opt" / "lumen-mail"

    def install(self, **kw) -> int:
        with redirect_stdout(io.StringIO()):
            return install_runtime(self.sources, self.prefix, Log(stream=io.StringIO()), owner=None, **kw)

    def test_closure_follows_node_lookup(self):
        found = {p.relative_to((self.tmp / "node_modules").resolve()).as_posix()
                 for p in compiler_closure(self.tmp / "node_modules")}
        self.assertEqual(found, {"less", "tslib", "copy-anything", "is-what", "mime", "clean-css", "source-map"})
        self.assertFalse(any("left-pad" in f for f in found))
        self.assertNotIn("react", found)
        self.assertNotIn("needle", found, "a missing optional dependency is skipped")

    def test_missing_required_package_fails(self):
        shutil.rmtree(self.tmp / "node_modules" / "tslib")
        with self.assertRaises(LumenError):
            compiler_closure(self.tmp / "node_modules")

    def test_install_and_replace(self):
        self.assertEqual(self.install(), 0)
        manifest = json.loads((self.prefix / MANIFEST).read_text())
        self.assertEqual(manifest["lumen_version"], (ROOT / "version.txt").read_text().strip())
        for rel in ("version.txt", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "package.json", "src/less/lumen.less", "skin/meta.json",
                    "generator/lumen_mail/lifecycle.py", "generator/lumen_mail/compile.mjs",
                    "node_modules/less/package.json", "node_modules/clean-css/package.json"):
            self.assertTrue((self.prefix / rel).is_file(), rel)
            self.assertIn(rel, manifest["files"])
        self.assertFalse((self.prefix / "node_modules" / "react").exists())
        self.assertEqual((self.prefix / "palette" / "dist" / "lumen-palette.js").read_bytes(), STUB_PALETTE.read_bytes())
        self.assertTrue(manifest["palette"])
        self.assertIn("palette/dist/lumen-palette.js", manifest["files"])
        self.assertTrue(list((self.prefix / "generator" / "lumen_mail" / "__pycache__").glob("lifecycle.*.pyc")))
        wrapper = self.prefix / "bin" / "lumen-mail"
        self.assertTrue(os.access(wrapper, os.X_OK))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("LUMEN_MAIL_", "PYTHON"))}
        out = subprocess.run([str(wrapper), "--version"], capture_output=True, text=True, env=env, timeout=60,
                             cwd=self.tmp, check=True).stdout
        self.assertIn(f"({self.prefix})", out, "the wrapper must run the generator of the runtime")
        # the runtime finds its sources without options
        src = Sources.locate(self.prefix)
        src.check()
        self.assertEqual(src.version, manifest["lumen_version"])
        first = manifest["installed_at"]
        self.assertEqual(self.install(), 0)
        self.assertTrue((self.prefix / MANIFEST).is_file())
        self.assertEqual([p.name for p in self.prefix.parent.iterdir()], ["lumen-mail"], "no staging leftovers")
        self.assertIsNotNone(first)

    def test_refuses_a_foreign_folder(self):
        self.prefix.mkdir(parents=True)
        (self.prefix / "something").write_text("x")
        with self.assertRaises(LumenError):
            self.install()
        self.assertEqual(self.install(force=True), 0)

    def test_pin_mismatch_fails(self):
        meta = self.tmp / "node_modules" / "less" / "package.json"
        data = json.loads(meta.read_text())
        data["version"] = "0.0.1"
        meta.write_text(json.dumps(data))
        with self.assertRaises(LumenError) as ctx:
            self.install()
        self.assertIn("pins", str(ctx.exception))

    def test_dry_run_writes_nothing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            install_runtime(self.sources, self.prefix, Log(stream=io.StringIO()), dry_run=True, owner=None)
        self.assertIn("dry run", out.getvalue())
        self.assertFalse(self.prefix.exists())

    def test_the_prebuilt_palette_is_required(self):
        # sync rebuilds from the runtime and never runs Vite: the runtime must carry the bundle.
        self.sources = Sources(ROOT, node_modules=self.tmp / "node_modules", palette=self.tmp / "missing.js")
        with self.assertRaises(LumenError) as ctx:
            self.install()
        self.assertIn("command palette bundle", ctx.exception.render())
        self.assertFalse(self.prefix.exists())


if __name__ == "__main__":
    unittest.main()
