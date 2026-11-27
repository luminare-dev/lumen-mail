// Compile a Lumen token file into a lumen-mail customization folder (Node.js 22.6+, no packages):
//
//   node --experimental-strip-types tokens/compile.mjs my.lumen.json --out custom/
//   node --experimental-strip-types tokens/compile.mjs --preset aurora --out /tmp/aurora
//
// The folder holds lumen.tokens.json (the checked, complete token set), lumen-custom.less (the
// skin's LESS variables, compiled into the skin on the server), lumen-custom.css (appended to the
// compiled stylesheet), branding.json (logos, favicon, browser colours) and README.txt. Uploaded
// files the tokens name as /storage/lumen/<file> go into its custom/ subfolder; the customizer ZIP
// adds them itself. Exit 1 when the token file has invalid values (they are listed and replaced by
// the Luminare default), 2 on a usage error.

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { normalize } from "./core.ts";
import { customizationFiles } from "./roundcube.ts";

const here = dirname(fileURLToPath(import.meta.url));
export const PRESET_NAMES = ["luminare", "graphite", "aurora", "contrast"];

export function preset(name) {
  return JSON.parse(readFileSync(join(here, "presets", `${name}.json`), "utf8"));
}

function main(argv) {
  let input = null;
  let out = null;
  let presetName = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--out") out = argv[++i];
    else if (argv[i] === "--preset") presetName = argv[++i];
    else if (!input) input = argv[i];
    else return usage(`unexpected argument ${argv[i]}`);
  }
  if (!out || Boolean(input) === Boolean(presetName)) return usage("give a token file or --preset, and --out");
  if (presetName && !PRESET_NAMES.includes(presetName)) return usage(`unknown preset ${presetName}`);
  let doc;
  try {
    doc = presetName ? preset(presetName) : JSON.parse(readFileSync(input, "utf8"));
  } catch (err) {
    return usage(`cannot read ${input}: ${err.message}`);
  }
  const { tokens, errors } = normalize(doc, preset("luminare"));
  mkdirSync(out, { recursive: true });
  for (const [name, text] of Object.entries(customizationFiles(tokens))) writeFileSync(join(out, name), text);
  for (const path of errors) console.error(`replaced by the default: ${path}`);
  console.log(`${out}: ${tokens.meta.name}`);
  return errors.length ? 1 : 0;
}

function usage(message) {
  console.error(`error: ${message}\nusage: tokens/compile.mjs (TOKENS.json | --preset NAME) --out DIR`);
  return 2;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) process.exit(main(process.argv.slice(2)));
