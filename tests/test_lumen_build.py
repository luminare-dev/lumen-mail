"""Tests for the lumen_mail generator: build and verify against a fake Roundcube tree.

Everything here runs with the Python stand-in compiler (tests/stub_compiler.py), so no Node is
needed. The real compile is in test_lumen_integration.py.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from fake_roundcube import FAKE_VERSION, ROOT, FakeTreeCase, write

sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail import STAMP_NAME  # noqa: E402
from lumen_mail.build import BuildOptions, build  # noqa: E402
from lumen_mail.cli import main as cli_main  # noqa: E402
from lumen_mail.cssurls import iter_urls, rewrite_urls  # noqa: E402
from lumen_mail.elastic import DriftError  # noqa: E402
from lumen_mail.roundcube import Roundcube  # noqa: E402
from lumen_mail.sources import Sources  # noqa: E402
from lumen_mail.cli import parser as cli_parser  # noqa: E402
from lumen_mail.templates import assemble, check_wrapper  # noqa: E402
from lumen_mail.util import LumenError, sha256_file, short_hash  # noqa: E402
from lumen_mail.verify import verify  # noqa: E402

VERSION = (ROOT / "version.txt").read_text(encoding="utf-8").strip()


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli_main(list(argv))
    return code, out.getvalue(), err.getvalue()


class BuildTest(FakeTreeCase):
    def build(self, palette: Path | None = None, out_name: str = "out/lumen"):
        sources = Sources.locate(ROOT, palette=palette)
        return build(BuildOptions(roundcube=self.rc, out=self.tmp / out_name, sources=sources,
                                  compiler=self.compiler, quiet=True))

    def test_build_assembles_the_skin(self):
        result = self.build()
        out = result.out
        for rel in ("meta.json", "README.md", "lumen.js", "watermark.html", "thumbnail.png",
                    "templates/includes/footer.html", "localization/en_US.inc", "localization/de_DE.inc",
                    "fonts/Sora-Variable.woff", "fonts/Sora-OFL.txt", "images/luminare-mark.svg",
                    "styles/styles.css", "styles/styles.min.css", "styles/embed.css", "styles/embed.min.css",
                    "lumen-palette.js", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", STAMP_NAME):
            self.assertTrue((out / rel).is_file(), rel)
        self.assertFalse(list(out.rglob("*.less")), "no LESS source may stay in the skin")
        self.assertEqual(verify(out, Roundcube.at(self.rc), Sources.locate(ROOT)), [])
        meta = json.loads((out / "meta.json").read_text())
        self.assertEqual((meta["name"], meta["extends"], meta["localization"]), ("Lumen", "elastic", True))
        readme = (out / "README.md").read_text()
        self.assertIn(f"Lumen {VERSION}, compiled for Roundcube {FAKE_VERSION}", readme)
        self.assertIn("Aleksander Machniak and The Roundcube Dev Team", readme)
        self.assertNotIn("$", readme)

    def test_the_banner_fits_a_server_build_and_a_release_package(self):
        head = (self.build().out / "styles/styles.min.css").read_text(encoding="utf-8")[:900]
        self.assertIn(" * Compiled from two sources:", head)
        self.assertNotIn("on this server", head, "release packages are compiled in CI")
        self.assertIn("licensed under CC BY-SA 3.0", head)

    def test_stamp_contents(self):
        result = self.build()
        stamp = json.loads((result.out / STAMP_NAME).read_text())
        rc = Roundcube.at(self.rc)
        self.assertEqual(stamp["schema"], 1)
        self.assertEqual(stamp["lumen_version"], VERSION)
        self.assertEqual(stamp["roundcube_version"], FAKE_VERSION)
        self.assertEqual(stamp["elastic_digest"], rc.elastic_digest())
        self.assertTrue(stamp["elastic_digest"].startswith("sha256:"))
        self.assertIs(stamp["palette"], True)
        self.assertRegex(stamp["built_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        files = {p.relative_to(result.out).as_posix() for p in result.out.rglob("*") if p.is_file()}
        self.assertEqual(set(stamp["files"]), files - {STAMP_NAME})
        for rel, digest in stamp["files"].items():
            self.assertEqual(sha256_file(result.out / rel), digest, rel)

    def test_css_urls_get_cache_busters_and_final_paths(self):
        out = self.build().out
        css = (out / "styles/styles.min.css").read_text()
        self.assertIn("This compiled file is an adaptation of Elastic and is licensed under CC BY-SA 3.0.", css)
        urls = {u.value for u in iter_urls(css)}
        font = out / "fonts/Sora-Variable.woff"
        self.assertIn(f"../fonts/Sora-Variable.woff?v={short_hash(font)}", urls)
        fake_font = self.rc / "skins/elastic/fonts/fake.woff2"
        self.assertIn(f"../../elastic/fonts/fake.woff2?v={short_hash(fake_font)}", urls)
        self.assertIn(f"../../elastic/images/fake.svg?v={short_hash(self.rc / 'skins/elastic/images/fake.svg')}", urls)
        # written relative to styles/ inside styles/widgets/, as Elastic does
        icon = self.rc / "skins/elastic/images/fake-icon.svg"
        self.assertIn(f"../../elastic/images/fake-icon.svg?v={short_hash(icon)}", urls)

    def test_elastic_images_are_linked_only_during_the_compile(self):
        out = self.build().out
        self.assertFalse([p for p in out.rglob("*") if p.is_symlink()])
        images = sorted(p.name for p in (out / "images").iterdir())
        self.assertEqual(images, sorted(p.name for p in (ROOT / "skin/images").iterdir()))

    def test_the_palette_is_always_required(self):
        sources = Sources.locate(ROOT, palette=self.tmp / "nowhere.js")
        with self.assertRaises(LumenError) as ctx:
            build(BuildOptions(roundcube=self.rc, out=self.tmp / "x", sources=sources, compiler=self.compiler,
                               quiet=True))
        text = ctx.exception.render()
        self.assertIn("command palette bundle", text)
        self.assertIn("npm run build:palette", text)
        self.assertNotIn("--no-palette", text)
        self.assertFalse((self.tmp / "x").exists())

    def test_no_command_has_an_option_to_leave_the_palette_out(self):
        commands = next(a for a in cli_parser()._actions  # noqa: SLF001
                        if isinstance(a, argparse._SubParsersAction))  # noqa: SLF001
        self.assertIn("build", commands.choices)
        for name, sub in commands.choices.items():
            options = {o for a in sub._actions for o in a.option_strings}  # noqa: SLF001
            self.assertFalse({"--no-palette", "--require-palette"} & options, name)

    def test_footer_loads_the_palette_and_its_labels(self):
        bundle = write(self.tmp / "palette.js", "/*! palette */\n(function(){})();\n")
        out = self.build(palette=bundle).out
        footer = (out / "templates/includes/footer.html").read_text()
        self.assertIn('<script src="/lumen.js"', footer)
        self.assertIn('<script src="/lumen-palette.js" defer></script>', footer)
        self.assertIn('<roundcube:add_label name="lumen.palette_title" />', footer)
        self.assertNotIn("<!--", footer)
        self.assertTrue(footer.rstrip().endswith('<roundcube:include file="includes/footer.html" skinpath="skins/elastic" />'))
        self.assertEqual((out / "lumen-palette.js").read_bytes(), bundle.read_bytes())
        self.assertTrue(json.loads((out / STAMP_NAME).read_text())["palette"])
        self.assertEqual(verify(out, Roundcube.at(self.rc), Sources.locate(ROOT, palette=bundle)), [])

    def test_labels_in_the_footer_exist_in_the_localization(self):
        footer = (ROOT / "skin/templates/includes/footer.html").read_text()
        ours = set(re.findall(r'add_label name="(lumen\.[a-z0-9_]+)"', footer))
        self.assertTrue(ours)
        for lang in ("en_US", "de_DE"):
            text = (ROOT / f"skin/localization/{lang}.inc").read_text()
            defined = set(re.findall(r"\$labels\['(lumen\.[a-z0-9_]+)'\]", text))
            self.assertEqual(ours, defined, lang)

    def test_output_must_be_new_or_empty(self):
        write(self.tmp / "busy/lumen/file.txt", "x")
        with self.assertRaises(LumenError):
            self.build(out_name="busy/lumen")

    def test_no_temporary_files_are_left(self):
        self.build(out_name="clean/lumen")
        self.assertEqual(sorted(p.name for p in (self.tmp / "clean").iterdir()), ["lumen"])

    def test_the_roundcube_tree_is_only_read(self):
        def snapshot() -> dict[str, tuple[str, float]]:
            return {p.relative_to(self.rc).as_posix(): (sha256_file(p), p.stat().st_mtime)
                    for p in self.rc.rglob("*") if p.is_file()}

        before = snapshot()
        self.build()
        self.assertEqual(snapshot(), before)

    def test_without_static_php_the_type_check_is_skipped(self):
        (self.rc / "public_html/static.php").unlink()
        out = self.build().out
        self.assertIsNone(Roundcube.at(self.rc).static_types())
        self.assertEqual(verify(out, Roundcube.at(self.rc), Sources.locate(ROOT)), [])

    def test_not_a_roundcube_root(self):
        with self.assertRaises(LumenError) as ctx:
            Roundcube.at(self.tmp)
        self.assertIn("program/include/iniset.php is missing", ctx.exception.render())


class DriftTest(FakeTreeCase):
    def build(self):
        return build(BuildOptions(roundcube=self.rc, out=self.tmp / "out", sources=Sources.locate(ROOT),
                                  compiler=self.compiler, quiet=True))

    def test_missing_variable_is_named(self):
        colors = self.rc / "skins/elastic/styles/colors.less"
        colors.write_text(colors.read_text().replace("@color-taskmenu-background: #123456;\n", ""))
        with self.assertRaises(DriftError) as ctx:
            self.build()
        text = ctx.exception.render()
        self.assertIn("Elastic no longer defines @color-taskmenu-background", text)
        self.assertIn("src/less/lumen-variables.less:", text)

    def test_missing_file_is_named(self):
        (self.rc / "skins/elastic/templates/includes/footer.html").unlink()
        with self.assertRaises(DriftError) as ctx:
            self.build()
        self.assertIn("skins/elastic/templates/includes/footer.html is missing", ctx.exception.render())

    def test_missing_marker_is_named(self):
        footer = self.rc / "skins/elastic/templates/includes/footer.html"
        footer.write_text(footer.read_text().replace('src="/ui.js"', 'src="/ui2.js"'))
        with self.assertRaises(DriftError) as ctx:
            self.build()
        self.assertIn("no longer contains 'src=\"/ui.js\"'", ctx.exception.render())

    def test_missing_core_label_is_named(self):
        labels = self.rc / "program/localization/en_US/labels.inc"
        labels.write_text(labels.read_text().replace("$labels['checkmail'] = 'fake checkmail';\n", ""))
        with self.assertRaises(DriftError) as ctx:
            self.build()
        self.assertIn("Roundcube no longer has the label 'checkmail', which skin/templates/includes/footer.html",
                      ctx.exception.render())
        labels.unlink()
        with self.assertRaises(DriftError) as ctx:
            self.build()
        self.assertIn("program/localization/en_US/labels.inc is missing", ctx.exception.render())

    def test_a_plugin_or_an_outside_data_uri_in_elastic_is_named(self):
        widgets = self.rc / "skins/elastic/styles/widgets/buttons.less"
        widgets.write_text(widgets.read_text() + '// @plugin "commented";\n@plugin "evil";\n'
                           '.x { background: data-uri("image/svg+xml", "../../../../etc/hostname"); }\n'
                           '.y { background: data-uri("../images/fake.svg"); }\n')
        with self.assertRaises(DriftError) as ctx:
            self.build()
        text = ctx.exception.render()
        self.assertIn("skins/elastic/styles/widgets/buttons.less:3 has an @plugin rule", text)
        self.assertIn("embeds '../../../../etc/hostname' with data-uri()", text)
        self.assertNotIn("fake.svg", text)
        self.assertNotIn(":2 has an @plugin", text, "comments are ignored")

    def test_elastic_styles_css_would_shadow_ours(self):
        write(self.rc / "skins/elastic/styles/styles.css", "/* new */")
        with self.assertRaises(DriftError) as ctx:
            self.build()
        self.assertIn("skins/elastic/styles/styles.css exists now", ctx.exception.render())

    def test_cli_exit_codes(self):
        colors = self.rc / "skins/elastic/styles/colors.less"
        colors.write_text(colors.read_text().replace("@color-main: #123456;\n", ""))
        code, _, err = run_cli("build", "--roundcube", str(self.rc), "--out", str(self.tmp / "o"),
                               "--compiler", self.compiler, "-q")
        self.assertEqual(code, 3, err)
        self.assertIn("@color-main", err)

    def test_compile_error_exit_code(self):
        os.environ["STUB_COMPILER_FAIL"] = "1"
        self.addCleanup(os.environ.pop, "STUB_COMPILER_FAIL", None)
        code, _, err = run_cli("build", "--roundcube", str(self.rc), "--out", str(self.tmp / "o"),
                               "--compiler", self.compiler, "-q")
        self.assertEqual(code, 4, err)
        self.assertIn("variable @color-x is undefined", err)
        self.assertFalse((self.tmp / "o").exists())


class VerifyTest(FakeTreeCase):
    def setUp(self) -> None:
        super().setUp()
        self.out = build(BuildOptions(roundcube=self.rc, out=self.tmp / "out/lumen", sources=Sources.locate(ROOT),
                                      compiler=self.compiler, quiet=True)).out
        self.rcx = Roundcube.at(self.rc)

    def problems(self) -> list[str]:
        return verify(self.out, self.rcx, Sources.locate(ROOT))

    def test_clean_build_passes_and_cli_says_ok(self):
        self.assertEqual(self.problems(), [])
        code, out, _ = run_cli("verify", str(self.out), "--roundcube", str(self.rc))
        self.assertEqual(code, 0)
        self.assertIn("ok:", out)

    def test_broken_url_is_caught(self):
        css = self.out / "styles/styles.css"
        css.write_text(css.read_text() + '.x{background:url("../images/missing.svg?v=0")}\n')
        found = "\n".join(self.problems())
        self.assertIn("url(../images/missing.svg?v=0) points to skins/lumen/images/missing.svg, which does not exist",
                      found)
        code, out, _ = run_cli("verify", str(self.out), "--roundcube", str(self.rc))
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)

    def test_stale_cache_buster_and_unserved_type_are_caught(self):
        write(self.out / "fonts/extra.ttf", b"ttf")
        css = self.out / "styles/embed.css"
        css.write_text(css.read_text() + ".y{src:url(../fonts/Sora-Variable.woff?v=deadbeef00)}"
                                         ".z{src:url(../fonts/extra.ttf?v=" + short_hash(self.out / "fonts/extra.ttf") + ")}\n")
        found = "\n".join(self.problems())
        self.assertIn("lacks the cache-buster", found)
        self.assertIn("static.php does not serve .ttf files", found)

    def test_url_outside_the_skins_is_caught(self):
        css = self.out / "styles/styles.css"
        css.write_text(css.read_text() + ".x{background:url(../../../program/x.png)}.a{background:url(/abs.png)}\n")
        found = "\n".join(self.problems())
        self.assertIn("outside the two skins", found)
        self.assertIn("url(/abs.png) is absolute", found)

    def test_non_wrapper_markup_is_caught(self):
        footer = self.out / "templates/includes/footer.html"
        footer.write_text("<div class=\"copied\">Elastic markup</div>\n" + footer.read_text())
        self.assertIn("markup that is not a wrapper construct", "\n".join(self.problems()))

    def test_include_without_skinpath_is_caught(self):
        footer = self.out / "templates/includes/footer.html"
        footer.write_text(footer.read_text().replace(' skinpath="skins/elastic"', ""))
        self.assertIn("the include must be exactly", "\n".join(self.problems()))

    def test_wrapper_without_elastic_counterpart_is_caught(self):
        write(self.out / "templates/nothere.html",
              '<roundcube:include file="nothere.html" skinpath="skins/elastic" />\n')
        self.assertIn("wraps skins/elastic/templates/nothere.html, which does not exist", "\n".join(self.problems()))

    def test_copied_elastic_file_is_caught(self):
        shutil.copy(self.rc / "skins/elastic/ui.js", self.out / "ui.js")
        self.assertIn("ui.js is a copy of skins/elastic/ui.js", "\n".join(self.problems()))

    def test_stamp_detects_changes(self):
        iniset = self.rc / "program/include/iniset.php"
        iniset.write_text(iniset.read_text().replace(FAKE_VERSION, "9.9.9"))
        (self.rc / "skins/elastic/templates/mail.html").write_text("changed\n")
        (self.out / "lumen.js").write_text("// edited\n")
        found = "\n".join(verify(self.out, Roundcube.at(self.rc), Sources.locate(ROOT)))
        self.assertIn(f"built for Roundcube {FAKE_VERSION}, installed is 9.9.9", found)
        self.assertIn("built from different Elastic sources", found)
        self.assertIn("lumen.js differs from the content recorded", found)

    def test_missing_file_is_caught(self):
        (self.out / "styles/embed.min.css").unlink()
        found = "\n".join(self.problems())
        self.assertIn("styles/embed.min.css is missing", found)
        self.assertIn("listed in lumen-build.stamp but missing", found)

    def test_a_build_without_the_palette_is_caught(self):
        (self.out / "lumen-palette.js").unlink()
        stamp_path = self.out / STAMP_NAME
        stamp = json.loads(stamp_path.read_text())
        stamp["palette"] = False
        del stamp["files"]["lumen-palette.js"]
        stamp_path.write_text(json.dumps(stamp))
        footer = self.out / "templates/includes/footer.html"
        footer.write_text(footer.read_text().replace('<script src="/lumen-palette.js" defer></script>\n', ""))
        found = "\n".join(self.problems())
        self.assertIn("lumen-palette.js is missing", found)
        self.assertIn("built without the command palette", found)
        self.assertIn("no wrapper template loads the command palette", found)

    def test_meta_must_extend_elastic(self):
        meta = self.out / "meta.json"
        data = json.loads(meta.read_text())
        data["extends"] = "larry"
        data["config"]["skin_logo"] = "/x.png"
        meta.write_text(json.dumps(data))
        found = "\n".join(self.problems())
        self.assertIn("extends is 'larry'", found)
        self.assertIn("config keys ['skin_logo'] are not expected", found)


class TemplateRulesTest(unittest.TestCase):
    def test_assemble_keeps_or_drops_blocks(self):
        src = "a\n<!--lumen:palette-->\nb\n<!--/lumen:palette-->\nc\n"
        self.assertEqual(assemble(src, {"palette"}), "a\nb\nc\n")
        self.assertEqual(assemble(src, set()), "a\nc\n")
        with self.assertRaises(LumenError):
            assemble("<!-- stray comment -->\n", set())

    def test_wrapper_rules(self):
        good = ('<roundcube:if condition="!env:framed" />\n<script src="/lumen.js" data-src-app="/images/a.svg"></script>\n'
                '<roundcube:endif />\n<roundcube:include file="includes/footer.html" skinpath="skins/elastic" />\n')
        report, problems = check_wrapper("includes/footer.html", good)
        self.assertEqual(problems, [])
        self.assertEqual(report.scripts[0]["src"], "/lumen.js")
        bad_cases = {
            "unclosed": '<roundcube:if condition="x" />\n<roundcube:include file="includes/footer.html" skinpath="skins/elastic" />',
            "object": '<roundcube:object name="logo" />\n<roundcube:include file="includes/footer.html" skinpath="skins/elastic" />',
            "after": '<roundcube:include file="includes/footer.html" skinpath="skins/elastic" />\n<script src="/a.js"></script>',
            "inline-js": '<script>alert(1)</script>\n<roundcube:include file="includes/footer.html" skinpath="skins/elastic" />',
            "remote": '<script src="https://cdn.example.com/x.js"></script>\n<roundcube:include file="includes/footer.html" skinpath="skins/elastic" />',
            "other-file": '<roundcube:include file="includes/menu.html" skinpath="skins/elastic" />',
            "no-include": '<script src="/lumen.js"></script>\n',
        }
        for name, text in bad_cases.items():
            _, problems = check_wrapper("includes/footer.html", text)
            self.assertTrue(problems, name)

    def test_source_footer_is_a_valid_wrapper(self):
        src = (ROOT / "skin/templates/includes/footer.html").read_text()
        report, problems = check_wrapper("includes/footer.html", assemble(src, set()))
        self.assertEqual(problems, [])
        self.assertIn({"src": "/lumen-palette.js", "defer": ""}, report.scripts)


class CssUrlTest(unittest.TestCase):
    def test_tokenizer(self):
        css = ('/* url(comment.png) */ a{background:url("a b.png")} b{background:url( c.png )}'
               " c{content:'url(no.png)'} d{background:url('data:image/svg+xml,%3Csvg)%3E')}"
               " e{background:URL(x.svg)} f{mask:image-url(z.png)}")
        values = [u.value for u in iter_urls(css)]
        self.assertEqual(values, ["a b.png", "c.png", "data:image/svg+xml,%3Csvg)%3E", "x.svg"])

    def test_rewrite_keeps_quotes(self):
        css = "a{b:url('x.png')}c{d:url(y.png)}"
        self.assertEqual(rewrite_urls(css, lambda u: u.value + "?v=1"), "a{b:url('x.png?v=1')}c{d:url(y.png?v=1)}")


if __name__ == "__main__":
    unittest.main()
