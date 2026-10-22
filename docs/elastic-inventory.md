# Elastic inventory

Our own notes from reading Roundcube 1.7.3's Elastic skin and the parts of Roundcube that load
skins (read-only, 2026-10-21). They list names only (files, LESS variables, selectors, template
objects) and what Lumen does with them; no Elastic code is reproduced. Elastic is licensed under
CC BY-SA 3.0 by Aleksander Machniak and The Roundcube Dev Team.

## How Roundcube loads a skin that extends another

| Behaviour | Where | Consequence for Lumen |
|---|---|---|
| `meta.json` `"extends"` builds a search list `skins/lumen`, `skins/elastic`; config keys of the child apply after the parent's; `meta` tags merge by name; `"localization": true` loads `localization/<lang>.inc` (falls back to `en_US`) | `rcmail_output_html::load_skin` | Lumen ships only what differs. Labels live in `localization/`, keys prefixed `lumen.` |
| A template is taken from the first skin in the list that has it | `rcmail_output_html::parse` | Elastic's templates are used for every page; Lumen has one wrapper |
| `<roundcube:include file="…" skinpath="skins/elastic" />` puts the given skin first for this one lookup | include handler in `xml_command` | Lumen's `templates/includes/footer.html` includes Elastic's file of the same name. Without `skinpath` it would include itself and recurse |
| Asset paths in a template (`src`, `data-src-*`, `<link href>`) are resolved with the skin of that template **first**, then the search list | `file_callback`, `get_skin_file` | From Elastic's templates, any file that exists in Elastic wins: `images/logo.svg`, `images/favicon.ico`. Lumen's stylesheet wins only because Elastic ships `styles/styles.min.css` without `styles/styles.css`; Lumen ships both, and the drift check fails if Elastic adds a `styles.css` |
| A `.min.css`/`.min.js` next to the requested file is preferred and gets `?s=<mtime>` | `file_mod` | Template assets are cache-busted by Roundcube; `url()` inside CSS is not, so the build adds `?v=<sha256 prefix>` |
| The editor stylesheet is looked up only in the first skin (`skin_path . editor_css_location`), message frames search the list | `rcmail_action::html_editor_init`, `rcmail_html_page::write` | Lumen must ship `styles/embed.css` / `embed.min.css` |
| The empty content frame is `blankpage_url` (`/watermark.html`), resolved through the list | `rcmail_output_html::init`, `write` | Lumen ships its own `watermark.html` (Elastic's shows the Roundcube logo) |
| The skin chooser shows `skins/<skin>/thumbnail.png` at 64×64 and `meta.json` name, author (`url` makes it a link) and licence (`license-url`) | `rcmail_action_settings_index` | `thumbnail.png` is our own miniature |
| `public_html/static.php` serves skin files only for types in `SUPPORTED_TYPES` (no `ttf`; `json` yes), never `templates/`, `README*`, `meta.json` | `static.php` | Font as WOFF; stamp named `lumen-build.stamp` |
| A missing user-preference skin falls back to the system skin; a missing system skin breaks every page | `set_skin`, `check_skin` | The restore after a KeyHelp update must be fast (sync, task 2) |
| Plugin skin folders fall back through the extended skins | `rcube_plugin::local_skin_path`, `jqueryui` | Plugins keep their Elastic styles |

## Templates

| Template | What matters | Lumen |
|---|---|---|
| `includes/layout.html` | `<head>`: `meta` and `links` objects, Bootstrap's CSS from `deps/`, `/styles/styles.css` (or `print.css` for `action=print`), an inline script that adds `dark-mode` to `<html>` from the `colorMode` cookie or `prefers-color-scheme`; opens `<body class="task-… action-…">` and `#layout` | not wrapped; relies on the `styles.css` lookup above. Lumen ships no `print.css`, so print pages get Elastic's `print.min.css`, which holds only print layout rules, on top of Lumen's stylesheet |
| `includes/footer.html` | closes `#layout` (non-framed pages), `messagestack` object, Bootstrap bundle and `ui.js` script lines, `</body>`. Roundcube inserts its own footer scripts (`rcmail.init()` on DOM ready) before the trailing script lines | wrapped: our scripts go before Elastic's footer, i.e. as the last children of `#layout`, so `lumen.js` runs before `ui.js` |
| `includes/menu.html` | `#layout-menu` with `.popover-header` (logo object `src="/images/logo.svg" id="logo"`, close button) and `#taskmenu` (`.action-buttons` with compose, `mail`, `contacts`, `taskbar` container, `settings`, `.special-buttons` with `theme`, `about`, `logout`) | styled (Night rail); logo swapped by `lumen.js`; `lumen-palette.js` adds its **Jump to** link as the first item of `.special-buttons` |
| `login.html` | `#layout-content.no-navbar`, logo object, `#login-form.propform` with the `loginform` object, `#login-footer` | branded hero and card in `lumen.less`; logo swapped |
| `mail.html` | `#layout-sidebar` (`#folderlist-content` > `ul.treelist.listing.folderlist`), `#layout-list` (`#messagelist-header.header`, `.searchbar`, `#messagelist-content` > `table.messagelist`), `#layout-content` (toolbar header, `.iframe-wrapper` with the content frame) | colours by variables; row hover, unread weight, rounded sidebar selection |
| `settings.html` | `#layout-sidebar` with `#settings-menu` (from `includes/settings-menu.html`), `#layout-list` with `#sections-table`, content frame | same list rules |
| `error.html`, `about.html`, print templates | error pages set `env:server_error`; print logo only through `skin_logo[print]` | palette not loaded on login, error and print pages |
| `watermark.html`, `thumbnail.png` | blank frame with the Roundcube logo; 64×64 preview | replaced by our own files |

Elastic's `ui.js` also matters: it turns the login table into Bootstrap input groups (icons,
placeholders, `btn-lg` submit), toggles `html.dark-mode` (and the class in frames) from the theme
button, the cookie and the colour-scheme media query, and swaps `#logo` for the types in
`rcmail.env.additional_logos` (`small` and `small-dark` on phones, `dark` in dark mode) on start,
on resize and on colour-mode changes. It sets `layout-large|normal|small|phone` and `touch` on
`<html>`.

