# Development

How the repository is laid out, how to run every check, and how the command palette and the
gallery are put together. Installing the skin on a server is in [install.md](install.md).

## Layout

| Path | What it is |
|---|---|
| `src/less/` | Lumen's LESS: tokens (`lumen-tokens.less`), Elastic variable overrides (`lumen-variables.less`), the component layer (`lumen.less`, `lumen-embed.less`) and the contrast pairs |
| `skin/` | the skin's own static files: `meta.json`, the footer wrapper template, `lumen.js` (logo), localization, logos, Sora, thumbnail, the installed README |
| `palette/` | the command palette: TypeScript and React sources (`src/`), Vitest tests (`test/`), its Vite and Vitest configs |
| `gallery/` | the design-system gallery (React, Vite) and `data.mjs`, which reads our tokens and labels at build time |
| `generator/lumen_mail/` | the Python package behind `python3 -m lumen_mail` (standard library only) and `compile.mjs`, the Node driver of the LESS compiler |
| `contrib/systemd/` | the sync service, path and timer units |
| `scripts/` | release package, contrast table, palette bundle check, font and thumbnail builders, repository checks |
| `tests/` | Python tests (fake Roundcube tree, stub compiler, a real-compile integration test) and `tests/js/` (`node --test`) |

Nothing from Roundcube or Elastic is in the repository; the generator reads the installed Elastic
at build time ([ADR 0005](adr/0005-a-skin-that-extends-elastic-built-on-the-server.md)).

## Tools

- Node.js 22 (Vite 8 needs 20.19 or later, or 22.12 or later) and npm 10;
- Python 3.12 (the generator needs 3.10 or later and only the standard library);
- for the real-compile test: a Roundcube tree with Elastic's LESS sources, for example from
  `python3 -I scripts/package.py fetch --dest /tmp/roundcube` (the pinned, sha256-checked
  release).

```bash
npm ci --ignore-scripts --no-audit --no-fund
```

`.npmrc` turns install scripts off and saves exact versions. The server only needs the compiler
(`npm ci --omit=dev`, two packages and their dependencies); everything else is a development
dependency.

## Commands

| Command | What it does |
|---|---|
| `npm run typecheck` | TypeScript (strict) over the palette, its tests and the gallery |
| `npm test` | Vitest with jsdom and Testing Library: the palette and the gallery's contrast maths |
| `npm run test:js` | `node --test` for `skin/lumen.js` (logo swap) and `gallery/data.mjs` |
| `npm run build:palette` | `palette/dist/lumen-palette.js`, then `scripts/check-palette.mjs` (one classic script, no network or storage API, licence banner, size budget) |
| `npm run build:gallery` | `gallery/dist/` (static, relative paths) |
| `npm run gallery` | the gallery's dev server |
| `npm run build` | both builds |
| `python3 -m unittest discover -s tests` | generator, lifecycle, units, packaging, repository checks; the real compile runs when `node_modules` and a Roundcube tree exist (`LUMEN_MAIL_TEST_ROUNDCUBE`, default `/home/keyhelp/www/roundcube`) |
| `python3 scripts/contrast.py --check` | every colour pair passes WCAG 2.2 AA and `docs/contrast.md` is current |
| `python3 scripts/forbidden_words.py` | the wording check CI runs |
| `PYTHONPATH=generator python3 -m lumen_mail build --roundcube R --out /tmp/lumen` | a real build (needs the palette bundle) |

CI ([ci.yml](../.github/workflows/ci.yml)) runs the same commands in four jobs: `ci / lint-test`
(Python tests and the linters), `node`, `package` (compiler-only install, the palette bundle from
`node`, the real compile against the pinned Roundcube release, the release package) and
`secrets / gitleaks`.

### Memory on a small server

On a server that also runs mail, start heavy steps with a memory cap and let the kernel stop
them first if memory runs out:

```bash
NODE_OPTIONS=--max-old-space-size=256 systemd-run --scope --quiet --collect \
  -p MemoryMax=300M -p MemorySwapMax=0 choom -n 1000 -- nice -n 19 npm test
```

