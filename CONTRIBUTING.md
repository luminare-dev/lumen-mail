# Contributing

Thank you for helping. This guide is the organization's
[contributing guide](https://github.com/luminare-dev/.github/blob/main/CONTRIBUTING.md) adapted
to lumen-mail; where they differ, this file wins.

## Before you start

- Questions and ideas go to
  [Discussions](https://github.com/orgs/luminare-dev/discussions), security problems to
  [SECURITY.md](SECURITY.md), never to a public issue.
- Search the open and closed issues first.
- Open an issue before a large pull request: a new feature, a change in behaviour, a new
  dependency, a change to the CLI, the stamp or the units, or more than about 100 changed lines.

## Rules specific to this project

- **No Roundcube or Elastic file, ever.** Not a template, not a LESS or CSS excerpt, not a script,
  not an image, not even "just this one mixin". Lumen addresses Elastic by the names of its
  variables, selectors and template files; the generator compiles against the Elastic installed
  where it runs. A change that needs a copied template is the wrong change: use a wrapper
  template (`templates.py` describes what a wrapper may contain) or a rule in `src/less/`.
- **Every build includes the command palette.** There is no option to leave it out; tests use the
  stub in `tests/fixtures/lumen-palette.js`.
- **Labels:** every text the palette shows comes from Roundcube. A new one needs the key in
  `palette/src/i18n.ts`, a `<roundcube:add_label>` in `skin/templates/includes/footer.html` and,
  for the skin's own labels, an entry in `skin/localization/en_US.inc` and `de_DE.inc`;
  `tests/test_palette_consistency.py` checks all four.
- **Colours:** a new text or UI colour pair goes into `src/less/contrast-pairs.json`; run
  `python3 scripts/contrast.py` to update `docs/contrast.md`. Every pair must pass WCAG 2.2 AA.
- **Size:** the palette bundle must stay under the budget in `scripts/check-palette.mjs`.
- **Right to left:** use logical properties (`inline-start`, `block-end`) in our styles.
- **Screenshots and fixtures** use example data only: `user@example.com`,
  `webmail.example.com`, invented names.

## Development setup and tests

[docs/development.md](docs/development.md) describes the tools, the layout and every command.
In short, CI runs:

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run typecheck && npm test && npm run test:js && npm run build
python3 -m unittest discover -s tests
python3 scripts/contrast.py --check
```

Run them before you push. A pull request is reviewed once CI is green.

## Commits, pull requests and the DCO

Commit messages and pull request titles follow
[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/): `feat`, `fix`,
`perf`, `security` and `revert` reach the changelog; `docs`, `refactor`, `test`, `style`,
`build`, `ci` and `chore` do not. A breaking change adds `!` after the type. Pull requests are
squash-merged, so the title becomes the commit message: lower-case imperative summary, no full
stop, at most 100 characters. Do not edit `CHANGELOG.md` by hand; release-please writes it.

Every commit is signed off (`git commit -s`), certifying the
[Developer Certificate of Origin 1.1](https://developercertificate.org/). Your contribution is
licensed under the repository's MIT licence; you keep your copyright. Only submit code you have
the right to license this way.

One topic per pull request, tests and documentation in the same pull request, and link the issue
it closes.

## Never post secrets or personal data

Issues, pull requests, logs, screenshots and fixtures are public. Never include passwords,
tokens, keys, `config.inc.php` contents, real mail addresses or folder names, IP addresses or
hostnames. If you posted a secret by accident, revoke or rotate it at once.

## Code of Conduct

Everyone who takes part follows the
[Code of Conduct](https://github.com/luminare-dev/.github/blob/main/CODE_OF_CONDUCT.md).
