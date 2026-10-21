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
system skin.

**Fix:** copy the last build back (`cp -a <build> /path/to/roundcube/skins/lumen`) or set the
Interface skin to Elastic, then rebuild.

## Still stuck?

Search the issues, then ask in the organization's
[Discussions](https://github.com/orgs/luminare-dev/discussions). Never post secrets, keys, IP
addresses, hostnames or mailbox data; redact logs before you paste them.
