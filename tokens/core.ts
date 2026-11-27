// Lumen design tokens: types, validation, CSS compiler and contrast checks.
//
// This file has no imports on purpose: the panel bundles it with Vite, and the overlay's tests run
// it directly with `node --experimental-strip-types`. app/Lumen/Tokens/TokenCompiler.php is the
// PHP twin of `compile()`; tests/parity checks that both produce the same CSS for every preset.
// The schema is documented in docs/tokens.md.

export const SCHEMA_VERSION = 1;

export const COLOR_KEYS = [
    'canvas',
    'surfaceSunken',
    'surface',
    'surfaceRaised',
    'border',
    'text',
    'textMuted',
    'accent',
    'accentSecondary',
    'accentText',
    'accentContrast',
    'success',
    'warning',
    'danger',
    'info',
    'focus',
] as const;

export type ColorKey = (typeof COLOR_KEYS)[number];
export type ModeColors = Record<ColorKey, string>;
export type ThemeMode = 'dark' | 'light';
export type DefaultMode = ThemeMode | 'system';

export const ENUMS = {
    defaultMode: ['system', 'dark', 'light'],
    density: ['compact', 'comfortable', 'spacious'],
    shadow: ['none', 'soft', 'medium', 'strong'],
    sidebar: ['floating', 'flush'],
    indicator: ['pill', 'bar', 'glow'],
    contentWidth: ['full', 'wide', 'narrow'],
} as const;

export const RANGES = {
    scale: [0.85, 1.25],
    headingWeight: [400, 800],
    radius: [0, 28],
    spacing: [3, 6],
    sidebarWidth: [220, 360],
} as const;

export const LIMITS = { productName: 60, family: 200, url: 2048, customCss: 20000, metaText: 200 } as const;

export const BRANDING_KEYS = ['logoDark', 'logoLight', 'favicon', 'loginBackground'] as const;
export type BrandingAssetKey = (typeof BRANDING_KEYS)[number];

export interface Tokens {
    version: number;
    meta: { name: string; description: string };
    mode: { default: DefaultMode; allowToggle: boolean };
    color: { dark: ModeColors; light: ModeColors };
    typography: {
        display: string;
        body: string;
        mono: string;
        stylesheet: string;
        scale: number;
        headingWeight: number;
    };
    radius: { base: number };
    spacing: { base: number };
    density: (typeof ENUMS.density)[number];
    elevation: { shadow: (typeof ENUMS.shadow)[number]; borders: boolean };
    layout: {
        sidebar: (typeof ENUMS.sidebar)[number];
        sidebarWidth: number;
        indicator: (typeof ENUMS.indicator)[number];
        contentWidth: (typeof ENUMS.contentWidth)[number];
        backgroundGlow: boolean;
    };
    branding: {
        productName: string;
        logoDark: string;
        logoLight: string;
        favicon: string;
        loginBackground: string;
    };
    customCss: string;
}

export interface NormalizeResult {
    tokens: Tokens;
    errors: string[];
}

type Json = Record<string, unknown>;

