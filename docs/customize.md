# Customizing

The Lumen skin reads a Lumen token file: colours for light and dark mode, fonts, text size,
corner radius, spacing, logos, favicon, login background and custom CSS. The same token files
work in the other Lumen themes (the KeyHelp, Pterodactyl and Hydrodactyl themes and the browser
themes).

## The customizer

[`customizer/lumen-mail-customizer.html`](../customizer/lumen-mail-customizer.html) is one HTML
file that runs offline: download it and open it in a browser. Its Content-Security-Policy blocks
every network request. CI rebuilds it from `customizer/` and `tokens/` and fails when the
committed page is not current (`node customizer/build.mjs --out customizer/lumen-mail-customizer.html`).

What it edits:

- **Preset:** Luminare (default), Graphite (neutral, Roundcube's own logo), Aurora, High contrast.
- **Colours:** the 16 colour roles of each mode, with a picker and a hex field. Pairs below
  WCAG 2.2 AA are marked and listed with their ratio. The task rail and the login page use the
  dark palette in both modes, like the skin.
- **Typography:** body and code fonts (the whole skin), heading font and weight, text size
  (Elastic's 14px base scaled from 85 to 125 %).
- **Shape and spacing:** corner radius, spacing unit, density, the borders between the columns,
  the glow on the login page.
- **Branding:** product name (alt text of the logo), logos, favicon, login background, a font
  file for custom CSS. Files up to 4 MB go into the ZIP. Roundcube serves skin files only, so
  links to logos elsewhere are not used: upload them.
- **Custom CSS:** appended to the skin's stylesheet. Use the variables (`var(--lm-surface)`,
  `var(--lumen-accent)`); dark mode is `html.dark-mode`. Uploaded files are
  `url("/storage/lumen/<file>")`.

The preview is a mock of the webmail written for this page (the mail view and the login page,
light and dark); it uses the skin's role variables with the same formulas as the build, so colours
match the real skin closely, while Elastic's own details (icons, exact spacing) are not drawn.
**Export tokens** saves the token file, **Download customization ZIP** everything the server
needs, **Import** takes a token file from any Lumen theme or a ZIP made here.

Token values only other Lumen themes use stay in the file but change nothing here: the sidebar
style and widths, the content width, the active-item style and `mode.*` (Roundcube switches dark
mode per user).

## Install a customization

Copy the ZIP to a place the Roundcube owner can read (the command continues as that user when
started as root), then:

```bash
lumen-mail apply-custom /tmp/lumen-mail-example.zip --roundcube /var/www/roundcube
lumen-mail apply-custom /tmp/lumen-mail-example.zip --roundcube /var/www/roundcube --yes
```

The first command checks the ZIP and writes nothing. With `--yes` it moves the current
customization to `<state>/custom-backups/<time>/`, writes the new one to `<state>/custom/` and
runs `install`: build against the installed Elastic, verify, keep a backup of the current
`skins/lumen` and swap the new build in. If the install fails, the previous customization comes
back and `skins/lumen` stays as it was. The command prints the undo (`apply-custom <backup> --yes`
or `apply-custom --reset --yes`); `rollback` works for the skin as always.

The customization is part of the source digest: `check` reports a changed one, and `sync` (also
after a Roundcube update) builds with it.

### What the ZIP holds and what is checked

| File | Content |
|---|---|
| `lumen.tokens.json` | the token file |
| `lumen-custom.less` | the skin's `@lm-*` variables, imported right after `lumen-tokens.less` |
| `lumen-custom.css` | the `--lumen-*` variables, a few rules and the custom CSS, appended to `styles.css` |
| `branding.json` | logos for the task rail, login page and phones, favicon, browser colours |
| `custom/<file>` | your uploads, built into `skins/lumen/images/custom/` |

The build refuses any other file. The LESS file may only set `@lm-*` variables to colours,
`mix()` of two colours, pixel sizes or a font list (no `@import`, plugins, `data-uri()` or
JavaScript). Uploads must be images or fonts whose content matches their type; SVG files with
scripts, event handlers, `<use>`, animations, entities or outside references are refused. Every
`url()` must point at a file of the skin, as for any build.

## Compile a token file without the customizer

```bash
node --experimental-strip-types tokens/compile.mjs my.lumen.json --out /var/lib/lumen-mail/custom
```

Node.js 22.6 or newer, no packages. Put uploaded files into `custom/` inside that folder.

## How the tokens reach the skin

`tokens/core.ts` and the presets are copies of the Lumen token compiler of
[lumen-hydrodactyl-theme](https://github.com/luminare-dev/lumen-hydrodactyl-theme) (`shared.lock`,
checked by `scripts/check_shared.py`). `tokens/roundcube.ts` writes every role of
`src/less/lumen-tokens.less` from the 16 token roles, for example
`@lm-light-primary-tint: mix(<accent>, <surface>, 10%)`. LESS takes the last definition
everywhere, also inside Elastic's colour functions, so one file recolours Elastic and Lumen's own
layer. CI checks that the page embeds exactly this compiler and compiles the skin against the
pinned Roundcube with every preset.
