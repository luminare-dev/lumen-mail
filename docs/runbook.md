# Runbook

## Failure: webmail shows an error page after a Roundcube update

| | |
|---|---|
| **Meaning** | `skins/lumen` is missing or incomplete while Lumen is the system skin. On KeyHelp this happens when KeyHelp replaces the Roundcube folder during an update. |
| **Impact** | Every webmail page fails to render for every user until the folder is back. |
| **Diagnosis** | `ls /path/to/roundcube/skins/`; `PYTHONPATH=generator python3 -m lumen_mail verify /path/to/roundcube/skins/lumen --roundcube /path/to/roundcube`. |
| **Mitigation** | Copy the last good build back into `skins/lumen`, or switch the system skin to `elastic`. |
| **Fix** | Rebuild against the new Elastic (see [Installation](install.md)) and run `verify`. |

## Failure: the build stops with exit code 3 (Elastic drift)

| | |
|---|---|
| **Meaning** | The installed Elastic changed something Lumen relies on (named in the message). |
| **Impact** | No new build; the installed `skins/lumen` keeps working with the old compiled CSS. |
| **Diagnosis** | The message lists each missing file, marker or variable with the Lumen file and line that uses it. |
| **Mitigation** | Keep the current skin; `verify` will report the version mismatch until a rebuild succeeds. |
| **Fix** | Update lumen-mail, or adapt `src/less/` to the new names and release a fix. |
