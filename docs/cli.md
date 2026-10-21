# Command reference

Run the generator as `/opt/lumen-mail/bin/lumen-mail <command>` (after `install-runtime`) or, in
a checkout, `PYTHONPATH=generator python3 -m lumen_mail <command>`. `<command> --help` lists every
option. Commands that write accept `--dry-run`, which prints the plan and writes nothing.

## Commands

| Command | What it does |
|---|---|
| `build --roundcube R --out DIR` | compiles the skin into `DIR` (new or empty); reads `R` only |
| `verify DIR --roundcube R` | checks a build or `skins/lumen` against `R`; one `FAIL` line per problem |
| `install --roundcube R` | builds in a temporary folder, verifies, swaps `R/skins/lumen` in atomically, moves the previous one to the backups, saves the last good copy, prints the undo commands |
| `install --from DIR --roundcube R` | the same with a built folder (for example from a release package); `--allow-mismatch` accepts a build for another release of the same series |
| `check --roundcube R` | read-only: exit 0 if `skins/lumen` is complete and current and the last good copy matches it, 10 if `sync` has work to do |
| `sync --roundcube R` | what the unit runs: restore at once, rebuild if stale ([update safety](update-safety.md)); with no build and no last good copy it builds one if the system skin is lumen, otherwise it does nothing |
| `status --roundcube R` | installed build, last good copy, backups, system skin, sync state (`--json`) |
| `rollback --roundcube R` | puts the newest intact backup (or `--backup NAME`) back and holds it |
| `resume --roundcube R` | clears the hold: sync rebuilds again when the stamp is stale |
| `request-rebuild --roundcube R` | the next `sync` run rebuilds even if the stamp is current |
| `uninstall --roundcube R` | moves `skins/lumen` to the backups and stops sync from restoring it; refused while the system skin is lumen (`--force` overrides) |
| `install-runtime --prefix P` | copies the generator, the sources, the palette bundle and the compiler packages to `P` (default `/opt/lumen-mail`) and writes `P/bin/lumen-mail` |

## Options

| Option | Default | Commands |
|---|---|---|
| `--roundcube PATH` | `$LUMEN_MAIL_ROUNDCUBE` | all but `install-runtime` |
| `--state-dir PATH` | `$LUMEN_MAIL_STATE_DIR`, `$STATE_DIRECTORY` (systemd), `/var/lib/lumen-mail` | lifecycle commands |
| `--owner SPEC` | `auto`: as root, the owner of `<roundcube>/skins`; otherwise unchanged | writing commands |
| `--keep N` | 5 | backups kept in `<state>/backups/` |
| `--lock-timeout S` | 30 (`$LUMEN_MAIL_LOCK_TIMEOUT`) | seconds to wait for another run, then exit 75 |
| `--wait S` | 300 (`$LUMEN_MAIL_WAIT`) | `sync`: how long to wait for a complete Roundcube tree |
| `--settle S` | 5 (`$LUMEN_MAIL_SETTLE`) | `sync`: quiet seconds before a rebuild |
| `--min-available-mb N` | 400 (`$LUMEN_MAIL_MIN_AVAILABLE_MB`) | `sync`: MemAvailable needed to start the compiler; 0 turns the check off |
| `--rebuild` | off | `sync`: rebuild even if current |
| `--no-palette`, `--require-palette`, `--palette FILE` | use `palette/dist/lumen-palette.js` when it exists | building commands, `check`, `status` |
| `--source PATH`, `--node-modules PATH` | this checkout or runtime (`$LUMEN_MAIL_SOURCE`, `$LUMEN_MAIL_NODE_MODULES`) | all |
| `--node PATH`, `--compiler CMD` | `node` from `PATH` (`$LUMEN_MAIL_NODE`, `$LUMEN_MAIL_COMPILER`) | building commands |
| `--work-dir PATH` | `$TMPDIR` (`build`: next to `--out`) | building commands |
| `--config FILE` | `<roundcube>/config/config.inc.php`, read only for its `skin` setting; nothing else from the file is printed | `uninstall`, `status`, `check`, `sync` |
| `--json` | off | `check`, `status` |
| `-q`, `-v` | | only warnings and errors; also debug output |

`NODE_OPTIONS` defaults to `--max-old-space-size=256` for the compile unless it is set.

## Files

| Path | Content |
|---|---|
| `<roundcube>/skins/lumen/` | the installed skin; `lumen-build.stamp` lists every file's sha256 and what it was built from |
| `<roundcube>/.lumen-mail/` | staging during a run (removed afterwards; leftovers of an interrupted run are removed by the next one) |
| `<state>/last-good/` | copy of the last build that passed verify; the fast restore copies it back |
| `<state>/backups/<time>-<reason>/lumen/` | replaced or removed builds (`replaced-install`, `replaced-stale`, `replaced-broken`, `replaced-rollback`, `uninstall`) |
| `<state>/sync-state.json` | back-off after a failed rebuild, memory deferral, hold, uninstalled marker |
| `<state>/ROLLBACK.txt` | the undo commands of the last install, rollback or uninstall |
| `<state>/lock` | `flock(2)` lock shared by every writing command |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | ok; `check`: everything current; `sync`: done or nothing to do |
| 1 | error; `verify`: problems found; `sync`: the rebuild failed and the active build stays |
| 2 | usage |
| 3 | Elastic drift: the installed Elastic lacks a file, marker or variable Lumen relies on |
| 4 | LESS compile error |
| 5 | refused: `uninstall` while the system skin is (or may be) lumen; `install-runtime` over a folder that is not a runtime |
| 6 | `check`: not installed (no `skins/lumen`, no last good copy, and the system skin is not lumen) |
| 10 | `check`: sync needed (missing, damaged or stale build, missing last good copy, rebuild requested, or no build at all while the system skin is lumen) |
| 75 | try again later: lock busy, Roundcube tree incomplete, too little memory, back-off after a failed rebuild; the unit counts it as success |

## Journal

Under systemd (`$JOURNAL_STREAM` set) every line carries a syslog priority: restores and rebuilds
at notice, problems at warning or error, everything else at info. The unit sets
`LogLevelMax=notice`, so a run with nothing to do leaves no line in the journal.
