// The digest of everything the command palette bundle is built from, so a build can tell a
// current bundle from a stale one. palette/vite.config.js writes it into the bundle's banner
// ("sources sha256:<hex>"); scripts/check-palette.mjs and the generator
// (generator/lumen_mail/sources.py, palette_inputs_digest) recompute it from the checkout and stop
// when they differ. Both implementations must agree; tests/test_palette_digest.py compares them.
//
// Inputs: every file under palette/src, palette/vite.config.js and package.json (it pins React
// and the toolchain, and carries the version the banner names). For each file, sorted by its
// path relative to the repository root (with "/"): "<path>\0<sha256 of the content>\n"; the
// digest is the sha256 of all those lines.
//
// Run: node scripts/palette-inputs.mjs [root]   prints sha256:<hex>

import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const PALETTE_INPUTS = ["palette/src", "palette/vite.config.js", "package.json"];

function files(root, rel) {
  const path = join(root, rel);
  let info;
  try {
    info = statSync(path);
  } catch {
    return [];
  }
  if (info.isFile()) return [rel];
  if (!info.isDirectory()) return [];
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() || entry.isFile() ? files(root, `${rel}/${entry.name}`) : [],
  );
}

export function paletteInputsDigest(root) {
  const all = PALETTE_INPUTS.flatMap((rel) => files(root, rel)).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const outer = createHash("sha256");
  for (const rel of all) {
    const inner = createHash("sha256").update(readFileSync(join(root, rel))).digest("hex");
    outer.update(`${rel}\0${inner}\n`, "utf8");
  }
  return `sha256:${outer.digest("hex")}`;
}

const self = fileURLToPath(import.meta.url);
if (process.argv[1] && resolve(process.argv[1]) === self) {
  console.log(paletteInputsDigest(resolve(process.argv[2] ?? join(self, "..", ".."))));
}
