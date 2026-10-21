# Update safety

How Lumen survives Roundcube updates that replace the whole Roundcube folder, how long webmail is
affected, and how to watch it.

## What KeyHelp does

KeyHelp's install log lists the commands, and its update log the timing: the updates to 1.6.11,
1.6.15 and 1.7.3 ran between 02:11 and 02:15 at night and took one to five seconds each.

1. `rm -rf /home/keyhelp/www/roundcube/*` removes every file and folder in the Roundcube root,
   `skins/lumen` included. The shell glob does not match names that start with a dot.
2. `tar --strip 1 -xf roundcube.tar.gz -C /home/keyhelp/www/roundcube` extracts the new release
   (on a first install, a download runs between the `rm` and the `tar`). The official archive
   stores `alec:alec` (1000:1000) for every file; on this server uid 1000 is `keyhelp`.
3. "Setup configuration files": `config/config.inc.php` is written again from KeyHelp's settings
   (Configuration → Webmail: product name, Interface skin, logos, plugins), then `chmod 0600`.
4. `chown -R keyhelp:keyhelp /home/keyhelp/www/roundcube`.

While Lumen is the system skin, Roundcube cannot render any page between step 1 and the moment
`skins/lumen` is back: it finds no templates for the configured skin and shows an error page.
This is the trade-off of a real skin (instead of a plugin that switches skins), accepted for this
project; the units below keep the window short.

## The three units

| Unit | Role |
|---|---|
| `lumen-mail-sync.path` | starts the service when `config/config.inc.php` or `program/include/iniset.php` is deleted or written, or `skins/lumen/meta.json` changes or disappears |
| `lumen-mail-sync.service` | runs `lumen-mail sync` once, as `keyhelp`, in a sandbox |
| `lumen-mail-sync.timer` | runs the service every 2 minutes as a fallback |

The path unit fires at step 1: `PathChanged=` reacts to the deletion of a watched file
(`IN_ATTRIB`, `IN_DELETE_SELF`; systemd.path(5), inotify(7)), and `rm` deletes `config/` and
`program/` before `skins/` (alphabetical order of the glob). In the simulation below it fired
14 ms after `rm` began. The service then runs while the update is still going on and waits for
the extracted tree itself.

How systemd 255 handles the watched paths (`src/core/path.c`), and what follows from it:

- An event on the watched file itself starts the service. Events on its parent folders only
  renew the watches; while doing so, systemd starts the service if the file has appeared or
  disappeared since it last looked. So a file whose folder is deleted and created again (as
  here) is watched again as soon as it exists.
- While the service runs, nothing is watched, and when it ends, changes made meanwhile do not
  start it again. sync compares the watched files before and after each pass and runs another
  pass if they changed. In the simulation, the run ended before KeyHelp wrote the new
  `config.inc.php`; that file appearing started a second, cheap run.
- The service cannot start itself in a loop: its own swaps of `skins/lumen` happen while nothing
  is watched. A manual `install` or `rollback` while the path unit watches starts at most one
  run, which finds everything current and writes nothing.

If the path unit misses an update, the timer runs the same service within 2 minutes.

## What one run does

1. **Wait for the tree.** Poll every 50 ms until `program/include/iniset.php`,
   `skins/elastic/meta.json` and `skins/elastic/templates/includes/footer.html` exist again (step 2
   has extracted Elastic's templates). Up to 300 s, then exit 75 (exit 1 and "webmail is down" at
   error level if the system skin is lumen). The footer matters: Lumen's footer wrapper includes
   Elastic's, and without it Roundcube's include would find the wrapper itself and recurse until
   PHP stops, a fatal error on every page instead of Roundcube's own error page.
