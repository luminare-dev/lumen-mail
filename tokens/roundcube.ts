// Lumen tokens for Roundcube: what a token file compiles to for the Lumen skin.
//
// core.ts is a byte-for-byte copy of the Hydrodactyl theme's compiler (shared.lock). Elastic runs
// its colours through LESS functions at compile time, so the main output here is LESS:
// lumen-custom.less redefines the skin's @lm-* variables (src/less/lumen-tokens.less) from the 16
// colour roles, and the server-side build imports it right after lumen-tokens.less. A small CSS
// override (the --lumen-* variables, a few rules and the custom CSS) is appended to the compiled
// stylesheet. The customizer page runs this same code (customizer/build.mjs embeds it) and shows
// the role mapping with color-mix() in its mock, so its preview follows the same formulas.

import { type ColorKey, compile, fontStack, sanitizeCustomCss, type ThemeMode, type Tokens } from './core.ts';

/** A colour: a role of the mode being written, a role of a fixed mode, or a mix of two roles. */
type Ref = ColorKey | `dark:${ColorKey}` | `light:${ColorKey}`;
export type Expr = Ref | ['mix', Ref, Ref, number];

/** Every role of lumen-tokens.less (@lm-roles), from the token roles of one mode. */
export function roleExprs(mode: ThemeMode): [string, Expr][] {
    const d = mode === 'dark';
    const tint = d ? 14 : 10;
    const out: [string, Expr][] = [
        ['bg', 'canvas'],
        ['surface', 'surface'],
        ['surface-raised', ['mix', 'surfaceRaised', 'surface', 50]],
        ['surface-sunken', 'surfaceSunken'],
        ['surface-hover', 'surfaceRaised'],
        ['border', 'border'],
        ['border-subtle', ['mix', 'border', 'surfaceSunken', 50]],
        ['border-control', ['mix', 'textMuted', 'border', 70]],
        ['text', 'text'],
        ['text-strong', 'text'],
        ['text-2', ['mix', 'text', 'textMuted', 45]],
        ['text-muted', 'textMuted'],
        ['link', 'accentText'],
        ['link-hover', ['mix', 'accentText', 'text', 75]],
        ['primary', 'accent'],
        ['primary-hover', ['mix', 'accent', 'accentSecondary', 60]],
        ['primary-active', 'accentSecondary'],
        ['on-primary', 'accentContrast'],
        ['primary-tint', ['mix', 'accent', 'surface', tint]],
        ['on-primary-tint', 'accentText'],
        ['secondary', d ? ['mix', 'textMuted', 'surface', 35] : ['mix', 'text', 'textMuted', 45]],
        ['on-secondary', d ? 'text' : 'surface'],
        ['focus', 'focus'],
    ];
    for (const s of ['success', 'warning', 'danger', 'info'] as const) {
        out.push(
            [s, s],
            [`on-${s}`, 'surface'],
            [`${s}-tint`, ['mix', s, 'surface', tint]],
            [`${s}-text`, ['mix', s, 'text', 80]],
        );
    }
    out.push(
        ['highlight', ['mix', 'accent', 'surface', d ? 20 : 16]],
        ['scrollbar', ['mix', 'textMuted', 'border', 70]],
        // The task rail and the login page are Night in both modes: the dark palette.
        ['rail', 'dark:surfaceSunken'],
        ['rail-text', 'dark:textMuted'],
        ['rail-text-active', 'dark:text'],
        ['rail-hover', ['mix', 'dark:surfaceRaised', 'dark:surfaceSunken', 60]],
        ['rail-active', ['mix', 'light:accent', 'dark:surfaceSunken', 30]],
        ['rail-accent', 'dark:accent'],
        ['rail-danger', 'dark:danger'],
        ['rail-focus', 'dark:focus'],
        ['toast', d ? 'dark:surfaceRaised' : 'dark:surfaceSunken'],
        ['on-toast', 'dark:text'],
        ['toast-info', d ? ['mix', 'light:info', 'dark:canvas', 75] : 'light:info'],
        ['toast-success', d ? ['mix', 'light:success', 'dark:canvas', 75] : 'light:success'],
        ['toast-warning', d ? ['mix', 'light:warning', 'dark:canvas', 75] : 'light:warning'],
        ['toast-danger', d ? ['mix', 'light:danger', 'dark:canvas', 75] : 'light:danger'],
        ['on-toast-status', d ? 'dark:text' : 'light:surface'],
    );
    return out;
}

/** Brand variables the skin also reads directly (lumen-variables.less, lumen.less). */
export const BRAND_EXPRS: [string, Expr][] = [
    ['royal', 'light:accent'],
    ['abyss', ['mix', 'light:accent', 'light:text', 70]],
    ['night', 'dark:surfaceSunken'],
    ['lumen', 'dark:accent'],
    ['white', 'light:surface'],
    ['mint', 'dark:focus'],
    ['login-end', ['mix', 'dark:surface', 'dark:canvas', 50]],
];

