# Installation

Lumen is built on the server that runs Roundcube, from the Elastic skin installed there. The
commands below are written for Ubuntu 24.04 with Roundcube 1.7.3, Node 22 and Python 3.12.

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Roundcube Webmail | 1.7.3 tested | with its Elastic skin and Elastic's LESS sources (`skins/elastic/styles/*.less`, part of every release archive) |
| Node.js | 20 or later | build only: runs the pinned `less` and `clean-css` packages |
| Python | 3.12 (3.10 or later) | standard library only |

## Build and install

```bash
git clone https://github.com/luminare-dev/lumen-mail.git && cd lumen-mail
npm ci --omit=dev --ignore-scripts
PYTHONPATH=generator python3 -m lumen_mail build --roundcube /var/www/roundcube --out /tmp/lumen --no-palette
PYTHONPATH=generator python3 -m lumen_mail verify /tmp/lumen --roundcube /var/www/roundcube
sudo cp -a /tmp/lumen /var/www/roundcube/skins/lumen
```

- `build` reads the Roundcube tree only. It writes the skin to `--out` (a new or empty folder) and
  a temporary mirror tree next to it, which it removes again. It stops with exit code 3 and a list
  of names if the installed Elastic lacks a file, marker or variable Lumen relies on, and with
  exit code 4 if the LESS compile fails.
- `verify` checks the folder against the Roundcube it will run in; it exits 1 and prints one
  `FAIL` line per problem. Run it again on `skins/lumen` after copying.
- Give the copy the owner and modes of the rest of the Roundcube tree (for example
  `sudo chown -R www-data:www-data /var/www/roundcube/skins/lumen`, folders 755, files 644).
- `--no-palette` builds without the command palette bundle.

## Select the skin

- **For everybody:** `$config['skin'] = 'lumen';` in `config/config.inc.php`. Users who chose
  another skin in their preferences keep it.
- **For one user:** Settings → Preferences → User Interface → Interface skin → Lumen.
- **On KeyHelp:** Configuration → Webmail → Interface skin, and the product name in the same form
  (KeyHelp writes Roundcube's `config.inc.php` from these fields).

If `skins_allowed` is set in the Roundcube configuration, add `lumen` to it.

## Building on a small server

The compile runs Node for a short time. On a busy host, cap its memory and priority:

```bash
NODE_OPTIONS=--max-old-space-size=320 systemd-run --scope --quiet --collect \
  -p MemoryMax=450M -p MemorySwapMax=0 nice -n 19 \
  env PYTHONPATH=generator python3 -m lumen_mail build --roundcube /var/www/roundcube --out /tmp/lumen --no-palette
```

## Verify the release download

Every release has a `SHA256SUMS` file and a build provenance attestation:

```bash
sha256sum -c SHA256SUMS
gh attestation verify <archive>.tar.gz --repo luminare-dev/lumen-mail
```

## Check that it works

```bash
curl -s https://webmail.example.com/ | grep -o 'skins/lumen/styles/styles.min.css?s=[0-9]*'
```

The login page links `skins/lumen/styles/styles.min.css` (with Roundcube's `?s=` cache-buster)
once Lumen is the system skin.

## Uninstall

1. Select another skin first: set `$config['skin']` (or KeyHelp's Interface skin) back to
   `elastic`. While Lumen is the system skin, removing its folder breaks every page.
2. Move the folder away: `sudo mv /var/www/roundcube/skins/lumen /root/lumen-skin-backup`.

Users who picked Lumen in their own preferences fall back to the system skin automatically.

## On KeyHelp

KeyHelp replaces the whole Roundcube folder when it updates Roundcube, which also removes
`skins/lumen`. Build and copy the skin again after such an update; while Lumen is the system skin,
webmail shows an error page until the folder is back. KeyHelp is a registered trademark of Keyweb
AG; this project is not affiliated with or endorsed by Keyweb AG.
