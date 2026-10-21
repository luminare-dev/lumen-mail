// Tests for skin/lumen.js (the logo swap and theme-color), with Node's built-in test runner and no
// dependencies:
//   node --test "tests/js/*.test.mjs"
// The page shapes (static.php URLs with ?s= cache-busters, data-src-* on the script tag) are the
// ones Roundcube 1.7.3 renders for the login page and the task pages.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const code = readFileSync(new URL('../../skin/lumen.js', import.meta.url), 'utf8');
const ELASTIC_LOGO = 'static.php/skins/elastic/images/logo.svg?s=1787105668';
const SCRIPT_ATTRS = {
    src: 'static.php/skins/lumen/lumen.js?s=1792550238',
    'data-src-app': 'static.php/skins/lumen/images/luminare-mark.svg?s=1',
    'data-src-login': 'static.php/skins/lumen/images/luminare-lockup-horizontal-dark.svg?s=1',
    'data-src-compact': 'static.php/skins/lumen/images/luminare-lockup-compact-dark.svg?s=1',
};

function element(attrs, classNames = []) {
    const classes = new Set(classNames);
    return {
        attrs: { ...attrs },
        getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
        setAttribute(name, value) { this.attrs[name] = String(value); },
        removeAttribute(name) { delete this.attrs[name]; },
        classList: {
            add: (c) => classes.add(c),
            remove: (c) => classes.delete(c),
            contains: (c) => classes.has(c),
        },
    };
}

// The two tags meta.json produces (light and dark, by media query).
const THEME_METAS = () => [
    element({ name: 'theme-color', content: '#F3F6FB', media: '(prefers-color-scheme: light)' }),
    element({ name: 'theme-color', content: '#0A1224', media: '(prefers-color-scheme: dark)' }),
];

function run({ task = 'mail', logoSrc = ELASTIC_LOGO, logos, scriptAttrs = SCRIPT_ATTRS, rcmail = true,
    dark = false } = {}) {
    const logo = logoSrc === null ? null : element({ src: logoSrc, id: 'logo', alt: 'Logo' });
    const env = { task };
    if (logos) env.additional_logos = { ...logos };
    const html = element({}, dark ? ['dark-mode'] : []);
    const metas = THEME_METAS();
    const observers = [];
    class MutationObserver {
        constructor(callback) { this.callback = callback; observers.push(this); }
        observe(target, options) { this.target = target; this.options = options; }
    }
    const document = {
        currentScript: element(scriptAttrs),
        documentElement: html,
        getElementById: (id) => (id === 'logo' ? logo : null),
        querySelectorAll: (selector) => (selector === 'meta[name="theme-color"]' ? metas : []),
        body: { className: `task-${task} action-none` },
    };
    const window = { document, MutationObserver };
    if (rcmail) window.rcmail = { env };
    vm.runInNewContext(code, { window, document });
    // what Elastic's ui.js does when the user switches the colour mode
    const toggle = (on) => {
        html.classList[on ? 'add' : 'remove']('dark-mode');
        observers.forEach((o) => o.callback([]));
    };
    return { logo, env, metas, observers, toggle };
}

test('login page: the Luminare lockup replaces Elastic\'s default logo', () => {
    const { logo, env } = run({ task: 'login' });
    assert.equal(logo.getAttribute('src'), SCRIPT_ATTRS['data-src-login']);
    assert.equal(logo.getAttribute('alt'), 'Luminare');
    assert.ok(logo.classList.contains('lumen-logo'));
    // a copy: the object comes from the vm's realm, so its prototype is not this realm's Object
    assert.deepEqual({ ...env.additional_logos }, {
        dark: SCRIPT_ATTRS['data-src-login'],
        small: SCRIPT_ATTRS['data-src-compact'],
        'small-dark': SCRIPT_ATTRS['data-src-compact'],
    });
});

test('task pages: the mark goes into the menu rail', () => {
    const { logo, env } = run({ task: 'mail' });
    assert.equal(logo.getAttribute('src'), SCRIPT_ATTRS['data-src-app']);
    assert.equal(env.additional_logos.dark, SCRIPT_ATTRS['data-src-app']);
});

test('a logo the admin set with skin_logo always wins', () => {
    const custom = 'https://webmail.example.com/brand.svg';
    const { logo, env } = run({ logoSrc: custom });
    assert.equal(logo.getAttribute('src'), custom);
    assert.equal(env.additional_logos, undefined);
});

test('a logo variant the admin set is never outranked by a filled one', () => {
    // ui.js picks small-dark, then small, then dark: a filled small-dark would beat the admin's small
    for (const logos of [{ small: '/admin-small.svg' }, { dark: '/admin-dark.svg' }, { 'small-dark': '/a.svg' }]) {
        const { logo, env } = run({ logos });
        assert.deepEqual({ ...env.additional_logos }, logos);
        assert.equal(logo.getAttribute('src'), SCRIPT_ATTRS['data-src-app'], 'the main logo is still Luminare');
    }
});

test('theme-color follows html.dark-mode, not only the system setting', () => {
    const light = run({ task: 'mail' });
    assert.deepEqual(light.metas.map((m) => [m.getAttribute('content'), m.getAttribute('media')]),
        [['#F3F6FB', null], ['#F3F6FB', null]]);
    assert.equal(light.observers.length, 1);
    assert.deepEqual([...light.observers[0].options.attributeFilter], ['class']);
    light.toggle(true);
    assert.deepEqual(light.metas.map((m) => m.getAttribute('content')), ['#0A1224', '#0A1224']);
    light.toggle(false);
    assert.deepEqual(light.metas.map((m) => m.getAttribute('content')), ['#F3F6FB', '#F3F6FB']);
    const dark = run({ task: 'settings', dark: true });
    assert.deepEqual(dark.metas.map((m) => m.getAttribute('content')), ['#0A1224', '#0A1224']);
});

test('the login page is Night in both modes, with or without an admin logo', () => {
    for (const logoSrc of [ELASTIC_LOGO, 'https://webmail.example.com/brand.svg']) {
        const { metas, observers } = run({ task: 'login', logoSrc });
        assert.deepEqual(metas.map((m) => m.getAttribute('content')), ['#0A1224', '#0A1224']);
        assert.equal(observers.length, 0);
    }
});

test('nothing happens without rcmail, without a logo or without the image attributes', () => {
    assert.equal(run({ rcmail: false }).logo.getAttribute('src'), ELASTIC_LOGO);
    assert.equal(run({ logoSrc: null }).logo, null);
    const { logo } = run({ scriptAttrs: { src: SCRIPT_ATTRS.src } });
    assert.equal(logo.getAttribute('src'), ELASTIC_LOGO);
});