2. **Fast restore.** If `skins/lumen` is missing or does not match its stamp (every file's sha256),
   copy the last good build from `/var/lib/lumen-mail/last-good` (or, if that copy is missing or
   damaged, the newest intact backup that is not from `uninstall`) to
   `<roundcube>/.lumen-mail/run-*/lumen` and rename it into `skins/`. No Node, no compile, no
   network. In the simulated updates below it took 0.003 to 0.009 s; every restore logs its time
   and source (`restored skins/lumen from the last good build in 0.004 s`). If `skins/` is not
   writable yet (step 4 not done and the archive had another owner), it retries every 200 ms. A
   copy that fails (disk full, file size limit) is logged as one readable error line.
3. **Freshness.** Compare the stamp of `skins/lumen` with the installed Roundcube version, a
   sha256 digest of Elastic's LESS sources and templates, the lumen-mail version and a digest of
   lumen-mail's own sources. If all match, save the build as the last good copy when that copy is
   missing, and stop. This is the 2-minute no-op: it writes nothing and starts no compiler.
4. **Rebuild** (stale stamp only). Wait until the watched files have not changed for 5 s (KeyHelp
   has finished) and check again whether the build is still stale (the first look may have
   hashed a half-extracted Elastic). Skip if the last rebuild for exactly these inputs failed and
   its back-off has not expired, and skip if less than 300 MB of memory is available. Then compile
   in a temporary folder, verify, flush the new files to disk, and, if Roundcube did not change
   during the build, swap it into `skins/lumen` with one `renameat2(RENAME_EXCHANGE)` and save it
   as the new last good build (also flushed before its rename). The replaced build goes to
   `/var/lib/lumen-mail/backups/` (the newest 5 are kept).
5. **Check again.** If the watched files changed during the run, run steps 1 to 4 again (at most
   four passes). This matters because a path unit does not watch while its service runs.

**Webmail down.** If the system skin is lumen and there is no usable `skins/lumen` and nothing to
restore it from (the state folder was lost or damaged), every page fails. sync then builds at once:
without the back-off, and with an emergency memory floor of 150 MB instead of 300 MB (the compile
peaks at about 115 MB and runs inside the unit's 300M cgroup as the OOM killer's first victim). Until
`skins/lumen` is back, every run logs `webmail is down: ...` at error level and exits 1, so the
unit shows as failed.

The restored build is made for the old Roundcube release. It works with the new Elastic in most
cases (Elastic's markup rarely changes within a series); some of Elastic's own icons may show
with a stale cache-buster until the rebuild a few seconds later replaces it.

## Expected error window

Measured on scratch copies of this server's Roundcube 1.7.3 (2026-10-21). A script ran KeyHelp's
steps (`rm -rf <root>/*`, `tar --strip 1 -xzf` of a 6.5 MB archive of the same tree, a new
`config.inc.php` written in place, `chmod 600`, `chown -R`). The path unit was simulated with a
port of systemd 255's `PathChanged=` logic (the inotify watches of `path_spec_watch()`, the trigger
rules of `path_spec_fd_event()` and `path_spec_check_good()`, no watching while the service runs)
that started `lumen-mail sync` from an `install-runtime` copy, inside a 300 MB memory scope. A
poller fetched the login page every 50 ms. Times are from the start of `rm`:

| Step | Same release | New release (rebuild) |
|---|---|---|
| path unit fires (deletion of `config/config.inc.php`) | +0.014 s | +0.014 s |
| `rm -rf` done | +0.10 s | +0.10 s |
| `skins/lumen` restored from the last good build | during the extraction: the run had ended at +0.33 s (copy 0.003 s) | before +0.45 s (copy 0.004 s; the run went on to rebuild, so only its end is timed) |
| extraction done | +0.42 s | +0.38 s |
| new `config.inc.php` written | +0.47 s | +0.43 s |
| login page served with Lumen | +0.48 s (10 ms after the config) | +0.45 s (22 ms after the config), by the restored build |
| rebuild for the new release | none needed | swapped in at +7.3 s (5 s settle, 1.7 s build); the poller saw no interruption |

During the update the login page answered 500 and 404 (Roundcube without its files), then
Roundcube's own "Internal Error" page (no `config.inc.php` yet). `skins/lumen` was always back
before the page was served with the new configuration, and Roundcube's error log had no "Error
loading template" line, so Lumen added no error time of its own. The rebuild replaces a working
build with a current one through one atomic exchange.

Two more cases from the same tests:

- **Too little memory for the rebuild.** In one run `MemAvailable` fell to 381 MB during the
  update. sync restored the skin, deferred the rebuild (exit 75, logged once at notice) and the
  restored build kept serving every page and asset; a later run rebuilt it.
- **A missed trigger.** When nothing watched during the update (the path unit started too late),
  the login page stayed on Roundcube's 404 "Error loading template" page. The next sync (what the
  timer runs every 2 minutes) restored the skin in 0.007 s and rebuilt it in 1.7 s.

If the units are not running at all (not enabled, runtime missing), the error lasts until
someone runs `lumen-mail sync` or switches the Interface skin back to Elastic.

## Why these choices

- **The service runs as `keyhelp`**, the owner of the Roundcube tree, not as root. It can write
  `skins/` and the Roundcube root (where it stages), systemd creates `/var/lib/lumen-mail` for it
  (`StateDirectory=`), and Node and the runtime in `/opt/lumen-mail` are world-readable. Files it
  writes are owned by `keyhelp` like the rest of Roundcube; KeyHelp's own `chown -R` changes
  nothing. Tested on a scratch copy: as `keyhelp` (empty environment, no home folder), sync
  restored the skin in 0.003 s and rebuilt it in 1.4 s, every file it wrote belongs to
  `keyhelp`, `status` read the mode-600 `config.inc.php`, and `uninstall` refused with exit 5.
