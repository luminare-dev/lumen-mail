# Security policy

This is the security policy of lumen-mail. It follows the
[luminare-dev organization policy](https://github.com/luminare-dev/.github/blob/main/SECURITY.md)
and adds what is specific to this project: a Roundcube skin with a command palette that runs in
every webmail user's browser, and a generator whose sync unit runs on the mail server.

## Supported versions

Security fixes go into the **latest minor release**. Older releases do not get fixes; upgrade
first and check whether the problem still exists. Before 1.0.0 only the latest 0.x minor release
is supported. The unreleased `main` branch is fixed before the next release.

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a security problem.**

1. **Preferred: GitHub private vulnerability reporting.** Open
   <https://github.com/luminare-dev/lumen-mail/security/advisories/new>. Only the maintainers
   can see the report.
2. **Fallback: email <security@luminare.tech>** with "lumen-mail" in the subject line.

Please include the version, tag or commit, the Roundcube version, what an attacker could do,
and the smallest steps to reproduce it. Replace real mail addresses, folder names, hostnames, IP
addresses and secrets with placeholders such as `user@example.com` and `webmail.example.com`.

Acknowledgement is best effort within 14 days. The maintainers prepare a fix privately, agree on
a disclosure date with you (typically 90 days or less after the report) and publish a GitHub
security advisory with the fixed release; you are credited unless you prefer not to be.

## In scope

- **The command palette** (`palette/`, `skins/lumen/lumen-palette.js`): script injection through
  folder names, labels or other page content, actions that run without the user choosing them,
  keyboard handling that leaks keys out of editors, anything that sends data over the network or
  stores it (the palette must do neither).
- **The skin's own files**: the wrapper template (`templates/includes/footer.html`), `lumen.js`
  and the compiled stylesheets' references.
- **The generator and the sync units**: anything that lets a local user or a crafted Roundcube
  tree make `install`, `sync` or `uninstall` write outside `skins/lumen`, the staging folder and
  the state folder; symlink or race problems during the atomic swap; output that reveals any part
  of `config.inc.php` other than the `skin` setting; the units' sandboxing in `contrib/systemd/`.
- **The build and release chain**: install scripts, unpinned downloads or actions, a release
  package that differs from what CI built.

## Out of scope

- Vulnerabilities in Roundcube or its Elastic skin: report them to the
  [Roundcube project](https://github.com/roundcube/roundcubemail/security). Vulnerabilities in
  KeyHelp: report them to Keyweb AG. Not affiliated with or endorsed by the Roundcube project or
  by Keyweb AG; KeyHelp is a registered trademark of Keyweb AG.
- Findings that need an already compromised server, a compromised webmail session or root
  access, without showing a weakness in lumen-mail itself.
- Automated scanner output without a demonstrated impact.

## A secret was committed by mistake

If you find a credential, token or key in this repository or its history, report it privately
in the same way. Do not copy it into a public place.
