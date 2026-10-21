# Configuration

## Commands

Every command, option, environment variable, file and exit code is in the
[command reference](cli.md). The sync units in `contrib/systemd/` are described in
[update safety](update-safety.md); their paths and user are those of a KeyHelp server and are
adapted as shown in [the installation guide](install.md#plain-roundcube).

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
`config.inc.php` for `build`, `verify` or `install`. `uninstall` and `status` read only the `skin`
setting from it (a small PHP tokenizer, no PHP is run) and print nothing else from the file;
`check` and `sync` do the same, and only when there is neither a `skins/lumen` nor a last good
build (to decide whether a new build is urgent). CI scans every commit with gitleaks; a leaked secret is rotated first and removed from
history second.