- **The whole Roundcube root is writable in the sandbox**, not only `skins/`: KeyHelp removes
  `skins/` itself, and a missing `ReadWritePaths=`/`BindPaths=` source would fail the unit at
  start. Each writable path is a separate mount inside the sandbox, and `rename(2)` does not
  cross mounts (`EXDEV`), so staging must be on the same mount as `skins/`:
  `<roundcube>/.lumen-mail/` is. It also survives `rm -rf <roundcube>/*` (the glob skips dot
  names), and it is outside `skins/`, so Roundcube's skin chooser never lists it.
- **No start rate limit** on the service: if systemd's start limit were hit, it would fail the
  path unit too, which then stops watching until someone restarts it.
- **`OOMScoreAdjust=1000`, `MemoryMax=300M` and the 300 MB check**: the server is small and
  ClamAV holds about 1 GB. The real compile against Roundcube 1.7.3's Elastic peaked at 106 to
  115 MB RSS (`/usr/bin/time`, V8 heap capped at 256 MB by `NODE_OPTIONS`), so 300M leaves room. If
  memory runs out anyway, the kernel kills the compile first. The check was 400 MB at first, but
  `MemAvailable` on this host is often 290 to 420 MB, which deferred rebuilds for hours; 300 MB is
  the compile's peak plus about 150 MB. A deferral that lasts 6 hours is logged as a warning.
- **Never as root.** The Roundcube owner also runs the webmail's PHP and can change Elastic's
  LESS, which the rebuild compiles, and everything in the state folder. The service runs as that
  user; a manual command started as root drops to it after preparing the state folder
  ([command reference](cli.md#running-as-root)). The compile refuses every `@plugin` and reads
  no file outside the build's folders.
- **Exit code 75 counts as success** (`SuccessExitStatus=75`): "try again later" (lock busy,
  update still running, low memory, back-off) is not a failure; the timer retries.

## Monitoring

```bash
journalctl -u lumen-mail-sync.service -p notice --since today   # restores, rebuilds, failures
journalctl -u lumen-mail-sync.service -p warning                # only problems
systemctl list-timers lumen-mail-sync.timer
systemctl status lumen-mail-sync.path                           # must be "active (waiting)"
/opt/lumen-mail/bin/lumen-mail check --roundcube /home/keyhelp/www/roundcube; echo "exit $?"
/opt/lumen-mail/bin/lumen-mail status --roundcube /home/keyhelp/www/roundcube --json
```

| Journal message (priority) | Meaning |
|---|---|
| `restored skins/lumen from the last good build in N s` (notice) | a Roundcube update or something else removed or damaged `skins/lumen`; it is back |
| `restored skins/lumen from the backup <name> in N s` (notice) | the same, but the last good copy was missing or damaged; the next current run saves the restored build as the last good copy again |
| `rebuilt skins/lumen for Roundcube X (Lumen Y) in N s` (notice) | the stamp was stale; the new build is active and saved as the last good copy |
| `rebuild deferred: only N MB of memory available ...` (notice once per episode, warning after 6 h and every 6 h) | the timer retries every 2 minutes; the active build stays |
| `webmail is down: no usable skins/lumen while the system skin is lumen; ...` (error, every run) | nothing could be restored and the emergency build failed or waits; [runbook](runbook.md) |
| `rebuild failed (exit N): ...` (error) | the active build stays; next attempt after 10 min, 30 min, 1 h, 2 h, then every 6 h, or at once when the inputs change |
| `the Roundcube tree ... is still incomplete after 300 s` (warning) | the update did not finish; the timer retries |

`check` exit codes for scripts: 0 current, 10 sync needed, 6 not installed, others are errors
([command reference](cli.md#exit-codes)). The systemd unit shows as failed only after a failed
rebuild (exit 1, 3 or 4) or while webmail is down (exit 1).

## Test it

Without touching the live skin: `lumen-mail sync --dry-run --roundcube <root>` prints what a run
would do. To exercise the sandboxed rebuild path through the unit:

```bash
/opt/lumen-mail/bin/lumen-mail request-rebuild --roundcube /home/keyhelp/www/roundcube
systemctl start lumen-mail-sync.service
journalctl -u lumen-mail-sync.service -n 5 --no-pager
```

The restore path can be tested the same way while the Interface skin is still Elastic: move
`skins/lumen` away and start the service.
