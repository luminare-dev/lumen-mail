"""Tests for reading $config['skin'] from Roundcube config files (the uninstall guard)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail.phpconfig import find_setting, system_skin  # noqa: E402


def skin(text: str):
    s = find_setting(text, "skin")
    return s.value, s.found, s.certain


class FindSettingTest(unittest.TestCase):
    def test_quote_and_spacing_variants(self):
        for text in ("<?php\n$config['skin'] = 'lumen';\n",
                     '<?php\n$config["skin"]="lumen";\n',
                     "<?php\n$config[ 'skin' ]  =  \"lumen\" ;\n",
                     "<?php\n$config['skin']\n    = 'lumen'\n;\n",
                     "<?php $config['skin']='lumen'?>",
                     "<?php\n$rcmail_config['skin'] = 'lumen';\n"):
            with self.subTest(text=text):
                self.assertEqual(skin(text), ("lumen", True, True))

    def test_commented_out_lines_do_not_count(self):
        for text in ("<?php\n// $config['skin'] = 'lumen';\n$config['skin'] = 'elastic';\n",
                     "<?php\n$config['skin'] = 'elastic';\n# $config['skin'] = 'lumen';\n",
                     "<?php\n$config['skin'] = 'elastic';\n/* $config['skin'] = 'lumen';\n*/\n",
                     "<?php\n$config['skin'] = 'elastic'; // was: $config['skin'] = 'lumen';\n",
                     "$config['skin'] = 'lumen';\n<?php\n$config['skin'] = 'elastic';\n"):
            with self.subTest(text=text):
                self.assertEqual(skin(text), ("elastic", True, True))

    def test_text_inside_strings_does_not_count(self):
        text = "<?php\n$config['product_name'] = \"$config['skin'] = 'lumen';\";\n$config['skin'] = 'elastic';\n"
        self.assertEqual(skin(text)[0], "elastic")
        text = "<?php\n$config['support_url'] = '// not a comment';\n$config['skin'] = 'lumen';\n"
        self.assertEqual(skin(text), ("lumen", True, True))

    def test_last_assignment_wins(self):
        self.assertEqual(skin("<?php\n$config['skin'] = 'lumen';\n$config['skin'] = 'elastic';\n")[0], "elastic")
        self.assertEqual(skin("<?php\n$config['skin'] = 'elastic';\n$config['skin'] = 'lumen';\n")[0], "lumen")

    def test_escapes(self):
        self.assertEqual(skin("<?php\n$config['skin'] = 'lu\\'men';\n")[0], "lu'men")
        self.assertEqual(skin('<?php\n$config["skin"] = "lu\\"men";\n')[0], 'lu"men')

    def test_unknown_forms_are_uncertain(self):
        for text in ("<?php\n$config['skin'] = $skin;\n",
                     "<?php\n$config['skin'] = getenv('SKIN') ?: 'elastic';\n",
                     "<?php\n$config['skin'] = \"$name\";\n",
                     "<?php\n$config = array_merge($config, ['skin' => 'lumen']);\n",
                     "<?php\n$config['skin'] = 'elastic';\ninclude '/etc/roundcube/local.php';\n",
                     "<?php\n$config['skin'] .= 'x';\n"):
            with self.subTest(text=text):
                self.assertFalse(skin(text)[2])

    def test_include_before_a_literal_assignment_is_fine(self):
        self.assertEqual(skin("<?php\ninclude 'x.php';\n$config['skin'] = 'elastic';\n"), ("elastic", True, True))

    def test_reading_the_key_is_not_an_assignment(self):
        self.assertEqual(skin("<?php\nif ($config['skin'] == 'x') {}\n"), (None, False, True))

    def test_other_keys_are_ignored(self):
        self.assertEqual(skin("<?php\n$config['skin_logo'] = ['elastic:*' => '/x.svg'];\n"), (None, False, True))


class SystemSkinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lumen-mail-phpconfig-"))
        (self.tmp / "config").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_config_then_defaults_then_elastic(self):
        self.assertEqual(system_skin(self.tmp).value, "elastic")
        (self.tmp / "config" / "defaults.inc.php").write_text("<?php\n$config['skin'] = 'larry';\n")
        self.assertEqual(system_skin(self.tmp).value, "larry")
        (self.tmp / "config" / "config.inc.php").write_text("<?php\n$config['des_key'] = 'k';\n")
        self.assertEqual(system_skin(self.tmp).value, "larry")
        (self.tmp / "config" / "config.inc.php").write_text("<?php\n$config['skin'] = 'lumen';\n")
        s = system_skin(self.tmp)
        self.assertEqual((s.value, s.certain, s.printable), ("lumen", True, "lumen"))

    def test_printable_never_shows_an_odd_value(self):
        (self.tmp / "config" / "config.inc.php").write_text("<?php\n$config['skin'] = 'a b; secret';\n")
        self.assertEqual(system_skin(self.tmp).printable, "(not a plain name)")


if __name__ == "__main__":
    unittest.main()
