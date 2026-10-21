"""A tiny FAKE Roundcube tree for the generator tests, written by us (no Roundcube file in it).

It only has what the build and verify look at: RCMAIL_VERSION in program/include/iniset.php,
a SUPPORTED_TYPES list in public_html/static.php, the core labels our wrapper registers in
program/localization/en_US/labels.inc (dummy texts), and a fake skins/elastic whose LESS defines
every Elastic variable name Lumen's LESS sets or reads (dummy values), whose templates contain
the markers the drift check looks for, plus a few stand-in asset files.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail.elastic import our_variable_refs, wrapper_core_labels  # noqa: E402

STUB_COMPILER = ROOT / "tests" / "stub_compiler.py"
# Every build includes the command palette; the tests use this stub instead of the Vite build.
STUB_PALETTE = ROOT / "tests" / "fixtures" / "lumen-palette.js"
FAKE_VERSION = "9.8.7"


def write(path: Path, text: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def make_roundcube(base: Path, version: str = FAKE_VERSION, static_php: bool = True) -> Path:
    rc = base / "roundcube"
    write(rc / "program/include/iniset.php", f"<?php\n// fake\ndefine('RCMAIL_VERSION', '{version}');\n")
    labels = sorted({name for name, _rel in wrapper_core_labels(ROOT / "skin")})
    write(rc / "program/localization/en_US/labels.inc",
          "<?php\n$labels = [];\n" + "".join(f"$labels['{n}'] = 'fake {n}';\n" for n in labels))
    if static_php:
        write(rc / "public_html/static.php",
              "<?php\nconst SUPPORTED_TYPES = [\n    'css' => 'text/css',\n    'html' => 'text/html',\n"
              "    'ico' => 'image/x-icon',\n    'js' => 'text/javascript',\n    'png' => 'image/png',\n"
              "    'svg' => 'image/svg+xml',\n    'woff' => 'font/woff',\n    'woff2' => 'font/woff2',\n];\n")
    el = rc / "skins/elastic"
    names = sorted({r.name for r in our_variable_refs(ROOT / "src" / "less")})
    defs = "".join(f"@{n}: #123456;\n" for n in names if not n.startswith(("screen-width", "layout-")))
    sizes = "".join(f"@{n}: 100px;\n" for n in names if n.startswith(("screen-width", "layout-")))
    write(el / "meta.json", json.dumps({"name": "Fake parent", "author": "tests", "config": {}}))
    write(el / "styles/colors.less", "// fake colours\n" + defs)
    write(el / "styles/variables.less", "@import (reference) \"colors\";\n" + sizes)
    write(el / "styles/mixins.less", ".font-family { font-family: serif; }\n")
    write(el / "styles/global.less",
          "@import (reference) \"variables\";\n@import (reference) \"mixins\";\n"
          "@font-face { font-family: Fake; src: url(\"../fonts/fake.woff2\") format(\"woff2\"); }\n")
    write(el / "styles/styles.less", "@import \"global\";\n@import \"widgets/buttons\";\n"
                                     ".fake { background: url('../images/fake.svg'); }\n"
                                     "& when (true) { @import \"dark\"; }\n")
    # like Elastic: a url in styles/widgets/ is written relative to styles/, not to widgets/
    write(el / "styles/widgets/buttons.less", ".fake-btn { background: url(\"../images/fake-icon.svg\"); }\n")
    write(el / "styles/dark.less", "html.dark-mode .fake { color: red; }\n")
    write(el / "styles/embed.less", "@import \"global\";\n.fake-embed { color: blue; }\n")
    write(el / "templates/includes/footer.html",
          "</div>\n<roundcube:object name=\"message\" id=\"messagestack\" />\n"
          "<script src=\"/ui.js\"></script>\n</body>\n</html>\n")
    write(el / "templates/includes/layout.html", "<html><head><link rel=\"stylesheet\" href=\"/styles/styles.css\">"
                                                 "</head><body><div id=\"layout\">\n")
    write(el / "templates/includes/menu.html", "<roundcube:object name=\"logo\" src=\"/images/logo.svg\" id=\"logo\" />\n")
    write(el / "templates/login.html", "<roundcube:object name=\"logo\" src=\"/images/logo.svg\" id=\"logo\" />\n"
                                       "<form id=\"login-form\"></form>\n")
    write(el / "templates/mail.html", "<roundcube:include file=\"includes/footer.html\" />\n")
    write(el / "images/logo.svg", "<svg xmlns=\"http://www.w3.org/2000/svg\"/>\n")
    write(el / "images/fake.svg", "<svg xmlns=\"http://www.w3.org/2000/svg\"><rect/></svg>\n")
    write(el / "images/fake-icon.svg", "<svg xmlns=\"http://www.w3.org/2000/svg\"><circle/></svg>\n")
    write(el / "fonts/fake.woff2", b"wOF2-fake-font")
    write(el / "ui.js", "// fake ui\n")
    return rc


class FakeTreeCase(unittest.TestCase):
    """Base class: a fresh temp dir with a fake Roundcube and a stub compiler per test."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lumen-mail-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.rc = make_roundcube(self.tmp)
        self.compiler = f"{sys.executable} {STUB_COMPILER}"
        env = mock.patch.dict(os.environ, {"LUMEN_MAIL_PALETTE": str(STUB_PALETTE)})
        env.start()
        self.addCleanup(env.stop)
