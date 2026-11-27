"""Customizations: checking a customizer ZIP, building with it, apply-custom (fake Roundcube, stub compiler)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from fake_roundcube import ROOT, FakeTreeCase

sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail import STAMP_NAME, custom  # noqa: E402
from lumen_mail.apply import apply_custom  # noqa: E402
from lumen_mail.build import BuildOptions, build  # noqa: E402
from lumen_mail.lifecycle import Lifecycle  # noqa: E402
from lumen_mail.log import Log  # noqa: E402
from lumen_mail.roundcube import Roundcube  # noqa: E402
from lumen_mail.sources import Sources  # noqa: E402
from lumen_mail.state import StatePaths  # noqa: E402
from lumen_mail.verify import verify  # noqa: E402

IMAGES = ROOT / "skin" / "images"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="10"><rect width="40" height="10"/></svg>\n'
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
LESS = ("// Lumen tokens v1: Test\n// generated\n@lm-royal: #123456;\n@lm-abyss: mix(#123456, #000000, 70%);\n"
        "@lm-radius-m: 9px;\n@lm-font: ~'\"Inter\", system-ui, sans-serif';\n")
CSS = "/* Lumen tokens v1: Test */\n:root {\n    --lumen-accent: #123456;\n}\n/* custom marker */\n"


def make_custom(folder: Path, **branding: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "lumen.tokens.json").write_text(json.dumps({"version": 1, "meta": {"name": "Test"}}), encoding="utf-8")
    (folder / "lumen-custom.less").write_text(LESS, encoding="utf-8")
    (folder / "lumen-custom.css").write_text(CSS, encoding="utf-8")
    (folder / "custom").mkdir()
    (folder / "custom" / "logo.svg").write_bytes(SVG)
    (folder / "custom" / "fav.png").write_bytes(PNG)
    values = {"app": "/images/custom/logo.svg", "login": "/images/custom/logo.svg", "compact": "/images/custom/logo.svg",
              "favicon": "/images/custom/fav.png", "productName": "Example Mail", "themeLight": "#FFFFFF",
              "themeDark": "#000000"}
    values.update(branding)
    (folder / "branding.json").write_text(json.dumps(values), encoding="utf-8")
    return folder


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lumen-mail-custom-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_a_good_folder_loads(self):
        c = custom.load(make_custom(self.tmp / "c"), IMAGES)
        self.assertEqual((c.name, c.media), ("Test", ("fav.png", "logo.svg")))
        self.assertTrue(c.sha256.startswith("sha256:"))

    def test_less_may_only_set_variables(self):
        for bad in ('@import "/etc/passwd";', "@plugin \"x\";", "@lm-x: ~`1+1`;", ".a { color: red; }",
                    "@lm-x: data-uri('/etc/hostname');", "@color-main: #123456;"):
            folder = make_custom(self.tmp / f"c{abs(hash(bad))}")
            (folder / "lumen-custom.less").write_text(LESS + bad + "\n", encoding="utf-8")
            with self.assertRaises(custom.CustomError, msg=bad):
                custom.load(folder, IMAGES)

    def test_branding_must_name_skin_files(self):
        folder = make_custom(self.tmp / "c", app="https://x.example/logo.png", login="/images/nope.svg",
                             compact="/images/custom/missing.png", themeDark="black")
        with self.assertRaises(custom.CustomError) as ctx:
            custom.load(folder, IMAGES)
        self.assertEqual(len(ctx.exception.problems), 4)

    def test_svg_with_script_and_wrong_types_are_refused(self):
        folder = make_custom(self.tmp / "c")
        (folder / "custom" / "logo.svg").write_bytes(b"<svg onload=\"x()\"></svg>")
        (folder / "custom" / "fav.png").write_bytes(b"GIF89a")
        with self.assertRaises(custom.CustomError) as ctx:
            custom.load(folder, IMAGES)
        self.assertEqual(len(ctx.exception.problems), 2)

    def test_zip_paths_are_not_trusted(self):
        bad = self.tmp / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("x/../../evil.txt", "x")
        dest = self.tmp / "out"
        dest.mkdir()
        with self.assertRaises(custom.CustomError):
            custom.extract_zip(bad, dest)
        self.assertFalse((self.tmp / "evil.txt").exists())


class BuildWithCustomTest(FakeTreeCase):
    def build_with(self, folder: Path | None, out_name: str = "out/lumen"):
        sources = Sources.locate(ROOT, custom=folder)
        return build(BuildOptions(roundcube=self.rc, out=self.tmp / out_name, sources=sources,
                                  compiler=self.compiler, quiet=True)), sources

    def test_the_build_uses_the_customization(self):
        folder = make_custom(self.tmp / "c")
        result, sources = self.build_with(folder)
        out = result.out
        css = (out / "styles/styles.css").read_text(encoding="utf-8")
        self.assertIn("/* custom marker */", css)
        self.assertNotIn("/* custom marker */", (out / "styles/embed.css").read_text(encoding="utf-8"))
        self.assertEqual((out / "images/custom/logo.svg").read_bytes(), SVG)
        footer = (out / "templates/includes/footer.html").read_text(encoding="utf-8")
        self.assertIn('data-src-app="/images/custom/logo.svg"', footer)
        self.assertIn('data-theme-dark="#000000"', footer)
        self.assertIn('data-alt="Example Mail"', footer)
        meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["config"]["favicon"], "/images/custom/fav.png")
        stamp = json.loads((out / STAMP_NAME).read_text(encoding="utf-8"))
        self.assertEqual(stamp["custom"]["name"], "Test")
        self.assertFalse(list(out.rglob("*.less")))
        self.assertEqual(verify(out, Roundcube.at(self.rc), sources), [])

    def test_empty_logos_keep_elastics_logo(self):
        folder = make_custom(self.tmp / "c", app="", login="", compact="", favicon="")
        result, _ = self.build_with(folder)
        footer = (result.out / "templates/includes/footer.html").read_text(encoding="utf-8")
        self.assertNotIn("data-src-", footer)
        self.assertNotIn("favicon", json.loads((result.out / "meta.json").read_text())["config"])

    def test_a_customization_changes_the_source_digest(self):
        plain = Sources.locate(ROOT).digest()
        folder = make_custom(self.tmp / "c")
        with_custom = Sources.locate(ROOT, custom=folder).digest()
        self.assertNotEqual(plain, with_custom)
        self.assertEqual(plain, Sources.locate(ROOT, custom=self.tmp / "missing").digest())
        (folder / "lumen-custom.css").write_text(CSS + "/* x */\n", encoding="utf-8")
        self.assertNotEqual(with_custom, Sources.locate(ROOT, custom=folder).digest())


class ApplyCustomTest(FakeTreeCase):
    def lifecycle(self, target: Path) -> Lifecycle:
        return Lifecycle(roundcube=self.rc, state=StatePaths(self.tmp / "state"),
                         sources=Sources.locate(ROOT, custom=target), log=Log(quiet=True), owner_spec="",
                         compiler=self.compiler, work_dir=self.tmp / "work")

    def zip_of(self, folder: Path) -> Path:
        dest = self.tmp / "lumen-mail-test.zip"
        with zipfile.ZipFile(dest, "w") as z:
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    z.write(path, "lumen-mail-test/" + path.relative_to(folder).as_posix())
        return dest

    def test_dry_run_then_apply_then_reset(self):
        target = self.tmp / "state" / "custom"
        z = self.zip_of(make_custom(self.tmp / "src"))
        lines: list[str] = []
        self.assertEqual(apply_custom(self.lifecycle(target), z, out=lines.append), 0)
        self.assertIn("nothing was written", lines[-1])
        self.assertFalse(target.exists())
        self.assertFalse((self.rc / "skins/lumen").exists())
        lines.clear()
        self.assertEqual(apply_custom(self.lifecycle(target), z, yes=True, out=lines.append), 0, lines)
        self.assertTrue((target / "custom/logo.svg").is_file())
        self.assertTrue((self.rc / "skins/lumen/images/custom/logo.svg").is_file())
        self.assertIn("apply-custom --reset --yes", lines[-1])
        lines.clear()
        self.assertEqual(apply_custom(self.lifecycle(target), None, reset=True, yes=True, out=lines.append), 0)
        self.assertFalse(target.exists())
        self.assertFalse((self.rc / "skins/lumen/images/custom").exists())
        self.assertEqual(len(list((self.tmp / "state" / "custom-backups").iterdir())), 1)

    def test_a_bad_zip_writes_nothing(self):
        target = self.tmp / "state" / "custom"
        folder = make_custom(self.tmp / "src")
        (folder / "lumen-custom.less").write_text(LESS + '@import "x";\n', encoding="utf-8")
        with self.assertRaises(custom.CustomError):
            apply_custom(self.lifecycle(target), self.zip_of(folder), yes=True, out=lambda _l: None)
        self.assertFalse(target.exists())


class CompilerTest(unittest.TestCase):
    """tokens/compile.mjs output passes the server-side checks, for every preset."""

    def test_compiled_presets_load(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        if tuple(int(x) for x in version.lstrip("v").split(".")[:2]) < (22, 6):
            self.skipTest(f"node {version} cannot strip types")
        tmp = Path(tempfile.mkdtemp(prefix="lumen-mail-compile-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for name in ("luminare", "graphite", "aurora", "contrast"):
            subprocess.run([node, "--experimental-strip-types", "--no-warnings", str(ROOT / "tokens" / "compile.mjs"),
                            "--preset", name, "--out", str(tmp / name)], check=True, capture_output=True)
            c = custom.load(tmp / name, IMAGES)
            self.assertTrue(c.less.startswith("// Lumen tokens v1: "))

    def test_every_role_of_the_skin_is_written(self):
        tokens_less = (ROOT / "src/less/lumen-tokens.less").read_text(encoding="utf-8")
        roles = re.search(r"@lm-roles:(.*?);", tokens_less, re.S).group(1)
        names = {r.strip() for r in roles.replace("\n", " ").split(",")}
        ts = (ROOT / "tokens/roundcube.ts").read_text(encoding="utf-8")
        written = set(re.findall(r"\['([a-z0-9-]+)', ", ts.split("export const BRAND_EXPRS")[0]))
        written |= {f"{p}{s}" for s in ("success", "warning", "danger", "info") for p in ("", "on-")}
        written |= {f"{s}-{k}" for s in ("success", "warning", "danger", "info") for k in ("tint", "text")}
        self.assertEqual(names - written, set())


if __name__ == "__main__":
    unittest.main()
