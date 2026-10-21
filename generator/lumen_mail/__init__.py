"""lumen-mail: build, verify and maintain the Lumen skin for Roundcube Webmail.

Python standard library only. The LESS compiler is the pinned Node package "less" (plus
"clean-css" for minifying), called through compile.mjs; nothing else needs Node.

    python3 -m lumen_mail build  --roundcube /path/to/roundcube --out /path/to/lumen
    python3 -m lumen_mail verify /path/to/lumen --roundcube /path/to/roundcube
"""

from __future__ import annotations

SKIN_NAME = "lumen"
PARENT_SKIN = "elastic"
STAMP_NAME = "lumen-build.stamp"
STAMP_SCHEMA = 1
PROJECT_URL = "https://github.com/luminare-dev/lumen-mail"
