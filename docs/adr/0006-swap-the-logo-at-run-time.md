# 0006. Swap Elastic's default logo at run time

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Elastic's `login.html` and `includes/menu.html` render the logo as `/images/logo.svg`. Roundcube
resolves an asset path from a template in the folder of that template's skin first
(`rcmail_output_html::file_callback` puts the including skin's path in front of the search list),
so for a template that comes from Elastic, `skins/elastic/images/logo.svg` (the Roundcube logo)
always wins over a file of the same name in `skins/lumen`. The same holds for the favicon and for
`/styles/styles.css`. The admin's `skin_logo` option must keep working.

## Considered options

1. Copy `login.html` and `includes/menu.html` into Lumen with a different logo path.
2. Ask every admin to set `skin_logo`.
3. A small script from Lumen's footer wrapper that replaces Elastic's default logo before Elastic's
   `ui.js` starts, plus a CSS rule that keeps the default logo invisible until then.

## Decision

Option 3. `lumen.js` acts only when the page shows Elastic's default logo, so a configured
`skin_logo` always wins, and it fills `rcmail.env.additional_logos` only for the types the admin did
not set. The favicon comes from the `favicon` key in Lumen's `meta.json` config, with a file name
that Elastic does not have. The stylesheet works because Elastic ships only `styles.min.css`, so
Lumen's `styles/styles.css` is the first match; the drift check fails if Elastic ever adds a
`styles.css`.

## Consequences

- Good: no Elastic template is copied; the admin's logo settings are respected.
- Bad: the Luminare logo depends on JavaScript (Roundcube itself needs JavaScript); without it the
  logo area stays empty rather than showing the Roundcube logo.
