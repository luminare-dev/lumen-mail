// Check the built command palette (palette/dist/lumen-palette.js) before it goes into a skin:
//
//   * one classic script (IIFE): no import/export statements, no dynamic import(), and no global
//     variable (vite's lib mode needs a name for IIFE builds; the entry exports nothing, so the
//     bundle must not start with "var <name> =");
//   * no network or storage APIs in the bundle, React included (fetch, XMLHttpRequest,
//     WebSocket, EventSource, sendBeacon, localStorage, sessionStorage, indexedDB, cookies);
//   * the licence banner comes first and names the digest of the sources it was built from
//     (scripts/palette-inputs.mjs), which must equal this checkout's when the default file is
//     checked;
//   * size: at most 73 KB after gzip, the number is printed. Measured 2026-10-21 with Vite 8.3.4
//     (Oxc minifier): React 19.3.1 and React DOM alone, in a one-button app built the same way,
//     are 67,439 bytes (65.9 KB) gzip; the palette adds about 6.2 KB (73,825 bytes, 72.1 KB in
//     all). terser compresses React DOM worse (75.0 KB), a newer build target changes nothing.
//     The project's original goal of 70 KB therefore leaves under 4.1 KB for the palette itself;
//     the budget keeps the bundle from growing without a decision.
//
// Run: node scripts/check-palette.mjs [--max-gzip-kb 73] [file]

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { paletteInputsDigest } from "./palette-inputs.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const flag = args.indexOf("--max-gzip-kb");
const maxKb = flag >= 0 ? Number(args[flag + 1]) : 73;
const positional = args.filter((a, i) => !a.startsWith("--") && (flag < 0 || i !== flag + 1));
const file = positional[0] ? resolve(positional[0]) : join(root, "palette", "dist", "lumen-palette.js");

const FORBIDDEN = [
  ["module syntax", /^\s*(?:import|export)\s[^;]*?(?:from\s*["']|[{*])/mu],
  ["dynamic import()", /\bimport\s*\(/u],
  ["fetch()", /\bfetch\s*\(/u],
  ["XMLHttpRequest", /\bXMLHttpRequest\b/u],
  ["WebSocket", /\bWebSocket\b/u],
  ["EventSource", /\bEventSource\b/u],
  ["sendBeacon", /\bsendBeacon\b/u],
  ["localStorage", /\blocalStorage\b/u],
  ["sessionStorage", /\bsessionStorage\b/u],
  ["indexedDB", /\bindexedDB\b/u],
  ["document.cookie", /\.cookie\b/u],
];

let code;
try {
  code = readFileSync(file, "utf8");
} catch {
  console.error(`${file}: missing; run 'npm run build:palette' first`);
  process.exit(1);
}

const problems = FORBIDDEN.filter(([, re]) => re.test(code)).map(([name]) => `contains ${name}`);
if (!code.startsWith("/*! lumen-mail ")) problems.push("the licence banner is missing");
const banner = code.slice(0, code.indexOf("*/") + 2);
const built = /\bsources (sha256:[0-9a-f]{64})\b/u.exec(banner)?.[1];
if (!built) problems.push("the banner does not name the digest of its sources");
else if (!positional[0] && built !== paletteInputsDigest(root)) {
  problems.push(`built from other sources (${built}) than this checkout's (${paletteInputsDigest(root)})`);
}
if (/^\/\*![^*]*\*\/\s*(?:var|let|const)\s+[\w$]+\s*=/u.test(code)) problems.push("declares a global variable");

const raw = Buffer.byteLength(code);
const gzip = gzipSync(code, { level: 9 }).length;
const kb = (n) => (n / 1024).toFixed(1);
console.log(`${file}: ${raw} bytes (${kb(raw)} KB), gzip ${gzip} bytes (${kb(gzip)} KB), limit ${maxKb} KB`);
if (gzip > maxKb * 1024) problems.push(`gzip size ${kb(gzip)} KB is above ${maxKb} KB`);

if (problems.length) {
  for (const p of problems) console.error(`lumen-palette.js: ${p}`);
  process.exit(1);
}
console.log("ok: one classic script, no network or storage APIs");