Measured peaks (resident memory, this repository, 2026-10-21): `npm ci` from the lockfile 147 MB,
Vitest 155 MB (one worker, no file parallelism: `palette/vitest.config.js`), the palette build
150 MB, the gallery build 172 MB, `tsc` 137 MB, the LESS compile 109 MB. Resolving a new
lockfile (`npm install` with no lockfile entry for the new packages) needed more than 300 MB;
add new packages on a machine with more memory.

## The command palette

`palette/src/main.ts` is the entry of a Vite library build into one IIFE. The generator copies
`palette/dist/lumen-palette.js` into every `skins/lumen/`, and `install-runtime` puts it into the
runtime, so `sync` never runs Vite. The footer wrapper loads it with `defer` on top-level pages
(not framed, not in an external compose window, not login, print or error pages); Roundcube adds
its `?s=<mtime>` cache-buster.

| File | Role |
|---|---|
| `mount.tsx` | checks the page again (`rcmail`, skin `lumen`, top-level, not login/print/error), creates the shadow root and the trigger link in `#taskmenu .special-buttons` |
| `Palette.tsx` | the dialog: shortcut (also in same-origin frames, never in text areas, contenteditable or TinyMCE), combobox and listbox with `aria-activedescendant`, focus trap and restore |
| `collect.ts` | the items, read from `rcmail` and the page each time the palette opens |
| `fuzzy.ts` | ranking: subsequence match, word starts and runs score higher, accents and case ignored |
| `i18n.ts` | the label keys; every text comes from `rcmail.get_label()` |
| `page.ts` | dark mode (`html.dark-mode`), direction (`dir`, or a right-to-left language), shortcut and editor detection |
| `palette.css` | the shadow root's styles: `--lm-*` tokens with fallbacks equal to the LESS tokens, logical properties only |

Items run through Roundcube itself: `rcmail.command()` for commands that `rcmail.commands`
reports as enabled, or a click on Elastic's own button (dark mode, About, plugin tasks, settings
tabs), so Roundcube's checks (unsaved message, busy state, plugin hooks) apply. Nothing is
fetched or stored.

Adding a label: the key in `i18n.ts`, a `<roundcube:add_label>` in the footer wrapper, and for
the skin's own labels the text in both localization files. `tests/test_palette_consistency.py`
fails until all of them agree, and the generator's drift check fails a build if the installed
Roundcube lacks a core label.

Freshness: the bundle's banner names the digest of everything it is built from (`palette/src/`,
`palette/vite.config.js`, `package.json`; `scripts/palette-inputs.mjs`). `check-palette.mjs` and
the generator recompute it from the checkout, so `build`, `install`, `install-runtime` and the
release package stop with "out of date" until `npm run build:palette` has run after a change.
`tests/test_palette_digest.py` keeps the Node and Python digests equal.

Size: React 19 and React DOM alone are 65.9 KB gzip in this build setup; the palette adds about
6 KB. `scripts/check-palette.mjs` holds the bundle under 73 KB gzip.

## The gallery

```bash
npm run gallery                     # dev server, tokens, contrast and the palette
npm run build:gallery               # gallery/dist, served from any folder
```

With a built skin, the gallery also shows preview pages (mail, settings, login) written with
Elastic's structural ids and classes, styled by the built stylesheet, in light or dark mode,
left-to-right or right-to-left, at 1280 or 360 pixels:

```bash
# a folder with lumen/ (a build) next to the elastic/ it was built against, e.g. after
# lumen-mail install into a test copy of Roundcube:
LUMEN_GALLERY_SKINS=/path/to/roundcube/skins npm run gallery
LUMEN_GALLERY_SKINS=/path/to/roundcube/skins npm run build:gallery
```

A gallery built that way contains the compiled skin (CC BY-SA 3.0, an adaptation of Elastic) and
Elastic's fonts and images; it is for local review only. CI builds the gallery without a skin.

## Trying the skin in a test copy of Roundcube

