// Tests for gallery/data.mjs (what the gallery reads from this repository at build time):
//   node --test tests/js/gallery-data.test.mjs
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { findSkin, galleryData, parseLabels, parseTokens } from '../../gallery/data.mjs';

const ROOT = fileURLToPath(new URL('../..', import.meta.url));

test('parseTokens resolves references and splits brand, modes and shape', () => {
    const t = parseTokens('@lm-night: #0a1224;\n@lm-light-text: @lm-night;\n@lm-dark-text: #F3F6FB;\n'
        + '@lm-radius-m: 10px;\n@lm-roles: text,\n    bg;\n');
    assert.equal(t.brand.night, '#0A1224');
    assert.equal(t.light.text, '#0a1224');
    assert.equal(t.dark.text, '#F3F6FB');
    assert.equal(t.shape['radius-m'], '10px');
    assert.deepEqual(t.roles, ['text', 'bg']);
});

test('the real tokens have every role in both modes', () => {
    const { tokens } = galleryData(ROOT, null);
    assert.ok(tokens.roles.length > 40);
    for (const role of tokens.roles) {
        assert.match(tokens.light[role], /^#[0-9A-F]{6}$/i, `light ${role}`);
        assert.match(tokens.dark[role], /^#[0-9A-F]{6}$/i, `dark ${role}`);
    }
});

test('parseLabels reads the skin localization, escapes included', () => {
    assert.deepEqual(parseLabels("$labels['lumen.a'] = 'It\\'s';\n$labels['lumen.b'] = 'Zwei';"),
        { 'lumen.a': "It's", 'lumen.b': 'Zwei' });
    const { labels } = galleryData(ROOT, null);
    assert.equal(labels.en['lumen.palette_trigger'], 'Jump to');
    assert.equal(labels.de['lumen.palette_trigger'], 'Springen zu');
    assert.deepEqual(Object.keys(labels.de).sort(), Object.keys(labels.en).sort());
});

test('findSkin needs a built lumen/ next to elastic/', () => {
    const dir = mkdtempSync(join(tmpdir(), 'lumen-gallery-'));
    try {
        assert.equal(findSkin(null), null);
        assert.equal(findSkin(dir), null);
        mkdirSync(join(dir, 'lumen', 'styles'), { recursive: true });
        mkdirSync(join(dir, 'elastic'), { recursive: true });
        writeFileSync(join(dir, 'lumen', 'styles', 'styles.min.css'), '/* css */');
        assert.equal(findSkin(dir), null, 'no elastic/meta.json yet');
        writeFileSync(join(dir, 'elastic', 'meta.json'), '{}');
        writeFileSync(join(dir, 'lumen', 'lumen-build.stamp'), JSON.stringify({ lumen_version: '1.2.3', roundcube_version: '1.7.3' }));
        const skin = findSkin(dir);
        assert.equal(skin.lumenVersion, '1.2.3');
        assert.equal(skin.roundcubeVersion, '1.7.3');
        assert.equal(skin.bootstrap, false);
    } finally {
        rmSync(dir, { recursive: true, force: true });
    }
});
