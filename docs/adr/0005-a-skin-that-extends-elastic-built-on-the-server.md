# 0005. A skin that extends Elastic, compiled on the server

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Lumen must be a real Roundcube skin: selectable as the system skin (`$config['skin']`, KeyHelp's
"Interface skin" field) and in each user's skin chooser, on any Roundcube installation. Elastic,
Roundcube's default skin, is licensed under CC BY-SA 3.0; its LESS sources ship with every
Roundcube release. Keeping a copy of Elastic's templates or styles in this repository would make
the repository a CC BY-SA adaptation, and the copy would go stale with every Roundcube update.

## Considered options

1. A full fork of Elastic (templates, LESS, scripts) in the repository.
2. A plugin that injects a stylesheet into Elastic.
3. A skin with `"extends": "elastic"` whose CSS is compiled on the server from the installed
   Elastic LESS plus our LESS (variable overrides and a component layer).

## Decision

Option 3. Roundcube looks up every template and asset in `skins/lumen` first and then in
`skins/elastic`, so Lumen ships only its own files: compiled CSS, one wrapper template
(`templates/includes/footer.html`, which includes Elastic's footer through
`skinpath="skins/elastic"`), a logo script, images, the font and labels. The generator compiles
against exactly the Elastic that is installed, checks first that every variable, file and marker
it relies on still exists (drift check), and records the Roundcube version and a digest of the
Elastic sources in `lumen-build.stamp`, so a Roundcube update triggers a rebuild.

## Consequences

- Good: the repository holds only our code (MIT); new Elastic features and fixes arrive with each
  rebuild; the skin works on every Roundcube that has Elastic.
- Good: a renamed Elastic variable stops the build with its name instead of silently losing a
  colour.
- Bad: the server needs Node 20+ and the pinned `less` and `clean-css` packages to build; the
  release package for other users is compiled against one Roundcube version and fits that minor
  series only. The compiled CSS is CC BY-SA 3.0 and says so in its banner.
