# 0007. Sora as WOFF, and a stamp file that is not served

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Roundcube 1.7 serves skin files through `public_html/static.php`, which answers only for the file
types in its `SUPPORTED_TYPES` list. That list has `woff` and `woff2` but not `ttf`, and it has
`json`. The brand kit ships Sora as a variable TTF; WOFF 2.0 needs the brotli module, which the
server's Python does not have. The build stamp contains the exact Roundcube version, which
Roundcube does not show to visitors who are not logged in.

## Considered options

1. Ship the TTF (fails with 404 under 1.7).
2. Convert to WOFF 1.0 with fontTools and zlib, keeping every glyph and the wght axis.
3. Name the stamp `lumen-build.json`, or give it an extension static.php does not serve.

## Decision

Option 2 for the font (`scripts/build_font.py`, reproducible, 60,684 bytes instead of 111,400) and
`lumen-build.stamp` for the stamp (JSON content, but not a served type). `verify` checks every
`url()` in the compiled CSS against the installed `static.php` list, so an unserved type fails the
build.

## Consequences

- Good: the font loads in every browser Roundcube supports; the version is not exposed.
- Bad: WOFF compresses less well than WOFF 2.0; switching is a change to `scripts/build_font.py`
  once brotli is available.
