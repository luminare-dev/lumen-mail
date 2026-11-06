# Update safety

KeyHelp replaces the whole Roundcube folder on every Roundcube update (`rm -rf <root>/*`, extract
the new release, rewrite `config.inc.php`, `chown -R`). That removes `skins/lumen`, and while Lumen
is the system skin every page fails until it is back. The sync units put it back within a second
and rebuild it for the new release.

## The units

| Unit | Role |
|---|---|
| `lumen-mail-sync.path` | starts the service when `config/config.inc.php` or `program/include/iniset.php` is deleted or written, or `skins/lumen/meta.json` changes |
| `lumen-mail-sync.service` | runs `lumen-mail sync` once, as the Roundcube owner (`keyhelp`), sandboxed, `MemoryMax=300M` |
| `lumen-mail-sync.timer` | runs the service every 2 minutes as a fallback |

## What one run does

1. **Wait for the tree** until Roundcube and Elastic's footer template are back (up to 300 s,
   then exit 75).
2. **Restore** `skins/lumen` from the last good build in `/var/lib/lumen-mail` (or the newest
   backup) if it is missing or damaged. No Node, no compile; it takes milliseconds.
3. **Check freshness**: the stamp against the Roundcube version, Elastic's sources and the
   lumen-mail version. If everything matches, stop without writing anything.
4. **Rebuild** if the stamp is stale: wait until the update has settled for 5 s, skip if less
   than 300 MB of memory is available or a back-off is running, compile in a temporary folder,
   verify, and swap it in atomically. The replaced build goes to `backups/` (5 are kept).
5. **Run again** if the watched files changed meanwhile (a path unit does not watch while its
   service runs).

If the system skin is lumen and nothing can be restored, sync builds at once with a 150 MB memory
floor and logs `webmail is down` until it succeeds.

Exit code 75 means "try again later" (lock busy, update still running, low memory) and counts as
success for the unit.

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
