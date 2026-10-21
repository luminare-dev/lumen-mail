"""Integration test: the REAL compile (Node, less, clean-css) against a real Elastic skin.

Runs when node_modules has less and clean-css and a Roundcube tree is available:
  * LUMEN_MAIL_TEST_ROUNDCUBE: the Roundcube root (default /home/keyhelp/www/roundcube; CI uses
    the sha256-pinned release archive), read only;
  * LUMEN_MAIL_TEST_OUT: where the build goes (default a new folder under /var/tmp/lumen-mail when
    that exists, else the system temp dir); removed afterwards unless LUMEN_MAIL_TEST_KEEP=1;
  * LUMEN_MAIL_TEST_REQUIRE=1 turns the skip into a failure (CI).
On a small host, run it with a memory limit (the systemd-run line in docs/install.md).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail.build import BuildOptions, build  # noqa: E402
from lumen_mail.compiler import CompileJob, compiler_command, run_compiler  # noqa: E402
from lumen_mail.cssurls import iter_urls  # noqa: E402
from lumen_mail.roundcube import Roundcube  # noqa: E402
from lumen_mail.sources import Sources  # noqa: E402
from lumen_mail.verify import verify  # noqa: E402

RC_ROOT = Path(os.environ.get("LUMEN_MAIL_TEST_ROUNDCUBE", "/home/keyhelp/www/roundcube"))
NODE_MODULES = ROOT / "node_modules"


def why_not() -> str | None:
    if not (NODE_MODULES / "less" / "package.json").is_file() or not (NODE_MODULES / "clean-css").is_dir():
        return "node_modules has no less/clean-css (run npm ci --ignore-scripts)"
    if shutil.which(os.environ.get("LUMEN_MAIL_NODE", "node")) is None:
        return "node is not on the PATH"
    if not (RC_ROOT / "skins" / "elastic" / "styles" / "styles.less").is_file():
        return f"no Elastic LESS sources under {RC_ROOT}"
    return None


REASON = why_not()
if REASON and os.environ.get("LUMEN_MAIL_TEST_REQUIRE") == "1":
    raise RuntimeError(f"integration test required but not runnable: {REASON}")


def out_base() -> Path:
    if os.environ.get("LUMEN_MAIL_TEST_OUT"):
        return Path(os.environ["LUMEN_MAIL_TEST_OUT"])
    scratch = Path("/var/tmp/lumen-mail")
    return scratch if scratch.is_dir() and os.access(scratch, os.W_OK) else Path(tempfile.gettempdir())


@unittest.skipIf(REASON, REASON or "")
class RealCompileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base = out_base()
        base.mkdir(parents=True, exist_ok=True)
        cls.work = Path(tempfile.mkdtemp(prefix="it-", dir=base))
        cls.rc = Roundcube.at(RC_ROOT)
        # The real palette bundle when it was built (or $LUMEN_MAIL_PALETTE), else the test stub.
        palette = None if os.environ.get("LUMEN_MAIL_PALETTE") or (ROOT / "palette/dist/lumen-palette.js").is_file() \
            else ROOT / "tests/fixtures/lumen-palette.js"
        cls.sources = Sources.locate(ROOT, palette=palette)
        cls.result = build(BuildOptions(roundcube=RC_ROOT, out=cls.work / "lumen", sources=cls.sources, quiet=True))
        cls.min_css = (cls.result.out / "styles/styles.min.css").read_text(encoding="utf-8")
        report = {"roundcube": cls.rc.version(), "sizes": cls.result.sizes,
                  "compiler": cls.result.stamp.get("compiler")}
        (cls.work / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\n[integration] Roundcube {report['roundcube']}, compiler {report['compiler']}", file=sys.stderr)
        for rel, size in sorted(cls.result.sizes.items()):
            print(f"[integration] {rel}: {size} bytes", file=sys.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        if os.environ.get("LUMEN_MAIL_TEST_KEEP") != "1":
            shutil.rmtree(cls.work, ignore_errors=True)
        else:
            print(f"[integration] kept {cls.work}", file=sys.stderr)

    def test_verify_passes(self):
        self.assertEqual(verify(self.result.out, self.rc, self.sources), [])

    def test_every_url_points_into_the_two_skins_with_a_cache_buster(self):
        urls = [u for u in iter_urls(self.min_css) if u.is_local]
        self.assertTrue(urls)
        for u in urls:
            path, query, _ = u.parts()
            self.assertTrue(path.startswith(("../fonts/", "../images/", "../../elastic/")), u.value)
            self.assertRegex(query, r"(^|&)v=[0-9a-f]{10}$", u.value)
        self.assertTrue(any(u.value.startswith("../fonts/Sora-Variable.woff?v=") for u in urls))
        self.assertTrue(any(u.value.startswith("../../elastic/fonts/fa-solid-900.woff2?v=") for u in urls))

    def test_sora_replaces_roboto(self):
        # clean-css keeps Elastic's "font-family: Roboto, sans-serif" in front of ours (the Sora
        # stack has the vendor-like -apple-system), so check what each rule finally applies:
        # the last !important declaration, else the last one.
        effective = {}
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", self.min_css):
            if selector.strip().startswith("@font-face"):
                continue
            decls = re.findall(r"font-family:([^;}]+)", body)
            if not decls:
                continue
            important = [d for d in decls if d.rstrip().endswith("!important")]
            effective[selector.strip()] = (important or decls)[-1]
        self.assertTrue(effective)
        roboto = {s: f for s, f in effective.items() if f.startswith(("Roboto", "'Roboto'", '"Roboto"'))}
        self.assertEqual(roboto, {}, "rules whose effective font is Roboto")
        body = [f for s, f in effective.items() if "body" in s.split(",")]
        self.assertTrue(body and body[0].startswith(("Sora", '"Sora"')), body)

    def test_tokens_reach_the_css(self):
        css = self.min_css.lower()
        self.assertIn("--lm-bg:#f3f6fb", css)
        self.assertRegex(css, r"html\.dark-mode\{[^}]*--lm-bg:#0a1224")
        self.assertIn("#1f47c4", css)  # Royal, Elastic's @color-main now
        self.assertNotIn("#37beff", css, "Elastic's main colour is still in the compiled CSS")

    def test_banner_and_licence(self):
        for rel in ("styles/styles.css", "styles/styles.min.css", "styles/embed.css", "styles/embed.min.css"):
            head = (self.result.out / rel).read_text(encoding="utf-8")[:1200]
            self.assertIn("licensed under CC BY-SA 3.0", head, rel)
            self.assertIn("Aleksander Machniak and The Roundcube Dev Team", head, rel)

    def test_elastic_alone_compiles_like_the_shipped_stylesheet(self):
        """Toolchain parity: our less + clean-css on Elastic's unmodified styles.less gives about
        as many rules as Elastic's own shipped styles.min.css."""
        tmp = self.work / "parity"
        tmp.mkdir()
        entry = tmp / "entry.less"
        entry.write_text(f'@import "{(RC_ROOT / "skins/elastic/styles/styles.less").as_posix()}";\n', encoding="utf-8")
        run_compiler(compiler_command(self.sources), [CompileJob(entry, tmp / "e.css", tmp / "e.min.css")], NODE_MODULES)
        ours = (tmp / "e.min.css").read_text(encoding="utf-8").count("{")
        shipped = (RC_ROOT / "skins/elastic/styles/styles.min.css").read_text(encoding="utf-8").count("{")
        print(f"\n[integration] parity: {ours} blocks from our toolchain, {shipped} in Elastic's styles.min.css",
              file=sys.stderr)
        self.assertLess(abs(ours - shipped) / shipped, 0.05)


if __name__ == "__main__":
    unittest.main()