## LESS sources

| File | Contents (names only) | Lumen |
|---|---|---|
| all LESS files | every `url()` is written relative to `styles/` (also in `styles/widgets/`, for example the sign-in button icons), and `data-uri()` reads files relative to the entry; Elastic's build does not rewrite urls | the compile runs with url rewriting off; each url is then resolved in `skins/lumen` first, else in `skins/elastic` (`../../elastic/…`); Elastic's images are linked into the mirror tree during the compile so `data-uri()` embeds them |
| `variables.less` | breakpoints `@screen-width-large/medium/small/xs/mini`, `@page-font-size` (14px), layout sizes (`@layout-menu-width` 78px, `@layout-header-height` 58px, …), `@scrollbar-width`, data-URI icons; ends with an optional `_variables` import | sets `@layout-menu-width` to 96px; reads the breakpoints |
| `colors.less` | base colours (`@color-main`, `@color-black`, `@color-font`, `@color-link`, `@color-error/success/warning`, `@color-black-shade-*`), layout, task menu, toolbar, menu, list, message, popover, dialog, form, button, quota, quote, date picker, editor, image tools and scrollbar groups, and the `@color-dark-*` family | sets almost every colour variable in `lumen-variables.less` (light and dark), from tokens |
| `mixins.less` | `.font-icon-class`, `.font-family` (Roboto), `.overflow-ellipsis`, focus helper | `.font-family()` is extended with Sora |
| `global.less` | `@font-face` for the icon font and Roboto, base font, link colours, scrollbar colours | Sora `@font-face` added; Roboto is no longer referenced, so never downloaded |
| `layout.less` | `#layout` flex columns, `.header`/`.footer` bars, `#layout-sidebar/list/content`, `#layout-menu .popover-header` logo sizes, breakpoint rules, `hidden-*` helpers | headers keep their size; sidebar header transparent; a long `.header-title` takes a second line |
| `widgets/menu.less` | `.menu`, `.toolbar` (links capped at `max-width: 6rem`, which also matches the rail, `#taskmenu.menu.toolbar`), popover menus, menu icons, `.searchbar`, `#taskmenu` (phone, medium, large), `.pagenav` | rail colours, active indicator, rail labels 12px, rail links as wide as the rail, header toolbar buttons up to 11rem, phone footer buttons as wide as their label, the list count on up to two lines, rounded toolbar buttons, search field |
| `widgets/lists.less` | `.listing` rows, focus indicator (`border-left`), `ul.treelist`, `.folderlist` unread badge, `.messagelist` columns and flags, attachments | sidebar list pills, row hover, unread weight, long entries of the folder, address book and settings lists wrap instead of an ellipsis |
| `widgets/forms.less`, `buttons.less` | Bootstrap overrides: `.form-control` focus, checkboxes and switches, `.btn-*` colours with focus shadows | radius 10px, visible focus, primary hover |
| `widgets/dialogs.less`, `jqueryui.less` | `.popover` shadow, phone popovers, `.ui-dialog` (square, full screen at ≤480px), `.ui-widget`, `.ui-menu` | rounded popovers and dialogs above 480px; menus up to 28rem wide (Bootstrap: 276px); in the small and phone layouts long menu entries take a second line |
| `widgets/messages.less` | `.ui.alert` boxes, `#messagestack` toasts (full width at ≤480px) | rounded toasts above 480px |
| `dark.less` | everything under `html.dark-mode`, from the `@color-dark-*` variables, plus a few light ones: `@color-main` (compose button, editor dialog tab, date picker highlight), `@color-success` (active toolbar toggle), `@color-list-flagged` | Lumen repeats those selectors with dark tokens (below) |
| `embed.less` | editor and message frame content (`.mce-content-body`, `.rcmail-inline-message`) | `lumen-embed.less`: Sora, quote border, rounded inline message |
| `styles.less` | imports the above, login, contacts, mail view, settings rules, `@import "dark"` | compiled as is, with Lumen's files after it |

