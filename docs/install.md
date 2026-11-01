# Installation

There are two ways to install Lumen:

| | Build on the server (recommended) | Release package |
|---|---|---|
| What you get | `skins/lumen` compiled from the Elastic installed on this server: an exact match | `skins/lumen` compiled in CI from the official Roundcube release named in the file name |
| Needs | Node.js 22 (or 20.19 or later) and npm to build the command palette once and to compile; Python 3.10 or later | nothing besides Roundcube |
| Roundcube | any release whose Elastic passes the drift check | the same minor series as the package (1.7.x for `roundcube-1.7.3`) |
| After a Roundcube update | rebuilt automatically by the sync units | install the matching package by hand |

Lumen is tested with Roundcube 1.7.3 (as shipped by KeyHelp 26.1.1) and supported on the 1.7
series. The build's drift check stops with the exact name of anything Lumen relies on that is
missing.

## On a KeyHelp server

KeyHelp keeps Roundcube in `/home/keyhelp/www/roundcube` (owner `keyhelp:keyhelp`) and replaces
that whole folder when it updates Roundcube; the sync units put `skins/lumen` back
([update safety](update-safety.md)). Run everything below as root: lumen-mail prepares
`/var/lib/lumen-mail` and then continues as `keyhelp`, so the compile never runs as root
([running as root](cli.md#running-as-root)).

1. Get the sources, the locked packages and the command palette:

   ```bash
   git clone https://github.com/luminare-dev/lumen-mail.git /root/lumen-mail
   cd /root/lumen-mail
   npm ci --ignore-scripts --no-audit --no-fund
   npm run build:palette
   ```

   On a server with little free memory, use the `systemd-run` prefix of step 3. Without npm's
   development packages, take `lumen/lumen-palette.js` from the release package of the same
   version and pass `--palette <file>` to `install-runtime`.

2. Install the runtime (generator, sources, the palette bundle and the compiler only). The sync
   units run from this copy, never from the checkout, and never need Vite:

   ```bash
   PYTHONPATH=generator python3 -m lumen_mail install-runtime --prefix /opt/lumen-mail --dry-run
   PYTHONPATH=generator python3 -m lumen_mail install-runtime --prefix /opt/lumen-mail
   ```

3. Build, verify and install the skin (it runs as `keyhelp`, so everything it writes belongs to
   `keyhelp:keyhelp`, folders 755, files 644; root first creates the state folder
   `/var/lib/lumen-mail` and gives it to `keyhelp`):

   ```bash
   /opt/lumen-mail/bin/lumen-mail install --roundcube /home/keyhelp/www/roundcube --dry-run
   NODE_OPTIONS=--max-old-space-size=256 systemd-run --scope --quiet --collect \
     -p MemoryMax=300M -p MemorySwapMax=0 choom -n 1000 -- nice -n 19 \
     /opt/lumen-mail/bin/lumen-mail install --roundcube /home/keyhelp/www/roundcube
   ```

   The `systemd-run` line caps memory and priority for the short compile; plain
   `/opt/lumen-mail/bin/lumen-mail install --roundcube ...` works too. The command prints how to
   undo it and keeps that in `/var/lib/lumen-mail/ROLLBACK.txt`.

4. Install and start the units:

   ```bash
   install -m 644 contrib/systemd/lumen-mail-sync.service contrib/systemd/lumen-mail-sync.path \
     contrib/systemd/lumen-mail-sync.timer /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now lumen-mail-sync.path lumen-mail-sync.timer
   systemctl start lumen-mail-sync.service && systemctl status --no-pager lumen-mail-sync.service
   ```

5. Turn it on in KeyHelp: **Configuration → Webmail**, set **Interface skin** to **Lumen** and
   **Product name** to **Luminare Webmail**, then save. KeyHelp writes both into Roundcube's
   `config.inc.php`; lumen-mail never edits that file. If Lumen is not in the list, check
   `ls /home/keyhelp/www/roundcube/skins/` and the owner of `skins/lumen`.

   If the list still shows only Elastic, see [troubleshooting](troubleshooting.md#lumen-is-missing-from-the-skin-chooser).

KeyHelp is a registered trademark of Keyweb AG. This project is not affiliated with or endorsed
by Keyweb AG.

## Plain Roundcube

The same steps, with your paths and the owner of `<roundcube>/skins` (for example `www-data`).
Started as root, lumen-mail continues as that owner. If root owns your Roundcube files, add
`--owner root:root` (and `Environment=LUMEN_MAIL_OWNER=root:root` to the service below, which then
runs as root): commands that write refuse a tree that belongs to root otherwise.

```bash
git clone https://github.com/luminare-dev/lumen-mail.git && cd lumen-mail
npm ci --ignore-scripts --no-audit --no-fund && npm run build:palette
sudo PYTHONPATH=generator python3 -m lumen_mail install-runtime --prefix /opt/lumen-mail
sudo /opt/lumen-mail/bin/lumen-mail install --roundcube /var/www/roundcube
```

Select the skin:

- **For everybody:** `$config['skin'] = 'lumen';` in `config/config.inc.php`. Users who chose
  another skin in their preferences keep it.
- **For one user:** Settings → Preferences → User Interface → Interface skin → Lumen.
- If `skins_allowed` is set, add `lumen` to it.

The sync units are optional on a server where Roundcube updates do not remove `skins/lumen`; they
also rebuild the skin after an update. To use them, adapt the paths and the user (the service
must run as the owner of `<roundcube>/skins` and be able to write in the Roundcube root, where it
stages new builds in `.lumen-mail/`):

```bash
sed -e 's|/home/keyhelp/www/roundcube|/var/www/roundcube|g' \
    -e 's|^User=keyhelp$|User=www-data|' -e 's|^Group=keyhelp$|Group=www-data|' \
    contrib/systemd/lumen-mail-sync.service | sudo tee /etc/systemd/system/lumen-mail-sync.service >/dev/null
sed -e 's|/home/keyhelp/www/roundcube|/var/www/roundcube|g' contrib/systemd/lumen-mail-sync.path \
  | sudo tee /etc/systemd/system/lumen-mail-sync.path >/dev/null
sudo install -m 644 contrib/systemd/lumen-mail-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now lumen-mail-sync.path lumen-mail-sync.timer
```

If Roundcube lives outside `/home`, the service's `ProtectHome=tmpfs` can stay as it is.

## Release package

Each release has `lumen-<version>-roundcube-<roundcube version>.tar.gz` and `.zip`, built in CI
against the official Roundcube release in the name (its sha256 is pinned in
`scripts/package.py`). Both hold one folder, `lumen/`, with `LICENSE`, `NOTICE` and a `README.md`
that credits Elastic's authors.

```bash
sha256sum -c SHA256SUMS --ignore-missing
gh attestation verify lumen-<version>-roundcube-1.7.3.tar.gz --repo luminare-dev/lumen-mail
sudo tar -xzf lumen-<version>-roundcube-1.7.3.tar.gz -C /var/www/roundcube/skins
sudo chown -R www-data:www-data /var/www/roundcube/skins/lumen
```

Then select the skin as above. The package includes the command palette
(`lumen/lumen-palette.js`, with React's MIT licence in `lumen/THIRD_PARTY_NOTICES.md`). The
compiled CSS in the package is an adaptation of Roundcube's Elastic skin and is licensed under
CC BY-SA 3.0. For another release of the same series the
stamp names a different Elastic; `verify --allow-mismatch` accepts that. With a runtime installed,
`lumen-mail install --from <folder> --allow-mismatch` installs the extracted folder with backups
and a last good copy.

`python3 scripts/package.py release --out dist` builds the same files locally (it downloads the
pinned release and checks its sha256); `package.py build --roundcube <root>` builds against an
extracted Roundcube.

## Check that it works

```bash
/opt/lumen-mail/bin/lumen-mail check --roundcube /home/keyhelp/www/roundcube      # exit 0 = current
/opt/lumen-mail/bin/lumen-mail status --roundcube /home/keyhelp/www/roundcube
curl -s https://webmail.example.com/ | grep -o 'skins/lumen/styles/styles.min.css?s=[0-9]*'
```

Once Lumen is the system skin, the login page links `skins/lumen/styles/styles.min.css` (with
Roundcube's `?s=` cache-buster), shows the Luminare logo and the product name. After login, every
page loads `skins/lumen/lumen-palette.js`: press Ctrl+K (Cmd+K on a Mac) or choose **Jump to** in
the menu.

## Roll back

- **To the previous Lumen build:** `/opt/lumen-mail/bin/lumen-mail rollback --roundcube <root>`.
  It puts the newest backup back and holds it: sync keeps restoring it but does not rebuild until
  `lumen-mail resume` or the next `install`.
- **To Elastic:** set the Interface skin (or `$config['skin']`) back to `elastic`, then
  `lumen-mail uninstall --roundcube <root>` and
  `systemctl disable --now lumen-mail-sync.path lumen-mail-sync.timer`. `uninstall` refuses while
  `config.inc.php` still selects lumen (it reads only the `skin` setting and prints nothing else
  from the file); `--force` overrides it. The removed build stays in
  `/var/lib/lumen-mail/backups/`. Users who picked Lumen in their own preferences fall back to the
  system skin automatically.
- **Without lumen-mail:** `ROLLBACK.txt` in the state folder has the plain `mv`/`cp` commands.

## Building without installing

`build` and `verify` work on any folder, without root and without touching the Roundcube tree
(after `npm run build:palette`, or with `--palette <file>`):

```bash
PYTHONPATH=generator python3 -m lumen_mail build --roundcube /var/www/roundcube --out /tmp/lumen
PYTHONPATH=generator python3 -m lumen_mail verify /tmp/lumen --roundcube /var/www/roundcube
```

`build` stops with exit code 3 and a list of names if the installed Elastic lacks a file, marker
or variable Lumen relies on, and with exit code 4 if the LESS compile fails. Every command and
exit code is in [the command reference](cli.md).
