#!/usr/bin/env python3
"""Render skin/thumbnail.png, the 64x64 preview Roundcube shows in the skin chooser.

The picture is our own: a miniature of the Lumen layout (Night rail with the Luminare mark,
Mist folder column, white list and content) drawn as SVG and rasterised with PyMuPDF from the
brand venv. The mark polygons are the brand kit's geometry (logo/luminare-mark.svg), scaled.

    /root/projects/.venvs/brand/bin/python scripts/render_thumbnail.py --out skin/thumbnail.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARK = ROOT / "skin" / "images" / "luminare-mark.svg"

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <defs><clipPath id="r"><rect width="64" height="64" rx="8"/></clipPath></defs>
  <g clip-path="url(#r)">
    <rect width="64" height="64" fill="#FFFFFF"/>
    <rect width="13" height="64" fill="#0A1224"/>
    <g transform="translate(1.5,2) scale(0.0122)">{mark}</g>
    <rect x="3" y="18" width="7" height="7" rx="2" fill="#0F1F4C"/>
    <rect x="3" y="18" width="1.2" height="7" fill="#5BDFFF"/>
    <circle cx="6.5" cy="21.5" r="1.6" fill="#FFFFFF"/>
    <circle cx="6.5" cy="30.5" r="1.6" fill="#B7C1D3"/>
    <circle cx="6.5" cy="39.5" r="1.6" fill="#B7C1D3"/>
    <rect x="13" width="13" height="64" fill="#F3F6FB"/>
    <rect x="14.5" y="8" width="10" height="4" rx="2" fill="#E9EDF9"/>
    <rect x="15.5" y="9.5" width="6" height="1" rx="0.5" fill="#1F47C4"/>
    <rect x="15.5" y="15.5" width="7" height="1" rx="0.5" fill="#5E6B84"/>
    <rect x="15.5" y="20.5" width="5" height="1" rx="0.5" fill="#5E6B84"/>
    <rect x="15.5" y="25.5" width="6" height="1" rx="0.5" fill="#5E6B84"/>
    <rect x="26" width="0.6" height="64" fill="#E3E8F1"/>
    <rect x="26.6" y="6" width="16" height="8" fill="#E9EDF9"/>
    <rect x="28" y="8" width="9" height="1.2" rx="0.6" fill="#0A1224"/>
    <rect x="28" y="10.8" width="12" height="1" rx="0.5" fill="#5E6B84"/>
    <rect x="28" y="17" width="9" height="1.2" rx="0.6" fill="#0A1224"/>
    <rect x="28" y="19.8" width="12" height="1" rx="0.5" fill="#B7C1D3"/>
    <rect x="28" y="26" width="9" height="1.2" rx="0.6" fill="#39445C"/>
    <rect x="28" y="28.8" width="12" height="1" rx="0.5" fill="#B7C1D3"/>
    <rect x="28" y="35" width="9" height="1.2" rx="0.6" fill="#39445C"/>
    <rect x="28" y="37.8" width="12" height="1" rx="0.5" fill="#B7C1D3"/>
    <rect x="42.6" width="0.6" height="64" fill="#E3E8F1"/>
    <rect x="46" y="8" width="14" height="2" rx="1" fill="#0A1224"/>
    <rect x="46" y="14" width="15" height="1" rx="0.5" fill="#B7C1D3"/>
    <rect x="46" y="18" width="13" height="1" rx="0.5" fill="#B7C1D3"/>
    <rect x="46" y="22" width="15" height="1" rx="0.5" fill="#B7C1D3"/>
    <rect x="46" y="26" width="10" height="1" rx="0.5" fill="#B7C1D3"/>
    <rect x="46" y="32" width="8" height="3.4" rx="1.7" fill="#1F47C4"/>
  </g>
  <rect x="0.5" y="0.5" width="63" height="63" rx="7.5" fill="none" stroke="#E3E8F1"/>
</svg>
"""


def mark_polygons() -> str:
    text = MARK.read_text(encoding="utf-8")
    start, end = text.index("<g>") + 3, text.index("</g>")
    return text[start:end]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "skin" / "thumbnail.png")
    ap.add_argument("--svg", type=Path, help="also write the SVG source here")
    args = ap.parse_args(argv)
    try:
        import pymupdf  # noqa: PLC0415 - optional dependency (brand venv)
    except ImportError:
        print("error: PyMuPDF is not installed (use the brand venv)", file=sys.stderr)
        return 2
    svg = SVG.format(mark=mark_polygons())
    if args.svg:
        args.svg.write_text(svg, encoding="utf-8")
    doc = pymupdf.open(stream=svg.encode(), filetype="svg")
    pix = doc[0].get_pixmap(alpha=True)
    if (pix.width, pix.height) != (64, 64):
        print(f"error: rendered {pix.width}x{pix.height}, expected 64x64", file=sys.stderr)
        return 1
    args.out.write_bytes(pix.tobytes("png"))
    print(f"{args.out}: {args.out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