## What Lumen overrides and why

| Area | How | Why |
|---|---|---|
| Colours, light and dark | Elastic variables in `lumen-variables.less`, values from `lumen-tokens.less` | the variables reach every Elastic rule, including colour functions; fewer selector overrides |
| Font | `.font-family()` mixin, `@font-face` | Sora is the brand typeface; one place covers body, controls, popovers and the editor |
| Task menu width | `@layout-menu-width: 96px`; `#taskmenu a { max-width: none }` and no padding on `span.inner` above 1024px | measured in Chromium at 12px: "Dunkler Modus" is 91px, "Einstellungen" 82px, plus 2.4px of padding; Elastic's 78px truncates them. Elastic's `.menu.toolbar a { max-width: 6rem }` also matches the rail's links, so without the reset they stayed 84px wide in the 96px rail (off centre, labels still cut) |
| Long labels | rail links as wide as the rail; header toolbar buttons up to `@lm-toolbar-button-max` (11rem), the content toolbar as flex items that share the header (long labels grow from Elastic's 6rem as far as there is room, with less side padding between 769 and 959px); phone footer buttons as wide as their label; menus up to `@lm-popover-max` (28rem); column header titles, the list footer's count, the menu entries of the small and phone layouts and long entries of the folder, address book and settings lists wrap instead of ending in an ellipsis, with one-line rows and titles exactly where Elastic puts them | Elastic cuts long labels with an ellipsis, and Sora is wider than Roboto; labels that fit keep Elastic's sizes ([ADR 0011](adr/0011-long-labels-get-room.md), checked by `scripts/screenshots/label-fit.mjs`) |
| Task rail | `#layout-menu #taskmenu …` rules with `--lm-rail-*` | Night in both modes, a Lumen indicator bar, Mint focus ring |
| Command palette trigger | `.menu a.lumen-palette:before { content: @fa-var-search }` | the link that `lumen-palette.js` adds to `#taskmenu .special-buttons` takes Elastic's menu layout on every screen size; this rule gives it an icon from Elastic's icon font (the drift check covers `@fa-var-search`) |
| Focus | `:focus-visible` rings, also on `.menu a`, list items and the search bar | Elastic removes outlines in several places (`.menu a:focus`, list focus, search input) |
| Login | hero gradient on `body.task-login`, card on `#login-form` | branded entry page, logo on Night in both modes |
| Dark mode fixes | same selectors as Elastic's dark rules for: plain links, `.btn-link`, primary button text, floating action button, editor dialog, date picker highlight, active toolbar toggle, search bar toggle, flagged rows, tabs | Elastic uses a light-mode variable there, which fails contrast on Night with Lumen's palette |
| Logo and favicon | `lumen.js`, `meta.json` `config.favicon` | see ADR 0006 |
| Reduced motion | transitions off under `prefers-reduced-motion: reduce` | spinners keep running (they show progress) |
| RTL | logical properties in `lumen.less`; `#taskmenu .special-buttons` gets `inset-inline-start: 0; inset-inline-end: auto` | Roundcube does not set `dir="rtl"` for Elastic; our rules hold if a page or the gallery does. Elastic pins the menu's bottom block with a physical `left: 0`, which put it on the far side of a forced-RTL page; the logical insets keep it under the rail |
