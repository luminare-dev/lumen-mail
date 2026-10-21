# 0010. A command palette as a skin asset: React in a shadow root, always part of the build

- **Status:** accepted
- **Date:** 2026-10-21

## Context

The owner asked for a React command palette (Ctrl/Cmd+K) in the webmail, inside a real skin and
without a Roundcube plugin. Roundcube renders server-side templates with jQuery; the palette has
to fit into that without copying Elastic templates, without network requests or storage of mail
data, in every language Roundcube has, in light and dark mode, and on touch screens. It runs in
every user's browser on a mail server that also has little memory to build with.

## Considered options

1. A Roundcube plugin that adds the script: ruled out by the owner (a skin, no plugin).
2. A skin asset: a script in `skins/lumen/`, loaded by Lumen's own footer wrapper, which includes
   Elastic's footer unchanged.
3. Plain DOM code instead of React: smaller, but not the React the owner asked for; or Preact:
   React-compatible and much smaller (not measured here), but not React.

For the texts: a translation table in the bundle, or Roundcube's own labels. For the visible
trigger: a copied Elastic menu template, or a link the script adds to Elastic's menu at run time.

## Decision

Option 2 with React 19. The Vite build writes one classic script; the generator copies it into
every build, so `sync` never runs Vite, and there is no option to build without it (a release can
never ship without the palette by accident). The dialog lives in a shadow root and reads only the
skin's `--lm-*` tokens. Items come from `rcmail` and the page each time it opens and run through
`rcmail.command()` (only when `rcmail.commands` enables the command) or Elastic's own buttons.
Every text is a Roundcube label: core labels and the skin's localization, registered by the
footer wrapper; tests and the drift check keep keys, wrapper and files in step. The trigger is a
link added to `#taskmenu .special-buttons`, laid out by Elastic's own menu rules and given its
icon by Lumen's stylesheet.

## Consequences

- Good: no Elastic template is copied; Roundcube's own checks (unsaved message, plugin hooks)
  apply to every action; translations follow Roundcube's language fallback; nothing leaves the
  page.
- Good: the visible trigger makes the palette usable on phones, where there is no Ctrl+K.
- Bad: React and React DOM are 65.9 KB gzip of the 72.1 KB bundle, over the 70 KB first aimed
  for. Trimming the palette cannot close the gap: the same bundle with its whole stylesheet
  removed is still 72,430 bytes (70.7 KB) gzip, and dropping the token fallbacks saves 190 bytes
  (measured 2026-10-21 on the built file). `scripts/check-palette.mjs` holds the bundle under
  73 KB; Preact would be the way to go far below, if the owner prefers size over React.
- Bad: building the palette needs npm's development packages once per lumen-mail version (or
  the bundle from a release package); the server's compile still needs only less and clean-css.
