# Update safety

How Lumen survives Roundcube updates that replace the whole Roundcube folder, how long webmail is
affected, and how to watch it.

## What KeyHelp does

KeyHelp's install and update logs show this sequence for every Roundcube update (1.6.11, 1.6.15
and 1.7.3 so far, each around 02:14 at night, each within about two seconds):

1. `rm -rf /home/keyhelp/www/roundcube/*` removes every file and folder in the Roundcube root,
   `skins/lumen` included. The shell glob does not match names that start with a dot.
2. `tar --strip 1 -xf roundcube.tar.gz -C /home/keyhelp/www/roundcube` extracts the new release.
   The official archive stores the owner `1000:1000` for every file.
3. "Setup configuration files": `config/config.inc.php` is written again from KeyHelp's settings
   (Configuration → Webmail: product name, Interface skin, logos, plugins).
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

The path unit is meant to fire at step 1 already: `PathChanged=` reacts to the deletion of a
watched file (`IN_DELETE_SELF`, systemd.path(5) and inotify(7)), and `rm` deletes `config/` and
`program/` before `skins/` (alphabetical order of the glob). The service then starts while the
update is still running and waits for the extracted tree itself. If the path unit misses an
update, the timer runs the same service within 2 minutes.

## What one run does

1. **Wait for the tree.** Poll every 50 ms until `program/include/iniset.php` and
   `skins/elastic/meta.json` exist again (step 2 has reached `skins/`). Up to 300 s, then exit 75.
2. **Fast restore.** If `skins/lumen` is missing or does not match its stamp (every file's sha256),
   copy the last good build from `/var/lib/lumen-mail/last-good` to
   `<roundcube>/.lumen-mail/run-*/lumen` and rename it into `skins/`. No Node, no compile, no
   network. In the simulated updates below it took 0.004 to 0.009 s; every restore logs its time
   (`restored skins/lumen from the last good build in 0.004 s`). If `skins/` is not writable yet
   (step 4 not done and the archive had another owner), it retries every 200 ms.
3. **Freshness.** Compare the stamp of `skins/lumen` with the installed Roundcube version, a
   sha256 digest of Elastic's LESS sources and templates, the lumen-mail version and a digest of
   lumen-mail's own sources. If all match, save the build as the last good copy when that copy is
   missing, and stop. This is the 2-minute no-op: it writes nothing and starts no compiler.
4. **Rebuild** (stale stamp only). Wait until the watched files have not changed for 5 s (KeyHelp
   has finished), skip if the last rebuild for exactly these inputs failed and its back-off has not
   expired, skip if less than 400 MB of memory is available. Then compile in a temporary folder,
   verify, and, if Roundcube did not change during the build, swap it into `skins/lumen` with one
   `renameat2(RENAME_EXCHANGE)` and save it as the new last good build. The replaced build goes to
   `/var/lib/lumen-mail/backups/` (the newest 5 are kept).
5. **Check again.** If the watched files changed during the run, run steps 1 to 4 again (at most
   four passes). This matters because a path unit does not watch while its service runs.

The restored build is made for the old Roundcube release. It works with the new Elastic in most
cases (Elastic's markup rarely changes within a series); some of Elastic's own icons may show
with a stale cache-buster until the rebuild a few seconds later replaces it.

## Expected error window

Measured on a scratch copy of this server's Roundcube 1.7.3 (2026-10-21): a script ran KeyHelp's
steps (`rm -rf`, `tar --strip 1 -xzf` of a 6.5 MB release archive, a new `config.inc.php`,
`chown -R`) and started `sync` together with the `rm`, as the path unit does, while a poller
fetched the login page every 50 ms.

| Step | Same release | New release (rebuild) |
|---|---|---|
| `rm -rf <roundcube>/*` | 0.22 s | 0.09 s |
| extraction | 0.30 s | 0.28 s |
| `skins/lumen` restored | during the extraction, in 0.009 s | during the extraction, in 0.004 s |
| new `config.inc.php` written | 0.25 s after the extraction | 0.33 s after the extraction |
| login page | error (500/404) during `rm` and extraction, plain Elastic until the config existed, then Lumen | the same; the rebuild followed 3 s after KeyHelp's last step (stand-in compiler) |

`skins/lumen` was back before KeyHelp had written the new configuration, so Lumen added no error
time of its own: the error pages came from the update itself (Roundcube without its files, then
without its configuration). The rebuild that follows replaces a working build with a current one
and causes no error window (`skins/lumen` is exchanged atomically, never removed).

If the service is not running (units not enabled, runtime missing), the window lasts until
someone runs `lumen-mail sync` or switches the Interface skin back to Elastic.

## Why these choices

- **The service runs as `keyhelp`**, the owner of the Roundcube tree, not as root. It can write
  `skins/` and the Roundcube root (where it stages), systemd creates `/var/lib/lumen-mail` for it
  (`StateDirectory=`), and Node and the runtime in `/opt/lumen-mail` are world-readable. Files it
  writes are owned by `keyhelp` like the rest of Roundcube; KeyHelp's own `chown -R` changes
  nothing.
- **The whole Roundcube root is writable in the sandbox**, not only `skins/`: KeyHelp removes
  `skins/` itself, and a missing `ReadWritePaths=`/`BindPaths=` source would fail the unit at
  start. Each writable path is a separate mount inside the sandbox, and `rename(2)` does not
  cross mounts (`EXDEV`), so staging must be on the same mount as `skins/`:
  `<roundcube>/.lumen-mail/` is. It also survives `rm -rf <roundcube>/*`, and Roundcube's skin
  list ignores names that start with a dot.
- **No start rate limit** on the service: if systemd's start limit were hit, it would fail the
  path unit too, which then stops watching until someone restarts it.
- **`OOMScoreAdjust=1000`, `MemoryMax=300M` and the 400 MB check**: the server is small and
  ClamAV holds about 1 GB. The real compile against Roundcube 1.7.3's Elastic peaked at 114 MB
  RSS (`/usr/bin/time`, V8 heap capped at 256 MB by `NODE_OPTIONS`), so 300M leaves room. If
  memory runs out anyway, the kernel kills the compile first.
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
| `rebuilt skins/lumen for Roundcube X (Lumen Y) in N s` (notice) | the stamp was stale; the new build is active and saved as the last good copy |
| `rebuild deferred: only N MB of memory available` (notice, once per episode) | the timer retries every 2 minutes; the active build stays |
| `rebuild failed (exit N): ...` (error) | the active build stays; next attempt after 10 min, 30 min, 1 h, 2 h, then every 6 h, or at once when the inputs change |
| `the Roundcube tree ... is still incomplete after 300 s` (warning) | the update did not finish; the timer retries |

`check` exit codes for scripts: 0 current, 10 sync needed, 6 not installed, others are errors
([command reference](cli.md#exit-codes)). The systemd unit shows as failed only after a failed
rebuild (exit 1, 3 or 4).

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
