# Runbook

Commands below use the KeyHelp paths; `R=/home/keyhelp/www/roundcube` and
`LM=/opt/lumen-mail/bin/lumen-mail`.

## Failure: webmail shows an error page after a Roundcube update

| | |
|---|---|
| **Meaning** | `skins/lumen` is missing or incomplete while Lumen is the system skin. KeyHelp removes it with the whole Roundcube folder during an update; the sync units normally restore it within a second of the extraction ([update safety](update-safety.md)). |
| **Impact** | Every webmail page fails to render for every user until the folder is back. |
| **Diagnosis** | `systemctl status lumen-mail-sync.path lumen-mail-sync.timer`; `journalctl -u lumen-mail-sync.service -p notice -n 20`; `$LM check --roundcube $R; echo $?`; `ls $R/skins/`. |
| **Mitigation** | `systemctl start lumen-mail-sync.service` (restores the last good build); if that fails, set KeyHelp's Interface skin to Elastic. |
| **Fix** | Find out why the units did not run (disabled, runtime missing, `AssertPathExists` failed) and enable them again. |

## Failure: `rebuild failed` in the journal (exit 1, 3 or 4)

| | |
|---|---|
| **Meaning** | After a Roundcube or lumen-mail update the new build failed: exit 3 means the new Elastic lacks something Lumen relies on (named in the message), 4 a LESS compile error, 1 anything else. |
| **Impact** | None for users: the previous build stays active (stale but working). The next attempt follows after 10 min, 30 min, 1 h, 2 h, then every 6 h, or at once when the inputs change. |
| **Diagnosis** | `journalctl -u lumen-mail-sync.service -p err`; `$LM status --roundcube $R`. |
| **Mitigation** | Nothing urgent. To stop the retries for a known-bad combination: `$LM rollback --roundcube $R` holds the current build. |
| **Fix** | Update lumen-mail (`install-runtime`, then `$LM request-rebuild` and `systemctl start lumen-mail-sync.service`), or adapt `src/less/` and release a fix. |

## Warning: `rebuild deferred: only N MB of memory available`

| | |
|---|---|
| **Meaning** | A rebuild is due, but less than 400 MB of memory is available, so the compiler was not started. |
| **Impact** | None for users; the active build stays. The timer retries every 2 minutes and logs only the first deferral. |
| **Diagnosis** | `free -m`; `$LM status --roundcube $R`. |
| **Mitigation** | Wait; KeyHelp updates run at night, when memory is usually free. |
| **Fix** | If it never clears, lower `--min-available-mb` in a drop-in (not below the service's `MemoryMax=`) or free memory. |

## Warning: `the Roundcube tree ... is still incomplete after 300 s`

| | |
|---|---|
| **Meaning** | `program/include/iniset.php` or `skins/elastic/meta.json` stayed missing: an update was interrupted or Roundcube was removed. |
| **Impact** | Webmail is broken for reasons outside lumen-mail; lumen-mail cannot restore into a missing tree. |
| **Diagnosis** | `ls $R`; KeyHelp's `/var/log/keyhelp/cronjob/panel-update.log`. |
| **Mitigation** | Let KeyHelp finish or repair the Roundcube installation; the timer restores Lumen as soon as the tree is back. |
| **Fix** | As above. |

## Failure: the build stops with exit code 3 (Elastic drift) during `install`

| | |
|---|---|
| **Meaning** | The installed Elastic changed something Lumen relies on (named in the message). |
| **Impact** | No new build; the installed `skins/lumen`, if any, keeps working with the old compiled CSS. |
| **Diagnosis** | The message lists each missing file, marker or variable with the Lumen file and line that uses it. |
| **Mitigation** | Keep the current skin; `check` reports the stale stamp until a rebuild succeeds. |
| **Fix** | Update lumen-mail, or adapt `src/less/` to the new names and release a fix. |
