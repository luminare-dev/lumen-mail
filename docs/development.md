# Development

Installing the skin on a server is in [install.md](install.md).

## Layout

| Path | What it is |
|---|---|
| `src/less/` | Lumen's LESS: tokens, Elastic variable overrides, the component layer and the contrast pairs |
| `skin/` | the skin's static files: `meta.json`, the footer wrapper template, `lumen.js`, localization, logos, Sora, thumbnail |
| `palette/` | the command palette (TypeScript, React) and its Vitest tests |
| `gallery/` | the design-system gallery (React, Vite) |
| `generator/lumen_mail/` | the Python package behind `python3 -m lumen_mail` (standard library only) and `compile.mjs`, the LESS compile driver |
| `contrib/systemd/` | the sync service, path and timer units |
| `scripts/` | release package, contrast table, palette bundle check, font and thumbnail builders, repository checks, screenshots |
| `tests/` | Python tests and `tests/js/` (`node --test`) |

No Roundcube or Elastic file is in the repository; the generator reads the installed Elastic at
build time.

## Tools

Node.js 22 (or 20.19+) with npm, and Python 3.10+. For the real-compile test you need a Roundcube
tree, for example from `python3 -I scripts/package.py fetch --dest /tmp/roundcube`.

```bash
npm ci --ignore-scripts --no-audit --no-fund
```

## Commands

| Command | What it does |
|---|---|
| `npm run typecheck` | TypeScript over the palette, its tests and the gallery |
| `npm test` | Vitest: the palette and the gallery's contrast maths |
| `npm run test:js` | `node --test` for `skin/lumen.js` and `gallery/data.mjs` |
| `npm run build:palette` | `palette/dist/lumen-palette.js`, then the size and API check |
| `npm run build:gallery` / `npm run gallery` | build the gallery / run its dev server |
| `python3 -m unittest discover -s tests` | Python tests; the real compile runs when `node_modules` and a Roundcube tree exist (`LUMEN_MAIL_TEST_ROUNDCUBE`) |
| `python3 scripts/contrast.py --check` | every colour pair passes WCAG 2.2 AA and `docs/contrast.md` is current |
| `python3 scripts/forbidden_words.py` | the wording check CI runs |

### Memory

On a small server, run heavy steps with a memory cap:

```bash
NODE_OPTIONS=--max-old-space-size=256 systemd-run --scope --quiet --collect \
  -p MemoryMax=300M -p MemorySwapMax=0 choom -n 1000 -- nice -n 19 npm test
```

Vitest runs with one worker for the same reason (`palette/vitest.config.js`). Adding new npm
packages needs more than 300 MB; do that on a bigger machine.

## The command palette

`palette/src/main.ts` is built by Vite into one IIFE, which every build copies into
`skins/lumen/`. Items run through `rcmail.command()` or a click on Elastic's own button, so
Roundcube's own checks apply. Nothing is fetched or stored.

Adding a label: the key in `i18n.ts`, a `<roundcube:add_label>` in the footer wrapper, and for
the skin's own labels the text in both localization files. `tests/test_palette_consistency.py`
checks they agree.

The bundle's banner holds a digest of its sources; `build`, `install` and `install-runtime`
stop with "out of date" until `npm run build:palette` has run after a change.

## The gallery

```bash
npm run gallery
LUMEN_GALLERY_SKINS=/path/to/roundcube/skins npm run gallery   # with preview pages
```

`LUMEN_GALLERY_SKINS` points at a folder with a built `lumen/` next to its `elastic/`. A gallery
built that way contains the compiled skin and Elastic's assets, so keep it local.

## Trying the skin in a test copy of Roundcube

Copy a Roundcube tree to a scratch folder, give it a minimal `config/config.inc.php` (sqlite
`db_dsnw` inside the copy, a random `des_key`, `skin` set to `lumen`), create the schema from
`SQL/sqlite.initial.sql`, run `lumen-mail install --roundcube <copy> --state-dir <scratch>/state`
and serve it with `php -S 127.0.0.1:8080 -t <copy>/public_html`. Never point a test copy at a
live database or mail server.

## Screenshots

`scripts/screenshots/lumen_screenshots/` is a Roundcube plugin with an in-memory example mailbox
(any password logs in; it only works under `php -S` from loopback). `capture.mjs` logs in and
takes the four README images in headless Chromium.

1. Make a test copy as above, copy the plugin to `<copy>/plugins/lumen_screenshots/` and enable
   it in the copy's config.
2. Install `playwright-core` and Chromium's headless shell outside the repository, then:

   ```bash
   PLAYWRIGHT_CORE=/tmp/lumen-browser/node_modules/playwright-core/index.mjs \
     PLAYWRIGHT_BROWSERS_PATH=/tmp/lumen-browser/ms-playwright \
     node scripts/screenshots/capture.mjs http://127.0.0.1:8080 docs/screenshots
   ```

## Label fit

`scripts/screenshots/label-fit.mjs` uses the same setup and checks, in several languages and
window sizes, that Lumen cuts no label that Elastic shows in full (and none in German). It exits
1 on a cut label and 3 if the run fails. `LUMEN_FIT_LOCALES` and `LUMEN_FIT_SIZES` narrow the
run. It needs PHP and a browser, so it is not part of CI.

## Releases

release-please keeps a release PR open; merging it tags the release and attaches the package
built against the pinned Roundcube, with `SHA256SUMS` and a provenance attestation. The Roundcube
version and sha256 are pinned in `scripts/package.py`; bump both together.
