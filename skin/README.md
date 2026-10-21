# Lumen skin for Roundcube Webmail

Lumen ${lumen_version}, built on this server for Roundcube ${roundcube_version}. A modern Luminare
skin for Roundcube Webmail, a Luminare Development open-source project:
<https://github.com/luminare-dev/lumen-mail>

Not affiliated with or endorsed by the Roundcube project.

## How this folder was made

Lumen extends the Elastic skin (`"extends": "elastic"` in `meta.json`): every template Lumen does
not have comes from `skins/elastic`. The stylesheets in `styles/` were compiled on this server by
`python3 -m lumen_mail build` from Elastic's LESS sources in `skins/elastic/styles` plus the Lumen
sources. `lumen-build.stamp` records the Roundcube version, a digest of the Elastic sources and the
sha256 of every file in this folder, so a rebuild is due whenever Roundcube changes Elastic.

## Credits

- **Elastic skin** by Aleksander Machniak and The Roundcube Dev Team (<https://roundcube.net>),
  licensed under the Creative Commons Attribution-ShareAlike 3.0 licence (CC BY-SA 3.0,
  <https://creativecommons.org/licenses/by-sa/3.0/>). The compiled stylesheets in `styles/` are an
  adaptation of Elastic: Elastic's styles with Lumen's colours, typography and component rules.
- Elastic's styles contain the icon code points of **Font Awesome Free 5** (code MIT, fonts SIL
  OFL 1.1, <https://fontawesome.com>); the font files themselves stay in `skins/elastic/fonts` and
  are referenced from there. Elastic's own README lists its other separately licensed parts
  (Bootstrap, Roboto).
- **Sora** typeface, Copyright 2019 The Sora Project Authors
  (<https://github.com/sora-xor/sora-font>), SIL Open Font License 1.1: `fonts/Sora-OFL.txt`.
  `fonts/Sora-Variable.woff` is the unchanged variable font in a WOFF container.
- `lumen-palette.js`, when present, bundles **React** and **React DOM** (MIT licence); their
  copyright and licence notices are kept at the top of the file.

## Licences

| Files | Licence |
|---|---|
| `styles/*.css` (compiled) | CC BY-SA 3.0, as an adaptation of Elastic |
| `templates/`, `localization/`, `lumen.js`, `lumen-palette.js`, `watermark.html`, `meta.json` | MIT, Copyright (c) 2026 Paul Pasaurek |
| `fonts/Sora-Variable.woff` | SIL Open Font License 1.1 |
| `images/`, `thumbnail.png` | Luminare brand files: not licensed (see the project's NOTICE) |

The names "Luminare Development" and "Luminare" and the Luminare logo and mark are not licensed
under any of the licences above.
