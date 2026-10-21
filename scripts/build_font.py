#!/usr/bin/env python3
"""Convert the Sora variable font from the Luminare brand kit to WOFF for the skin.

Why WOFF and not the kit's TTF: Roundcube 1.7 serves skin files through public_html/static.php,
which only answers for the file types in its SUPPORTED_TYPES list. That list has woff and woff2,
but not ttf, so a .ttf url() in the skin CSS would fail with 404. WOFF 2.0 needs the brotli
module, which is not installed here; WOFF 1.0 uses zlib from the standard library and works in
every browser Roundcube supports.

All glyphs and the wght axis are kept; only the container changes. The timestamp in the head
table is not touched, so the output is the same for the same input (reproducible).

Needs fontTools (the brand venv has it):
    /root/projects/.venvs/brand/bin/python scripts/build_font.py \
        --src "/root/important/brand/fonts/Sora[wght].ttf" --out skin/fonts/Sora-Variable.woff

Sora is Copyright 2019 The Sora Project Authors, SIL Open Font License 1.1 (no Reserved Font
Name). The licence text ships next to the font as skin/fonts/Sora-OFL.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True, type=Path, help="the kit's Sora[wght].ttf")
    ap.add_argument("--out", required=True, type=Path, help="where to write the .woff file")
    args = ap.parse_args(argv)
    try:
        from fontTools.ttLib import TTFont  # noqa: PLC0415 - optional dependency
    except ImportError:
        print("error: fontTools is not installed (use the brand venv)", file=sys.stderr)
        return 2
    font = TTFont(str(args.src), recalcTimestamp=False)
    if "fvar" not in font or not any(a.axisTag == "wght" for a in font["fvar"].axes):
        print(f"error: {args.src} is not the variable font with a wght axis", file=sys.stderr)
        return 1
    font.flavor = "woff"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(args.out), reorderTables=True)
    src_sha = hashlib.sha256(args.src.read_bytes()).hexdigest()
    out_sha = hashlib.sha256(args.out.read_bytes()).hexdigest()
    print(f"{args.out}: {args.out.stat().st_size} bytes, sha256 {out_sha}")
    print(f"source {args.src.name}: sha256 {src_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
