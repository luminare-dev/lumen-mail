// Data for the gallery, read at build time from this repository's own sources (never from
// Roundcube): the design tokens (src/less/lumen-tokens.less), the colour pairs the contrast
// check covers (src/less/contrast-pairs.json), the skin's labels (skin/localization/*.inc) and,
// optionally, a built skin for the preview pages (LUMEN_GALLERY_SKINS, see gallery/README section
// in the main README). Plain Node, no dependencies; tests/js/gallery-data.test.mjs covers it.

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** @lm-* tokens: brand colours, both modes' roles and the shape/motion values, references resolved. */
export function parseTokens(text) {
  const raw = {};
  for (const m of text.matchAll(/^@(lm-[a-z0-9-]+):\s*([^;]+);/gmu)) raw[m[1]] = m[2].trim();
  const resolve = (value, depth = 0) =>
    value.startsWith("@") && depth < 5 && raw[value.slice(1)] !== undefined ? resolve(raw[value.slice(1)], depth + 1) : value;
  const rolesMatch = text.match(/@lm-roles:\s*([^;]+);/u);
  const roles = rolesMatch ? rolesMatch[1].split(",").map((r) => r.trim()).filter(Boolean) : [];
  const out = { brand: {}, light: {}, dark: {}, roles, shape: {} };
  for (const [name, value] of Object.entries(raw)) {
    const v = resolve(value);
    const mode = name.match(/^lm-(light|dark)-(.+)$/u);
    if (mode) out[mode[1]][mode[2]] = v;
    else if (/^#[0-9a-f]{6}$/iu.test(v)) out.brand[name.slice(3)] = v.toUpperCase();
    else if (name !== "lm-roles") out.shape[name.slice(3)] = v;
  }
  return out;
}

/** $labels['lumen.x'] = '...'; -> { "lumen.x": "..." } (single-quoted PHP strings, as we write them). */
export function parseLabels(text) {
  const labels = {};
  for (const m of text.matchAll(/\$labels\['([a-z0-9_.]+)'\]\s*=\s*'((?:[^'\\]|\\.)*)';/gu)) {
    labels[m[1]] = m[2].replace(/\\(['\\])/gu, "$1");
  }
  return labels;
}

/**
 * A built skin to preview: <skins>/lumen (a build or an installed skins/lumen) next to the
 * <skins>/elastic it was built against. Returns null when there is none.
 */
export function findSkin(skins) {
  if (!skins) return null;
  const css = join(skins, "lumen", "styles", "styles.min.css");
  if (!existsSync(css) || !existsSync(join(skins, "elastic", "meta.json"))) return null;
  let stamp = {};
  try {
    stamp = JSON.parse(readFileSync(join(skins, "lumen", "lumen-build.stamp"), "utf8"));
  } catch {
    stamp = {};
  }
  return {
    dir: skins,
    lumenVersion: stamp.lumen_version ?? null,
    roundcubeVersion: stamp.roundcube_version ?? null,
    builtAt: stamp.built_at ?? null,
    bootstrap: existsSync(join(skins, "elastic", "deps", "bootstrap.min.css")),
  };
}

export function galleryData(root, skins) {
  const read = (rel) => readFileSync(join(root, rel), "utf8");
  const skin = findSkin(skins);
  return {
    version: read("version.txt").trim(),
    tokens: parseTokens(read("src/less/lumen-tokens.less")),
    pairs: JSON.parse(read("src/less/contrast-pairs.json")).pairs,
    labels: { en: parseLabels(read("skin/localization/en_US.inc")), de: parseLabels(read("skin/localization/de_DE.inc")) },
    skin: skin && { lumenVersion: skin.lumenVersion, roundcubeVersion: skin.roundcubeVersion, builtAt: skin.builtAt, bootstrap: skin.bootstrap },
  };
}
