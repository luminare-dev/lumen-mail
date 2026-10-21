# 0009. A release package built against a pinned official Roundcube release

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Building on the server gives an exact match with the installed Elastic but needs Node. Many
Roundcube installs have no Node, and their admins expect a skin they can extract into `skins/`.
The repository must not contain Elastic files, so a package can only exist as a build output, and
its compiled CSS is an adaptation of Elastic under CC BY-SA 3.0.

## Considered options

1. No package: building on the server is the only way.
2. Build in CI against the Elastic of an official Roundcube release, downloaded and checked
   against a pinned sha256, and attach the result to the GitHub release.
3. Commit compiled CSS to the repository (would put an adaptation of Elastic into the repository).

## Decision

Option 2. `scripts/package.py` holds the pin (Roundcube 1.7.3, the sha256 of
`roundcubemail-1.7.3.tar.gz`), downloads and checks the archive, extracts it with tarfile's `data`
filter, builds and verifies the skin and writes `lumen-<version>-roundcube-1.7.3.tar.gz` and
`.zip` (one `lumen/` folder with `LICENSE`, `NOTICE` and the credits in `README.md`). The archives
are reproducible: sorted entries, owner 0:0, modes 755/644, dates from `SOURCE_DATE_EPOCH` (the
last commit), gzip without name and time. CI keeps the package as an artifact on every run; the
release workflow attaches it, lists it in `SHA256SUMS` and attests it with the source archive.

## Consequences

- Good: installs without Node get Lumen with one `tar -xzf`; the same script builds the package
  locally.
- Good: the package carries its licence terms inside the folder, so redistribution keeps them.
- Bad: it matches one Elastic exactly; for other releases of the series the stamp differs
  (`verify --allow-mismatch`), and a major Roundcube change needs a new pin and release.