function hex(tokens: Tokens, mode: ThemeMode, ref: Ref): string {
    const at = ref.indexOf(':');
    if (at < 0) return tokens.color[mode][ref as ColorKey];
    return tokens.color[ref.slice(0, at) as ThemeMode][ref.slice(at + 1) as ColorKey];
}

export function lessValue(tokens: Tokens, mode: ThemeMode, e: Expr): string {
    if (typeof e === 'string') return hex(tokens, mode, e);
    return `mix(${hex(tokens, mode, e[1])}, ${hex(tokens, mode, e[2])}, ${e[3]}%)`;
}

export function cssValue(tokens: Tokens, mode: ThemeMode, e: Expr): string {
    if (typeof e === 'string') return hex(tokens, mode, e);
    return `color-mix(in srgb, ${hex(tokens, mode, e[1])} ${e[3]}%, ${hex(tokens, mode, e[2])})`;
}

function px(value: number): string {
    return `${Math.round(value * 100) / 100}px`;
}

const DENSITY: Record<Tokens['density'], number> = { compact: 0.875, comfortable: 1, spacious: 1.125 };

/** Sizes and fonts: [variable without @lm-, LESS value]. */
export function sizeVars(tokens: Tokens): [string, string][] {
    const unit = tokens.spacing.base * DENSITY[tokens.density];
    const r = tokens.radius.base;
    const t = tokens.typography;
    return [
        ['font', `~'${fontStack(t.body, 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif')}'`],
        ['font-mono', `~'${fontStack(t.mono, 'monospace')}'`],
        ['page-font-size', px(Math.round(14 * t.scale))],
        ['space-1', px(unit)],
        ['space-2', px(unit * 2)],
        ['space-3', px(unit * 3)],
        ['space-4', px(unit * 4)],
        ['space-5', px(unit * 6)],
        ['space-6', px(unit * 8)],
        ['space-7', px(unit * 12)],
        // The skin's radii at the default 14px card radius: 6, 10, 12 and 14px.
        ['radius-s', px(Math.round(r * 0.43))],
        ['radius-m', px(Math.round(r * 0.71))],
        ['radius-l', px(Math.round(r * 0.86))],
        ['radius-xl', px(r)],
    ];
}

export const LESS_HEAD = '// Lumen tokens v1: ';

/** lumen-custom.less: every @lm-* variable the skin reads, from the tokens. */
export function compileLess(tokens: Tokens): string {
    const name = tokens.meta.name.replace(/[^\x20-\x7e]/g, '');
    const lines = [
        `${LESS_HEAD}${name}`,
        '// Generated by lumen-mail (tokens/roundcube.ts) from a Lumen token file; edit the tokens, not this file.',
    ];
    for (const [v, e] of BRAND_EXPRS) lines.push(`@lm-${v}: ${lessValue(tokens, 'light', e)};`);
    for (const [v, value] of sizeVars(tokens)) lines.push(`@lm-${v}: ${value};`);
    for (const mode of ['light', 'dark'] as const) {
        for (const [role, e] of roleExprs(mode)) lines.push(`@lm-${mode}-${role}: ${lessValue(tokens, mode, e)};`);
    }
    return `${lines.join('\n')}\n`;
}

/** Token URLs as the compiled stylesheet in skins/lumen/styles/ reaches them. */
export const URL_PREFIXES: [string, string][] = [
    ['/lumen/brand/', '../images/'],
    ['/storage/lumen/', '../images/custom/'],
];

/** The shipped Luminare files a token URL may name, as files of the skin. */
export const BRAND_FILES: Record<string, string> = {
    'luminare-mark.svg': 'luminare-mark.svg',
    'luminare-mark-brand-deep.svg': 'luminare-mark-brand-deep.svg',
    'favicon.svg': 'luminare-favicon.ico',
};

export function resolveCssUrls(css: string): string {
    let out = css;
    for (const [from, to] of URL_PREFIXES) {
        out = out.replace(new RegExp(`url\\("${from.replace(/\//g, '\\/')}([^"]*)"\\)`, 'g'), (_m, file: string) =>
            `url("${to}${from === '/lumen/brand/' ? (BRAND_FILES[file] ?? file) : file}")`,
        );
    }
    return out;
}

export const CSS_HEAD = '/* Lumen tokens v1: ';

