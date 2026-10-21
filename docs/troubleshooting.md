# Troubleshooting

## `error: the installed Elastic skin changed in a way Lumen does not support yet` (exit code 3)

**Cause:** a Roundcube update renamed or removed an Elastic file, template marker or LESS variable
that Lumen uses. Each line under the message names one, for example
`Elastic no longer defines @color-taskmenu-background, which src/less/lumen-variables.less:44 sets`.

**Fix:** keep the current `skins/lumen` (it does not depend on the change until you rebuild),
update lumen-mail if a newer release supports the new Roundcube, or open an issue with the
message.

## `error: LESS compilation failed` (exit code 4)

**Cause:** the compiler could not process the sources; the line after the message names the file
and line. `cannot load the compiler` means `node_modules` is missing.

**Fix:**

```bash
npm ci --omit=dev --ignore-scripts
```

## `error: the command palette bundle .../lumen-palette.js is missing`

**Cause:** every build includes the command palette, and the sources (or the runtime) have no
built bundle.

**Fix:** in the checkout, `npm ci --ignore-scripts --no-audit --no-fund && npm run build:palette`,
then `install-runtime` again. Or use the `lumen/lumen-palette.js` of the release package of the
same version: `--palette <file>`. A sync run keeps the active build until the bundle is back.

## Ctrl+K does nothing

- The palette is not on the login page, on print and error pages, in frames and in the external
  compose window. Use it on a page after login, or choose **Jump to** in the menu.
- Inside a text area, the HTML editor and other editable text, Ctrl+K belongs to the editor (in
  the HTML editor it inserts a link). Click outside the editor first.
- On a Mac the shortcut is Cmd+K.
- `skins/lumen/lumen-palette.js` must load: the browser's developer tools show the request. A
  user with another skin in their preferences does not get it.

## The page looks like plain Elastic

**Cause:** Lumen is not the active skin, `devel_mode` is on, or the browser still has the old
stylesheet. Elastic would also win if a future Elastic shipped `styles/styles.css`; `build` checks
for that.

**Fix:** check `$config['skin']`, `devel_mode` and the user's Interface skin preference, then
reload without the cache. The page source must link `skins/lumen/styles/styles.min.css`.

## The logo area is empty

**Cause:** the Luminare logo is set by `lumen.js` before Elastic's UI starts; a script blocker or an
error before it leaves the area empty (the Roundcube logo is hidden on purpose).

**Fix:** check the browser console; `skins/lumen/lumen.js` must load with status 200.

## Lumen is missing from the skin chooser

**Cause:** `skins_allowed` is set without `lumen`, or `skins/lumen` is not readable by the web
server.

**Fix:** add `lumen` to `skins_allowed`, or fix the owner and modes of `skins/lumen`.

## Webmail shows an error page after a Roundcube update on KeyHelp

**Cause:** KeyHelp replaced the Roundcube folder, which removed `skins/lumen`, while Lumen is the
system skin, and the sync units did not put it back.

**Fix:** `systemctl start lumen-mail-sync.service` restores the last good build; then check why
the units did not run (`systemctl status lumen-mail-sync.path lumen-mail-sync.timer`). The
[runbook](runbook.md) has the details.

## `another lumen-mail run holds .../lock` (exit code 75)

**Cause:** an install, sync, rollback or uninstall is running, for example the unit after a
Roundcube update.

**Fix:** wait and run the command again; `--lock-timeout 300` waits up to five minutes.

## `uninstall` says `the configured system skin is lumen` (exit code 5)

**Cause:** `config.inc.php` still selects Lumen; removing the folder would break every page.

**Fix:** select Elastic first (KeyHelp: Configuration → Webmail → Interface skin), then run
`uninstall` again. If the setting is written in a form lumen-mail cannot read (an expression or an
include), check it yourself and pass `--force`.

## `check` exits 10 right after `install`

**Cause:** the runtime that `check` uses differs from the one that built the skin (for example the
checkout instead of `/opt/lumen-mail`), so the source digest in the stamp does not match.

**Fix:** run `install`, `check` and the unit from the same runtime: `/opt/lumen-mail/bin/lumen-mail`.

## The unit fails with status 226/NAMESPACE

**Cause:** a path in `BindPaths=` does not exist (for example a Roundcube root that was moved), so
systemd cannot set up the sandbox.

**Fix:** correct the paths in the service and the path unit, then `systemctl daemon-reload`.

## Still stuck?

Search the issues, then ask in the organization's
[Discussions](https://github.com/orgs/luminare-dev/discussions). Never post secrets, keys, IP
addresses, hostnames or mailbox data; redact logs before you paste them.
