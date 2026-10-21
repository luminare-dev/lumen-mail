# Upgrading

Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0 a minor
release may contain breaking changes; they are listed under "BREAKING CHANGES" in the
[changelog](../CHANGELOG.md).

## After a Roundcube update

With the sync units enabled, nothing: the unit restores `skins/lumen` within a second of the
extraction and rebuilds it for the new release ([update safety](update-safety.md)). Check with
`lumen-mail status --roundcube <root>`. If the rebuild stops with exit code 3, the new Elastic
changed something Lumen relies on; the journal names it, the previous build stays active, and the
fix is a lumen-mail update.

Without the units: `lumen-mail install --roundcube <root>` (or `build` and `verify` by hand).

## After a lumen-mail update

1. Read the changelog entries between your version and the new one.
2. Update the checkout and the pinned compiler:

   ```bash
   cd /root/lumen-mail && git pull --ff-only
   npm ci --omit=dev --ignore-scripts --no-audit --no-fund
   ```

3. Replace the runtime (atomic; the old one is removed afterwards):

   ```bash
   PYTHONPATH=generator python3 -m lumen_mail install-runtime --prefix /opt/lumen-mail
   ```

4. Rebuild: either wait for the next timer run (the new lumen-mail version makes the stamp stale)
   or run `/opt/lumen-mail/bin/lumen-mail install --roundcube <root>` now.
5. If the units in `contrib/systemd/` changed, copy them again and run `systemctl daemon-reload`.

## Version notes

No release has needed manual steps yet.
