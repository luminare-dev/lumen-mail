"""The command palette, the wrapper template, the localization files and the tokens agree.

* Every label the palette asks rcmail for is registered by the footer wrapper, and every skin
  label exists in en_US.inc and de_DE.inc (the bundle carries no copy of the texts).
* The fallback colours in palette/src/palette.css equal the LESS tokens, light and dark, so the
  palette looks right even on a page where the Lumen stylesheet failed to load.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail.templates import check_wrapper  # noqa: E402

I18N = ROOT / "palette/src/i18n.ts"
CSS = ROOT / "palette/src/palette.css"
TOKENS = ROOT / "src/less/lumen-tokens.less"
FOOTER = ROOT / "skin/templates/includes/footer.html"


def ts_array(name: str) -> list[str]:
    text = I18N.read_text(encoding="utf-8")
    m = re.search(rf"export const {name} = \[(.*?)\] as const;", text, re.DOTALL)
    if not m:
        raise AssertionError(f"{name} not found in {I18N}")
    return re.findall(r'"([a-z0-9_]+)"', m.group(1))


def inc_keys(lang: str) -> set[str]:
    text = (ROOT / f"skin/localization/{lang}.inc").read_text(encoding="utf-8")
    return set(re.findall(r"\$labels\['(lumen\.[a-z0-9_]+)'\]\s*=\s*'[^']+';", text))


def less_tokens() -> dict[str, str]:
    """@lm-* name -> value, with references to other @lm-* names resolved."""
    raw = dict(re.findall(r"^@(lm-[a-z0-9-]+):\s*([^;]+);", TOKENS.read_text(encoding="utf-8"), re.MULTILINE))

    def resolve(value: str, depth: int = 0) -> str:
        value = value.strip()
        if value.startswith("@") and depth < 5:
            return resolve(raw[value[1:]], depth + 1)
        return value

    return {k: resolve(v) for k, v in raw.items()}


def css_block(selector: str) -> str:
    text = CSS.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(selector)} \{{(.*?)^\}}", text, re.DOTALL | re.MULTILINE)
    if not m:
        raise AssertionError(f"{selector} block not found in {CSS}")
    return m.group(1)


class LabelsTest(unittest.TestCase):
    def setUp(self) -> None:
        report, problems = check_wrapper("includes/footer.html", FOOTER.read_text(encoding="utf-8"))
        self.assertEqual(problems, [])
        self.wrapper = set(report.labels)

    def test_skin_labels_match_everywhere(self):
        own = {f"lumen.{k}" for k in ts_array("OWN_KEYS")}
        self.assertTrue(own)
        self.assertEqual(own, {n for n in self.wrapper if n.startswith("lumen.")}, "palette keys vs footer wrapper")
        self.assertEqual(own, inc_keys("en_US"), "palette keys vs localization/en_US.inc")
        self.assertEqual(own, inc_keys("de_DE"), "palette keys vs localization/de_DE.inc")

    def test_core_labels_are_registered(self):
        core = set(ts_array("CORE_KEYS"))
        self.assertEqual(core, {n for n in self.wrapper if not n.startswith("lumen.")})

    def test_results_label_has_its_placeholder(self):
        for lang in ("en_US", "de_DE"):
            text = (ROOT / f"skin/localization/{lang}.inc").read_text(encoding="utf-8")
            self.assertRegex(text, r"\$labels\['lumen\.palette_results'\] = '[^']*\$n[^']*';", lang)

    @unittest.skipUnless(Path("/home/keyhelp/www/roundcube/program/localization/en_US/labels.inc").is_file(),
                         "no installed Roundcube to compare with")
    def test_core_labels_exist_in_the_installed_roundcube(self):
        text = Path("/home/keyhelp/www/roundcube/program/localization/en_US/labels.inc").read_text(encoding="utf-8")
        known = set(re.findall(r"\$labels\['([a-z0-9_]+)'\]", text))
        self.assertEqual(set(ts_array("CORE_KEYS")) - known, set())


class CssFallbackTest(unittest.TestCase):
    def check_mode(self, selector: str, mode: str) -> int:
        tokens = less_tokens()
        checked = 0
        for role, fallback in re.findall(r"var\(--lm-([a-z0-9-]+),\s*(#[0-9A-Fa-f]{3,8})\)", css_block(selector)):
            want = tokens.get(f"lm-{mode}-{role}")
            self.assertIsNotNone(want, f"{selector}: --lm-{role} is not a {mode} token")
            self.assertEqual(fallback.upper(), want.upper(), f"{selector}: fallback of --lm-{role}")
            checked += 1
        return checked

    def test_light_fallbacks_equal_the_light_tokens(self):
        self.assertGreaterEqual(self.check_mode(".lm", "light"), 9)

    def test_dark_fallbacks_equal_the_dark_tokens(self):
        self.assertGreaterEqual(self.check_mode(".lm.is-dark", "dark"), 9)

    def test_shape_and_motion_fallbacks_equal_the_tokens(self):
        tokens = less_tokens()
        block = css_block(".lm")
        for name in ("radius-s", "radius-m", "radius-xl", "ring", "ease"):
            m = re.search(rf"var\(--lm-{name},\s*([^;]+)\);", block)
            self.assertIsNotNone(m, name)
            self.assertEqual(m.group(1).replace(" ", ""), tokens[f"lm-{name}"].replace(" ", ""), name)

    def test_only_logical_properties_for_direction(self):
        text = CSS.read_text(encoding="utf-8")
        physical = re.findall(r"^\s*((?:margin|padding|border)-(?:left|right)[a-z-]*|left|right|text-align:\s*(?:left|right))\b",
                              text, re.MULTILINE)
        self.assertEqual(physical, [], "use logical properties (inline-start/end) so right-to-left pages mirror")


if __name__ == "__main__":
    unittest.main()