const HEX = /^#[0-9a-fA-F]{6}$/;
const PLAIN = /^[^<>]*$/;
const FAMILY = /^[A-Za-z0-9 ,'"_.-]*$/;
const LOCAL_URL = /^\/(?:storage\/lumen|lumen\/brand)\/[A-Za-z0-9._-]+$/;
const HTTPS_URL = /^https:\/\/[^\s"'()\\<>]+$/;

function isObject(value: unknown): value is Json {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function obj(value: unknown): Json {
    return isObject(value) ? value : {};
}

/**
 * Checks and completes a token document. Missing or invalid values fall back to `defaults`
 * (normally the Luminare preset); every replaced value is reported in `errors`, so an import can
 * show what was dropped. The result is always a complete, safe token set.
 */
export function normalize(input: unknown, defaults: Tokens): NormalizeResult {
    const errors: string[] = [];
    const src = obj(input);

    const str = (path: string, value: unknown, fallback: string, max: number, pattern?: RegExp): string => {
        if (value === undefined) return fallback;
        if (typeof value !== 'string' || value.length > max || (pattern && !pattern.test(value))) {
            errors.push(path);
            return fallback;
        }
        return value.trim();
    };
    const num = (path: string, value: unknown, fallback: number, range: readonly [number, number]): number => {
        if (value === undefined) return fallback;
        if (typeof value !== 'number' || !Number.isFinite(value) || value < range[0] || value > range[1]) {
            errors.push(path);
            return fallback;
        }
        return value;
    };
    const bool = (path: string, value: unknown, fallback: boolean): boolean => {
        if (value === undefined) return fallback;
        if (typeof value !== 'boolean') {
            errors.push(path);
            return fallback;
        }
        return value;
    };
    const oneOf = <T extends string>(path: string, value: unknown, fallback: T, allowed: readonly T[]): T => {
        if (value === undefined) return fallback;
        if (typeof value !== 'string' || !(allowed as readonly string[]).includes(value)) {
            errors.push(path);
            return fallback;
        }
        return value as T;
    };
    const url = (path: string, value: unknown, fallback: string): string => {
        if (value === undefined) return fallback;
        if (value === '') return '';
        if (
            typeof value !== 'string' ||
            value.length > LIMITS.url ||
            !(LOCAL_URL.test(value) || HTTPS_URL.test(value))
        ) {
            errors.push(path);
            return fallback;
        }
        return value;
    };

    if (src.version !== undefined && src.version !== SCHEMA_VERSION) errors.push('version');

    const meta = obj(src.meta);
    const mode = obj(src.mode);
    const color = obj(src.color);
    const typography = obj(src.typography);
    const elevation = obj(src.elevation);
    const layout = obj(src.layout);
    const branding = obj(src.branding);

    const colors = (which: ThemeMode): ModeColors => {
        const given = obj(color[which]);
        const out = {} as ModeColors;
        for (const key of COLOR_KEYS) {
            const value = str(`color.${which}.${key}`, given[key], defaults.color[which][key], 7, HEX);
            out[key] = value.toUpperCase();
        }
        return out;
    };

    const tokens: Tokens = {
        version: SCHEMA_VERSION,
        meta: {
            name: str('meta.name', meta.name, defaults.meta.name, LIMITS.metaText, PLAIN),
            description: str('meta.description', meta.description, defaults.meta.description, LIMITS.metaText, PLAIN),
        },
        mode: {
            default: oneOf('mode.default', mode.default, defaults.mode.default, ENUMS.defaultMode),
            allowToggle: bool('mode.allowToggle', mode.allowToggle, defaults.mode.allowToggle),
        },
        color: { dark: colors('dark'), light: colors('light') },
        typography: {
            display: str('typography.display', typography.display, defaults.typography.display, LIMITS.family, FAMILY),
            body: str('typography.body', typography.body, defaults.typography.body, LIMITS.family, FAMILY),
            mono: str('typography.mono', typography.mono, defaults.typography.mono, LIMITS.family, FAMILY),
            stylesheet:
                typography.stylesheet === ''
                    ? ''
                    : str(
                          'typography.stylesheet',
                          typography.stylesheet,
                          defaults.typography.stylesheet,
                          LIMITS.url,
                          HTTPS_URL,
                      ),
            scale: num('typography.scale', typography.scale, defaults.typography.scale, RANGES.scale),
            headingWeight: num(
                'typography.headingWeight',
                typography.headingWeight,
                defaults.typography.headingWeight,
                RANGES.headingWeight,
            ),
        },
        radius: { base: num('radius.base', obj(src.radius).base, defaults.radius.base, RANGES.radius) },
        spacing: { base: num('spacing.base', obj(src.spacing).base, defaults.spacing.base, RANGES.spacing) },
        density: oneOf('density', src.density, defaults.density, ENUMS.density),
        elevation: {
            shadow: oneOf('elevation.shadow', elevation.shadow, defaults.elevation.shadow, ENUMS.shadow),
            borders: bool('elevation.borders', elevation.borders, defaults.elevation.borders),
        },
        layout: {
            sidebar: oneOf('layout.sidebar', layout.sidebar, defaults.layout.sidebar, ENUMS.sidebar),
            sidebarWidth: num(
                'layout.sidebarWidth',
                layout.sidebarWidth,
                defaults.layout.sidebarWidth,
                RANGES.sidebarWidth,
            ),
            indicator: oneOf('layout.indicator', layout.indicator, defaults.layout.indicator, ENUMS.indicator),
            contentWidth: oneOf(
                'layout.contentWidth',
                layout.contentWidth,
                defaults.layout.contentWidth,
                ENUMS.contentWidth,
            ),
            backgroundGlow: bool('layout.backgroundGlow', layout.backgroundGlow, defaults.layout.backgroundGlow),
        },
        branding: {
            productName: str(
                'branding.productName',
                branding.productName,
                defaults.branding.productName,
                LIMITS.productName,
                PLAIN,
            ),
            logoDark: url('branding.logoDark', branding.logoDark, defaults.branding.logoDark),
            logoLight: url('branding.logoLight', branding.logoLight, defaults.branding.logoLight),
            favicon: url('branding.favicon', branding.favicon, defaults.branding.favicon),
            loginBackground: url(
                'branding.loginBackground',
                branding.loginBackground,
                defaults.branding.loginBackground,
            ),
        },
        customCss: str('customCss', src.customCss, defaults.customCss, LIMITS.customCss),
    };

    return { tokens, errors };
}

// ---------------------------------------------------------------------------------------------
// CSS compiler. Only token values are printed; all arithmetic is left to CSS calc() and
// color-mix(), so this file and the PHP twin cannot drift through float formatting.
// ---------------------------------------------------------------------------------------------

const DENSITY_FACTOR: Record<Tokens['density'], string> = { compact: '0.875', comfortable: '1', spacious: '1.125' };
const SHADOW_ALPHA: Record<ThemeMode, Record<Tokens['elevation']['shadow'], string>> = {
    dark: { none: '0', soft: '0.22', medium: '0.34', strong: '0.5' },
    light: { none: '0', soft: '0.06', medium: '0.1', strong: '0.16' },
};
const SHADOW_RGB: Record<ThemeMode, string> = { dark: '0 0 0', light: '15 23 42' };
const CONTENT_WIDTH: Record<Tokens['layout']['contentWidth'], string> = {
    full: 'none',
    wide: '1440px',
    narrow: '1200px',
};
const RADIUS_STEPS: [string, string][] = [
    ['xs', '0.17'],
    ['sm', '0.33'],
    ['md', '0.5'],
    ['lg', '0.67'],
    ['xl', '1'],
    ['2xl', '1.33'],
    ['3xl', '2'],
];
const TEXT_STEPS: [string, string][] = [
    ['xs', '0.75rem'],
    ['sm', '0.875rem'],
    ['base', '1rem'],
    ['lg', '1.125rem'],
    ['xl', '1.25rem'],
    ['2xl', '1.5rem'],
    ['3xl', '1.875rem'],
    ['4xl', '2.25rem'],
];
// Share of the canvas colour mixed into the text colour for each step of Tailwind's grey scales.
const GREY_STEPS: [string, string][] = [
    ['50', '3'],
    ['100', '8'],
    ['200', '18'],
    ['300', '30'],
    ['400', '45'],
    ['500', '58'],
    ['600', '70'],
    ['700', '80'],
    ['800', '88'],
    ['900', '94'],
    ['950', '97'],
];
const GREYS = ['zinc', 'neutral', 'gray'];
const STATUS: [string, ColorKey][] = [
    ['red', 'danger'],
    ['green', 'success'],
    ['emerald', 'success'],
    ['yellow', 'warning'],
    ['amber', 'warning'],
    ['blue', 'info'],
];

export function kebab(key: string): string {
    return key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

/** Quotes a family list item by item: `Sora, ui-sans-serif` stays readable and safe. */
export function fontStack(family: string, fallback: string): string {
    const parts = family
        .split(',')
        .map((part) => part.trim().replace(/["']/g, ''))
        .filter((part) => part !== '');
    const generic = /^(serif|sans-serif|monospace|cursive|fantasy|system-ui|ui-[a-z-]+|-apple-system)$/;
    const quoted = parts.map((part) => (generic.test(part) ? part : `"${part}"`));
    return [...quoted, fallback].join(', ');
}

export function cssUrl(value: string): string {
    return value === '' ? 'none' : `url("${value}")`;
}

/**
 * Makes custom CSS safe inside a <style> element: every `<` becomes the CSS escape `\3c `, so no
 * `</style`, `<!--` or `<script` can appear in the output, in any case or spelling. In a CSS string
 * the escape still reads as `<`; anywhere else `<` is not valid CSS, so nothing working is lost.
 */
export function sanitizeCustomCss(css: string): string {
    return css.replace(/</g, '\\3c ');
}

function mix(a: string, b: string, percentOfA: string): string {
    return `color-mix(in srgb, ${a} ${percentOfA}%, ${b})`;
}

function modeBlock(tokens: Tokens, mode: ThemeMode): string[] {
    const c = tokens.color[mode];
    const v = (key: ColorKey) => `var(--lumen-${kebab(key)})`;
    const lines: string[] = [];
    for (const key of COLOR_KEYS) lines.push(`--lumen-${kebab(key)}: ${c[key]};`);

    lines.push(
        `--lumen-shadow-rgb: ${SHADOW_RGB[mode]};`,
        `--lumen-shadow-alpha: ${SHADOW_ALPHA[mode][tokens.elevation.shadow]};`,
        `--lumen-glow: ${mix(v('accent'), 'transparent', mode === 'dark' ? '16' : '10')};`,
        `--lumen-glow-secondary: ${mix(v('accentSecondary'), 'transparent', mode === 'dark' ? '12' : '8')};`,
        `--lumen-border-color: ${tokens.elevation.borders ? v('border') : 'transparent'};`,
        `--brand-color: ${v('accent')};`,
        `--panel-accent: ${v('accent')};`,
        `--color-canvas: ${v('canvas')};`,
        `--color-bg: ${v('canvas')};`,
        `--color-bg-raised: ${v('surface')};`,
        `--color-bg-lowered: ${v('surfaceSunken')};`,
        `--color-primary: ${v('text')};`,
        `--color-secondary: ${v('textMuted')};`,
        `--color-overlay: ${v('text')};`,
        `--color-accent: ${v('text')};`,
        `--color-accent-foreground: ${v('surface')};`,
        `--color-ring: ${v('focus')};`,
        `--color-mocha-700: ${v('canvas')};`,
        `--color-mocha-600: ${v('surfaceSunken')};`,
        `--color-mocha-500: ${v('surface')};`,
        `--color-mocha-400: ${v('surfaceRaised')};`,
        `--color-mocha-300: ${v('border')};`,
        `--color-mocha-200: ${mix(v('border'), v('textMuted'), '65')};`,
        `--color-mocha-100: ${mix(v('border'), v('textMuted'), '35')};`,
        `--color-mocha-50: ${mix(v('textMuted'), v('border'), '85')};`,
        `--color-cream-50: ${v('text')};`,
        `--color-cream-100: ${v('text')};`,
        `--color-cream-200: ${v('text')};`,
        `--color-cream-300: ${v('text')};`,
        `--color-cream-400: ${v('text')};`,
        `--color-cream-500: ${mix(v('text'), v('textMuted'), '80')};`,
        `--color-hydro: ${v('accent')};`,
    );

    const hydro: [string, string][] = [
        ['50', mix(v('accent'), v('surface'), '10')],
        ['100', mix(v('accent'), v('surface'), '20')],
        ['200', mix(v('accent'), v('surface'), '35')],
        ['300', v('accentText')],
        ['400', v('accentText')],
        ['500', v('accent')],
        ['600', mix(v('accent'), v('canvas'), '85')],
        ['700', mix(v('accent'), v('canvas'), '70')],
        ['800', mix(v('accent'), v('canvas'), '55')],
        ['900', mix(v('accent'), v('canvas'), '40')],
    ];
    for (const [step, value] of hydro) lines.push(`--color-hydro-${step}: ${value};`);
    lines.push(`--color-brand: ${v('accent')};`);
    for (const [step, value] of hydro) lines.push(`--color-brand-${step}: ${value};`);

    for (const grey of GREYS) {
        for (const [step, share] of GREY_STEPS) {
            lines.push(`--color-${grey}-${step}: ${mix(v('canvas'), v('text'), share)};`);
        }
    }

    for (const [name, key] of STATUS) {
        lines.push(
            `--color-${name}-300: ${mix(v(key), v('text'), '80')};`,
            `--color-${name}-400: ${v(key)};`,
            `--color-${name}-500: ${v(key)};`,
            `--color-${name}-600: ${mix(v(key), v('canvas'), '85')};`,
        );
    }

    lines.push(
        '--shadow-xs: 0 1px 2px rgb(var(--lumen-shadow-rgb) / var(--lumen-shadow-alpha));',
        '--shadow-sm: 0 1px 3px rgb(var(--lumen-shadow-rgb) / calc(var(--lumen-shadow-alpha) * 1.2)), 0 1px 2px rgb(var(--lumen-shadow-rgb) / var(--lumen-shadow-alpha));',
        '--shadow-md: 0 6px 16px -4px rgb(var(--lumen-shadow-rgb) / calc(var(--lumen-shadow-alpha) * 1.4));',
        '--shadow-lg: 0 14px 32px -8px rgb(var(--lumen-shadow-rgb) / calc(var(--lumen-shadow-alpha) * 1.8));',
        '--shadow-xl: 0 24px 56px -12px rgb(var(--lumen-shadow-rgb) / calc(var(--lumen-shadow-alpha) * 2.2));',
        '--shadow-2xl: 0 32px 72px -16px rgb(var(--lumen-shadow-rgb) / calc(var(--lumen-shadow-alpha) * 2.6));',
    );
    return lines;
}

function sharedBlock(tokens: Tokens): string[] {
    const t = tokens.typography;
    const lines = [
        `--lumen-font-display: ${fontStack(t.display, 'ui-sans-serif, system-ui, sans-serif')};`,
        `--lumen-font-body: ${fontStack(t.body, 'ui-sans-serif, system-ui, sans-serif')};`,
        `--lumen-font-mono: ${fontStack(t.mono, 'monospace')};`,
        `--lumen-heading-weight: ${t.headingWeight};`,
        `--lumen-font-scale: ${t.scale};`,
        `--font-sans: var(--lumen-font-body);`,
        `--font-mono: var(--lumen-font-mono);`,
        `--lumen-radius: ${tokens.radius.base}px;`,
    ];
    for (const [step, factor] of RADIUS_STEPS) lines.push(`--radius-${step}: calc(var(--lumen-radius) * ${factor});`);
    lines.push(
        `--spacing: calc(${tokens.spacing.base}px * ${DENSITY_FACTOR[tokens.density]});`,
        `--lumen-density: ${DENSITY_FACTOR[tokens.density]};`,
    );
    for (const [step, size] of TEXT_STEPS) lines.push(`--text-${step}: calc(${size} * var(--lumen-font-scale));`);
    lines.push(
        `--sidebar-full-width: ${tokens.layout.sidebarWidth}px;`,
        `--lumen-content-max: ${CONTENT_WIDTH[tokens.layout.contentWidth]};`,
        `--lumen-login-background: ${cssUrl(tokens.branding.loginBackground)};`,
    );
    return lines;
}

export interface CompileOptions {
    /**
     * Selector the variables are scoped to. The default beats every palette rule of the panel
     * (specificity 0,5,0 against at most 0,3,0), whatever order the stylesheets load in.
     * The admin preview passes `.lumen-preview` to scope a copy to one element.
     */
    scope?: string;
    /** Leave out the custom CSS (the scoped preview never includes it). */
    withCustomCss?: boolean;
}

const ROOT_SCOPE = ':root:root:root[data-lumen]';

export function compile(tokens: Tokens, options: CompileOptions = {}): string {
    const scope = options.scope ?? ROOT_SCOPE;
    const block = (selector: string, lines: string[]) => `${selector} {\n    ${lines.join('\n    ')}\n}\n`;
    let css = `/* Lumen tokens v${SCHEMA_VERSION}: ${tokens.meta.name.replace(/\*\//g, '')} */\n`;
    css += block(scope, sharedBlock(tokens));
    css += block(`${scope}[data-theme="dark"]`, modeBlock(tokens, 'dark'));
    css += block(`${scope}[data-theme="light"]`, modeBlock(tokens, 'light'));
    if ((options.withCustomCss ?? true) && tokens.customCss.trim() !== '') {
        css += `/* custom CSS */\n${sanitizeCustomCss(tokens.customCss)}\n`;
    }
    return css;
}

/** The data attributes the stylesheet reads for the layout switches (set on <html>). */
export function layoutAttributes(tokens: Tokens): Record<string, string> {
    return {
        'data-lumen': '1',
        'data-lumen-sidebar': tokens.layout.sidebar,
        'data-lumen-indicator': tokens.layout.indicator,
        'data-lumen-width': tokens.layout.contentWidth,
        'data-lumen-glow': tokens.layout.backgroundGlow ? 'on' : 'off',
        'data-lumen-density': tokens.density,
        'data-lumen-shadow': tokens.elevation.shadow,
        'data-lumen-toggle': tokens.mode.allowToggle ? 'on' : 'off',
        'data-lumen-login': tokens.branding.loginBackground === '' ? 'gradient' : 'image',
    };
}

// ---------------------------------------------------------------------------------------------
// Contrast (WCAG 2.2 relative luminance).
// ---------------------------------------------------------------------------------------------

export function luminance(hex: string): number {
    const n = Number.parseInt(hex.slice(1), 16);
    const channel = (value: number) => {
        const s = value / 255;
        return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

export function contrast(a: string, b: string): number {
    const la = luminance(a);
    const lb = luminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

export interface ContrastPair {
    fg: ColorKey;
    bg: ColorKey;
    min: number;
    label: string;
}

/** Every text or UI pair the theme draws. 4.5 for text, 3 for large text and UI parts. */
export const CONTRAST_PAIRS: ContrastPair[] = [
    { fg: 'text', bg: 'canvas', min: 4.5, label: 'Text on the page background' },
    { fg: 'text', bg: 'surface', min: 4.5, label: 'Text on cards' },
    { fg: 'text', bg: 'surfaceRaised', min: 4.5, label: 'Text on raised surfaces' },
    { fg: 'textMuted', bg: 'surface', min: 4.5, label: 'Muted text on cards' },
    { fg: 'textMuted', bg: 'canvas', min: 4.5, label: 'Muted text on the page background' },
    { fg: 'accentText', bg: 'surface', min: 4.5, label: 'Accent text and links on cards' },
    { fg: 'accentContrast', bg: 'accent', min: 4.5, label: 'Button text on the accent' },
    { fg: 'accentContrast', bg: 'accentSecondary', min: 4.5, label: 'Button text on the gradient end' },
    { fg: 'danger', bg: 'surface', min: 4.5, label: 'Error text on cards' },
    { fg: 'success', bg: 'surface', min: 4.5, label: 'Success text on cards' },
    { fg: 'warning', bg: 'surface', min: 4.5, label: 'Warning text on cards' },
    { fg: 'info', bg: 'surface', min: 4.5, label: 'Info text on cards' },
    { fg: 'focus', bg: 'surface', min: 3, label: 'Focus ring on cards' },
    { fg: 'focus', bg: 'canvas', min: 3, label: 'Focus ring on the page background' },
];

export interface ContrastResult extends ContrastPair {
    mode: ThemeMode;
    ratio: number;
    ok: boolean;
}

export function contrastReport(tokens: Tokens): ContrastResult[] {
    const out: ContrastResult[] = [];
    for (const mode of ['dark', 'light'] as const) {
        for (const pair of CONTRAST_PAIRS) {
            const ratio = contrast(tokens.color[mode][pair.fg], tokens.color[mode][pair.bg]);
            out.push({ ...pair, mode, ratio, ok: ratio >= pair.min });
        }
    }
    return out;
}
