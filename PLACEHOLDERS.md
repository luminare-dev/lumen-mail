# Placeholders

This repository was created from
[luminare-dev/oss-template](https://github.com/luminare-dev/oss-template). Every placeholder of the
template is filled; CI fails if one comes back. The values used:

| Placeholder | Value |
|---|---|
| `{{SLUG}}` | `lumen-mail` (project page `https://luminare.tech/open-source/lumen-mail/`) |
| `{{PROJECT_TITLE}}` | `lumen-mail` (the skin itself is called "Lumen") |
| `{{ONE_LINE_PURPOSE}}` | A modern Luminare skin for Roundcube Webmail (README, first paragraph) |
| `{{PROBLEM_STATEMENT}}` | README, section "Why" |
| `{{QUICKSTART_COMMANDS}}` | README, section "Quickstart", and `docs/install.md` |
| `{{TARGET_SYSTEM}}` | the README diagram shows the Roundcube skins folder |
| `{{COMPONENT}}`, `{{TESTED_VERSION}}`, `{{SUPPORTED_RANGE}}` | README, "Supported versions"; `docs/install.md`, "Requirements" |
| `{{LIMITATION}}` | README, "Limitations" |
| `{{RESULT}}`, `{{VALUE}}`, `{{METHOD}}` | README, "Results" |
| `{{SPDX_ID}}` | `MIT` |
| `{{AUTHOR_NAME}}` | `Paul Pasaurek` (LICENSE, NOTICE, the inactive personal byline) |
| `{{YEAR}}` | `2026` |
| `{{VERSION}}` | no release with manual upgrade steps yet; `docs/upgrade.md` says so |

## Values to check, not placeholders

| Value | Where | Status |
|---|---|---|
| `ci / lint-test`, `node`, `package`, `secrets / gitleaks`, `pr / pr-title`, `DCO` | repository ruleset (required checks) | set when the repository is created (PUBLISHING.md, A7) |
| `luminare-dev` | README badges and links | the organization |
| `docs/brand/` | header SVGs and social preview | generated for `lumen-mail` by brand-repos (studio variant) |
| `release-please-config.json` -> `initial-version` | first release | `0.1.0` |
| `version.txt`, `package.json`, `package-lock.json` | release-please | start at `0.0.0`; release-please updates all three; the generator reads `version.txt` |
| `ROUNDCUBE_VERSION`, `ROUNDCUBE_SHA256` | `.github/workflows/ci.yml` | the Roundcube release CI compiles against; bump by hand with its sha256 |
