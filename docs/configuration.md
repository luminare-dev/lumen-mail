# Configuration

## Commands

`PYTHONPATH=generator python3 -m lumen_mail <command> --help` prints every option.

| Command and option | Default | Description |
|---|---|---|
| `build --roundcube PATH` | required | Roundcube root (the folder with `program/` and `skins/`), read only |
| `build --out PATH` | required | the skin folder to create; must not exist or be empty |
| `build --no-palette` | off | build without the command palette bundle |
| `build --palette FILE` | `palette/dist/lumen-palette.js` | the built command palette |
| `build --work-dir PATH` | next to `--out` | where the temporary mirror tree goes |
| `build --node PATH` | `node` from `PATH` | the Node binary |
| `build --compiler CMD` | `node generator/lumen_mail/compile.mjs` | a compiler that speaks the same JSON protocol (tests) |
| `build --print-stamp` | off | print the stamp as JSON |
| `verify SKIN --roundcube PATH` | | check a built folder or `skins/lumen` |
| `verify --no-source` | off | do not compare the stamp's version with this checkout |
| `--source PATH`, `--node-modules PATH` | this checkout | where the generator finds its sources and the compiler |

Environment variables: `LUMEN_MAIL_SOURCE`, `LUMEN_MAIL_NODE_MODULES`, `LUMEN_MAIL_PALETTE`,
`LUMEN_MAIL_NODE` and `LUMEN_MAIL_COMPILER` set the same values. `NODE_OPTIONS` defaults to
`--max-old-space-size=320` for the compile.

Exit codes: 0 ok, 1 error (or `verify` found problems), 2 usage, 3 Elastic drift, 4 compile error.

## Roundcube options that matter

| Option | Effect on Lumen |
|---|---|
| `skin` | `lumen` makes it the system skin |
| `skins_allowed` | must contain `lumen` if set |
| `skin_logo` | a configured logo always wins; Lumen fills only the logo types that are not set (`dark`, `small`, `small-dark`) |
| `product_name` | shown in the page title and the login footer |
| `devel_mode` | loads Elastic's LESS in the browser, so the page looks like plain Elastic |

Lumen's `meta.json` sets one option, `favicon`, to its own icon; `skin_logo` with a `[favicon]`
entry still takes precedence.

## Secrets

Secrets never go into this repository, an issue or a log. The generator never reads Roundcube's
`config.inc.php` for `build` or `verify`. CI scans every commit with gitleaks; a leaked secret is
rotated first and removed from history second.
