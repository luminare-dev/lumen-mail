"""Entry point for ``python3 -m lumen_mail``."""

from __future__ import annotations

import sys

from .cli import main

sys.exit(main())