/** lumen-custom.css: appended to styles.css; the --lumen-* variables, a few rules, custom CSS. */
export function compileCss(tokens: Tokens): string {
    const core = compile(tokens, { scope: ':root', withCustomCss: false })
        .replace(':root[data-theme="dark"] {', 'html.dark-mode {')
        .replace(':root[data-theme="light"] {', ':root:not(.dark-mode) {');
    let css = core;
    css +=
        'h1, h2, h3, .header-title, .boxtitle, .formcontent legend {\n' +
        '    font-family: var(--lumen-font-display);\n    font-weight: var(--lumen-heading-weight);\n}\n';
    if (!tokens.elevation.borders) {
        css += '#layout-sidebar, #layout-list, #layout-content, .popover, .ui-dialog {\n    border-color: transparent !important;\n}\n';
    }
    if (tokens.branding.loginBackground !== '') {
        css +=
            'body.task-login {\n' +
            '    background-image: linear-gradient(rgb(0 0 0 / 45%), rgb(0 0 0 / 45%)), var(--lumen-login-background);\n' +
            '    background-position: center;\n    background-size: cover;\n}\n';
    } else if (!tokens.layout.backgroundGlow) {
        css += 'body.task-login {\n    background-image: none;\n}\n';
    }
    if (tokens.customCss.trim() !== '') css += `/* custom CSS */\n${sanitizeCustomCss(tokens.customCss)}\n`;
    return resolveCssUrls(css);
}

/** Skin path of a token logo or favicon URL ('/images/…'), or '' (Elastic's own). */
export function skinPath(value: string): string {
    if (value.startsWith('/lumen/brand/')) {
        const file = value.slice('/lumen/brand/'.length);
        return `/images/${BRAND_FILES[file] ?? file}`;
    }
    if (value.startsWith('/storage/lumen/')) return `/images/custom/${value.slice('/storage/lumen/'.length)}`;
    return ''; // an https URL: Roundcube serves skin files only, so upload the file instead
}

/** The Luminare mark stands for the skin's Luminare logo set (rail mark, login and compact lockups). */
const LUMINARE_SET = {
    app: '/images/luminare-mark.svg',
    login: '/images/luminare-lockup-horizontal-dark.svg',
    compact: '/images/luminare-lockup-compact-dark.svg',
};

export interface Branding {
    app: string;
    login: string;
    compact: string;
    favicon: string;
    productName: string;
    themeLight: string;
    themeDark: string;
}

/**
 * branding.json: the logo on the task rail and the login page (both Night, so the dark-mode logo
 * comes first), the compact logo for phones, the favicon and the browser colours.
 */
export function branding(tokens: Tokens): Branding {
    const b = tokens.branding;
    const logo = skinPath(b.logoDark !== '' ? b.logoDark : b.logoLight);
    const luminare = logo === '/images/luminare-mark.svg' || logo === '/images/luminare-mark-brand-deep.svg';
    return {
        app: luminare ? LUMINARE_SET.app : logo,
        login: luminare ? LUMINARE_SET.login : logo,
        compact: luminare ? LUMINARE_SET.compact : logo,
        favicon: skinPath(b.favicon),
        productName: b.productName,
        themeLight: tokens.color.light.canvas,
        themeDark: tokens.color.dark.canvas,
    };
}

export function brandingJson(tokens: Tokens): string {
    return `${JSON.stringify(branding(tokens), null, 2)}\n`;
}

/** The role variables as --lm-* custom properties for one mode (the customizer's mock). */
export function previewProperties(tokens: Tokens, mode: ThemeMode): string[] {
    const lines = roleExprs(mode).map(([role, e]) => `--lm-${role}: ${cssValue(tokens, mode, e)};`);
    for (const [v, e] of BRAND_EXPRS) lines.push(`--lm-${v}: ${cssValue(tokens, 'light', e)};`);
    for (const [v, value] of sizeVars(tokens)) {
        lines.push(`--lm-${v}: ${value.startsWith("~'") ? value.slice(2, -1) : value};`);
    }
    return lines;
}

export function readme(tokens: Tokens): string {
    return (
        `Lumen customization for lumen-mail: ${tokens.meta.name.replace(/[^\x20-\x7e]/g, '')}\n\n` +
        'Install on the Roundcube server (a dry run; add --yes to install and rebuild the skin):\n' +
        '  lumen-mail apply-custom <this ZIP> --roundcube /var/www/roundcube\n\n' +
        'Contents: lumen.tokens.json (the token file; import it or this ZIP in the customizer to edit it\n' +
        'again), lumen-custom.less and lumen-custom.css (compiled from the tokens), branding.json and\n' +
        'the uploaded files in custom/. No Roundcube or Elastic file is included; the skin is compiled\n' +
        'on the server from the installed Elastic.\n' +
        'https://github.com/luminare-dev/lumen-mail\n'
    );
}

/** The text files of a customization (uploads go into custom/ beside them), keyed by path. */
export function customizationFiles(tokens: Tokens): Record<string, string> {
    return {
        'lumen.tokens.json': `${JSON.stringify(tokens, null, 2)}\n`,
        'lumen-custom.less': compileLess(tokens),
        'lumen-custom.css': compileCss(tokens),
        'branding.json': brandingJson(tokens),
        'README.txt': readme(tokens),
    };
}
