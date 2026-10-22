# 0011. Long labels get room instead of an ellipsis

- **Status:** accepted
- **Date:** 2026-10-22

## Context

In German, Lumen 0.1.0 cut labels with an ellipsis: "Einstellungen" and "Dunkler Modus" in the
task rail, "Allen antworten" and "Weiterleiten" in the message toolbar, "Schnellantworten" when
writing, three address book names, and more on touch screens and phones. Elastic itself cuts
some of them; Lumen cut more, for two reasons:

- Sora is wider than Elastic's Roboto: at 12.6px "Allen antworten" is 103px in Sora and 88px
  in Roboto, "Weiterleiten" 80px and 68px (measured in Chromium).
- Lumen's own LESS: `@layout-menu-width: 96px` widened the rail, but Elastic's
  `.menu.toolbar a { max-width: 6rem }` also matches the rail's links (`#taskmenu` is a
  `.menu.toolbar`), so they stayed 84px wide in the 96px rail, off centre. Lumen's padded sidebar
  lists leave 16px less room than Elastic's.

Where else the room ends: header toolbar buttons are capped at 6rem (84px), Bootstrap caps
popovers at 276px (too narrow for the 16px touch font), the small and phone layouts show menus
in a 272px side panel, the list footer's count stays on one line in a narrow list, and phone
footer buttons are capped at 6rem.

`scripts/screenshots/label-fit.mjs` now measures every label in the rail, the toolbars, the
column headers and footers, the sidebar lists and the open menus, for Lumen and for Elastic, in
ten languages at five sizes (docs/development.md, "Label fit"). Constraints for the fix: English
looks as before; no label below 11px, no letter-spacing below -0.01em, no horizontal squeezing;
two lines in the rail only if all its items keep the same height.

## Considered options

1. A smaller label size (11px) or tighter letter-spacing: every language, English too, pays for a
   few long words, and tighter spacing hurts legibility in Sora.
2. Two lines everywhere: the toolbar has no room for a second line (58px headers), rail items
   would differ in height, and single long words need hyphenation, which depends on the
   browser's dictionaries (Roundcube sets `lang`, but not every browser hyphenates).
3. A script that measures labels and shrinks or wraps them: a layout shift after the fonts load,
   and code on every page.
4. Give long labels the room, where there is room, and leave labels that fit exactly as Elastic
   lays them out.

## Decision

Option 4:

- the rail's links take the rail's full width, and their labels drop Elastic's 0.1em of side
  padding;
- the content toolbar's buttons start at Elastic's 6rem (or less, for short labels) and long
  labels grow to their full width, up to 11rem, as far as the header has room (flex items in
  place of Elastic's inline blocks); between 769 and 959px, where the content column is narrow,
  the buttons get less side padding; on a header that is still too narrow the longest label is
  cut, as in Elastic, instead of the last buttons leaving the header; list header buttons grow
  up to 11rem;
- phone footer buttons are as wide as a long label; menus grow up to 28rem;
- column header titles, the list footer's count, the entries of the 272px side panel menus and
  of the folder, address book and settings lists take a second line beside their icon when they
  are long, while one-line rows and titles stay exactly where Elastic puts them (line heights and
  padding in whole or quarter pixels).

English is unchanged at 960px and wider except for the rail: its items are now centred in the
96px rail (6px further right) and the selected item's background spans the rail, as intended
when the rail was widened. The README screenshots differ in those 96 columns only. Between 769
and 959px English toolbars are a little denser (less side padding).

Labels cut, measured with `label-fit.mjs` on 2026-10-22 (Roundcube 1.7.3, Chromium 156 headless
shell, example data); each label counted once per size, summed over desktop (1280px), normal
(1100px), touch (1024px), tablet (800px) and phone (360px):

| Language | Elastic | Lumen 0.1.0 | Lumen with this decision |
|---|---:|---:|---:|
| en_US | 1 | 5 | 0 |
| de_DE | 16 | 29 | 0 |
| fr_FR | 7 | 23 | 0 |
| es_ES | 8 | 22 | 0 |
| it_IT | 13 | 18 | 2 |
| nl_NL | 19 | 33 | 4 |
| pl_PL | 5 | 17 | 0 |
| ru_RU | 23 | 33 | 2 |
| pt_BR | 9 | 20 | 0 |
| ar | 8 | 7 | 0 |
| all | 109 | 207 | 8 |

The eight left are cut by Elastic too: single long words or long phrases in the rail at 1100px and
wider ("Nuovo messaggio", "Contactpersonen", "Написать сообщение") and two Dutch toolbar labels at
800px.

## Consequences

- Good: no label in the rail, the toolbars, the menus or the sidebar lists is cut in German at
  any of the five sizes, and Lumen cuts no label that Elastic shows in full in the other nine
  languages; the eight cuts left are Elastic's too.
- Good: the check shows a new Elastic release or translation as a table per language and size.
- Bad: long user folder names now wrap onto several lines instead of ending in an ellipsis.
- Bad: Lumen overrides more of Elastic's toolbar layout (flex in place of inline blocks), so an
  Elastic change to toolbar markup needs the check run again.
- Bad: the check needs a Roundcube tree, PHP and a downloaded browser, so it is not part of CI.
