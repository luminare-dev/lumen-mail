# 0008. Restore at once, rebuild later: a sync unit that runs as the Roundcube owner

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Lumen is a real skin and, on the KeyHelp server it was made for, the system skin (owner decision:
a skin selected in KeyHelp's Interface skin field, no plugin). KeyHelp updates Roundcube with
`rm -rf <roundcube>/*`, a fresh extraction, a rewritten `config.inc.php` and `chown -R`, all within
about two seconds at night. From the moment `skins/lumen` is gone until it is back, every webmail
page fails. A rebuild needs Node and a LESS compile on a small server where ClamAV holds a
gigabyte and an out-of-memory kill has happened before.

## Considered options

1. Rebuild after every update, nothing else: the error window lasts as long as the compile, and a
   failed compile leaves webmail broken.
2. Restore a copy of the last good build first, without Node, then rebuild against the new Elastic
   when the tree is quiet; keep the restored build if the rebuild fails.
3. Keep the system skin on Elastic and switch users to Lumen with a plugin only while the skin is
   present (the earlier design, replaced by the owner's decision).

Trigger: a timer only (up to its interval of downtime), or a systemd path unit on files that the
update deletes, plus a timer as a fallback.

Privileges: run as root (always able to write, needs `chown`), or as `keyhelp`, the owner of the
whole Roundcube tree.

## Decision

Option 2, triggered by `lumen-mail-sync.path` (`PathChanged=` on `config/config.inc.php`,
`program/include/iniset.php` and `skins/lumen/meta.json`: the first two are deleted by the update's
`rm` before `skins/`) and `lumen-mail-sync.timer` every 2 minutes. The service runs as `keyhelp`
with `StateDirectory=lumen-mail`, `ProtectSystem=strict`, `ProtectHome=tmpfs` and
`BindPaths=<roundcube>`.

- The whole Roundcube root is writable, because KeyHelp removes `skins/` itself (a missing bind
  source fails the unit at start) and because `rename(2)` cannot cross mount points: staging lives
  in `<roundcube>/.lumen-mail/`, on the same bind mount as `skins/`, outside the skin list and
  outside the reach of `rm -rf <roundcube>/*`.
- Every swap is one `renameat2(RENAME_EXCHANGE)`, so `skins/lumen` never disappears during a
  rebuild or an install; replaced builds go to `/var/lib/lumen-mail/backups/`.
- A path unit does not watch while its service runs, and when the service ends `PathChanged=`
  does not fire for changes made meanwhile. sync therefore compares the watched files before and
  after each pass and runs another pass when they changed.
- No start rate limit on the service: when it is hit, systemd fails the path unit too.
- Exit code 75 ("try again later") counts as success; failed rebuilds back off per input set.
- `LogLevelMax=notice` drops systemd's own per-run info lines, so the 2-minute no-op is silent.
- Before the compiler starts, sync requires 400 MB of `MemAvailable`; the unit has
  `MemoryMax=350M` and `OOMScoreAdjust=1000`.

## Consequences

- Good: in a simulated update on this server `skins/lumen` was back during the extraction, before
  KeyHelp wrote the new configuration, so Lumen added no error time of its own; a broken rebuild
  never breaks webmail; the service cannot write outside the Roundcube root and its state
  folder and has no capabilities.
- Good: the same units work on any Roundcube after changing the path and the user.
- Bad: the service needs write access to the whole Roundcube root (it owns it anyway as
  `keyhelp`); the sandbox cannot narrow this to `skins/`.
- Bad: right after an update, users see the previous build (made for the old Elastic) for the
  seconds until the rebuild finishes; some Elastic icons may carry a stale cache-buster meanwhile.
