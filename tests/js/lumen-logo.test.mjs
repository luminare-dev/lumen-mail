// Tests for skin/lumen.js (the logo swap), with Node's built-in test runner and no dependencies:
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

function element(attrs) {
    const classes = new Set();
    return {
        attrs: { ...attrs },
        getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
        setAttribute(name, value) { this.attrs[name] = String(value); },
        classList: { add: (c) => classes.add(c), contains: (c) => classes.has(c) },
    };
}

function run({ task = 'mail', logoSrc = ELASTIC_LOGO, logos, scriptAttrs = SCRIPT_ATTRS, rcmail = true } = {}) {
    const logo = logoSrc === null ? null : element({ src: logoSrc, id: 'logo', alt: 'Logo' });
    const env = { task };
    if (logos) env.additional_logos = { ...logos };
    const document = {
        currentScript: element(scriptAttrs),
        getElementById: (id) => (id === 'logo' ? logo : null),
        body: { className: `task-${task} action-none` },
    };
    const window = { document };
    if (rcmail) window.rcmail = { env };
    vm.runInNewContext(code, { window, document });
    return { logo, env };
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

test('only the logo types the admin did not set are filled', () => {
    const { env } = run({ logos: { small: '/admin-small.svg' } });
    assert.equal(env.additional_logos.small, '/admin-small.svg');
    assert.equal(env.additional_logos.dark, SCRIPT_ATTRS['data-src-app']);
    assert.equal(env.additional_logos['small-dark'], SCRIPT_ATTRS['data-src-compact']);
});

test('nothing happens without rcmail, without a logo or without the image attributes', () => {
    assert.equal(run({ rcmail: false }).logo.getAttribute('src'), ELASTIC_LOGO);
    assert.equal(run({ logoSrc: null }).logo, null);
    const { logo } = run({ scriptAttrs: { src: SCRIPT_ATTRS.src } });
    assert.equal(logo.getAttribute('src'), ELASTIC_LOGO);
});
