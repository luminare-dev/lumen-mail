# Upgrading

Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0 a minor
release may contain breaking changes; they are listed under "BREAKING CHANGES" in the
[changelog](../CHANGELOG.md).

## After a Roundcube update

Rebuild the skin: `verify` reports `built for Roundcube X, installed is Y` or `built from different
Elastic sources` when the installed skin no longer matches. If `build` stops with exit code 3, the
new Elastic changed something Lumen relies on; the message names it. Keep the old skin folder in
place (it still works with the new Elastic in most cases) and open an issue with the message.

## After a lumen-mail update

1. Read the changelog entries between your version and the new one.
2. `npm ci --omit=dev --ignore-scripts` (the compiler pins may have changed).
3. Build into a new folder, run `verify`, then replace `skins/lumen` (see
   [Installation](install.md)).

## Version notes

No release has needed manual steps yet.