Copy a Roundcube tree to a scratch folder, replace its `config/config.inc.php` with a minimal one
(an sqlite `db_dsnw` inside the copy, a random `des_key`, `skin` set to `lumen`, no plugins),
create the schema from `SQL/sqlite.initial.sql`, install the skin with
`lumen-mail install --roundcube <copy> --state-dir <scratch>/state`, and serve
`php -S 127.0.0.1:8080 -t <copy>/public_html`. The login page shows the skin; the palette appears
on every page after login. Never point a test copy at a live database or mail server.

## Releases

release-please keeps a release pull request open; merging it tags the release, runs the tests,
builds and tests the palette, builds the release package against the pinned Roundcube release
(`scripts/package.py`) and attaches it with `SHA256SUMS` and a provenance attestation. The
Roundcube version and its sha256 are pinned in `scripts/package.py`; bump both together.

## Label fit

Long labels must not end in an ellipsis: in German, Elastic itself cuts "Einstellungen",
"Dunkler Modus", "Allen antworten" and "Schnellantworten", and Sora is wider than Elastic's
Roboto ([ADR 0011](adr/0011-long-labels-get-room.md)). `scripts/screenshots/label-fit.mjs`
checks it in a test copy of Roundcube with the example-data plugin (the same setup as the README
screenshots, see "Screenshots"; it needs no mail server):

- it logs in once per skin (Lumen and Elastic, chosen in the preferences like a user would) and
  language, with the browser's language set, so Roundcube picks the language as it does for a new
  user;
- at 1280 x 800 (desktop), 1100 x 800 (Elastic's "normal" layout with labels), 1024 x 768 and
  800 x 1280 (Elastic's touch layout, the toolbar still in the header) and 360 x 740 (phone,
  with touch emulation) it opens the mail list, the folder menu, a message with its More, Mark,
  Reply all and Forward menus (on a phone the task menu, the folder list and the toolbar menus
  instead), compose, contacts and the settings pages Preferences, Folders, Identities and
  Responses;
- on each page, and in every frame of it, it measures each label in the task rail, the toolbars,
  the column headers and footers, the sidebar lists and the open menus: a label counts as cut
  when its text, or the padding around it, reaches past the edge of a box that hides overflow (or,
  with `text-overflow: ellipsis`, past the box's content edge, where the ellipsis starts), when
  one of its lines is hidden, or when a rail or toolbar button lies wholly outside its bar.

It prints a table per language and size with the labels each skin cuts, and exits with 1 if
Lumen cuts any label in German (`de_DE`), or in another language a label that Elastic shows in
full at the same size (each failure names the views); with 3 if the run itself fails (a page
error, a failed request, a failed login). The default languages are `en_US`, `de_DE`,
`fr_FR`, `es_ES`, `it_IT`, `nl_NL`, `pl_PL`, `ru_RU`, `pt_BR` and `ar` (right to left; Roundcube
does not set `dir="rtl"` for Elastic, so the page stays left to right with Arabic labels).

```bash
# test copy with Lumen and plugins/lumen_screenshots, served by php -S (see "Screenshots")
PLAYWRIGHT_CORE=/tmp/lumen-browser/node_modules/playwright-core/index.mjs \
  PLAYWRIGHT_BROWSERS_PATH=/tmp/lumen-browser/ms-playwright \
  node scripts/screenshots/label-fit.mjs http://127.0.0.1:8080
```

`LUMEN_FIT_LOCALES=de_DE,fr_FR` and `LUMEN_FIT_SIZES=desktop,phone` (of `desktop`, `normal`,
`touch`, `tablet`, `phone`) narrow the run, `LUMEN_FIT_JSON=fit.json` writes every finding,
`LUMEN_FIT_SHOTS=<folder>` saves a screenshot of every view. A whole run (ten languages, five
sizes, both skins) took 27 minutes on the project's server (2026-10-22, playwright-core 1.64.1,
Chromium 156 headless shell, `php -S`); its largest process stayed at 130 MB resident, and it ran
within the 300 MB cap of "Memory on a small server". It is not part of CI: it needs a Roundcube
tree, PHP and a browser download.
