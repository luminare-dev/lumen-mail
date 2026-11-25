// Build the self-contained customizer page (Node.js 22.13+, no packages):
//
//   node customizer/build.mjs --out customizer/lumen-mail-customizer.html
//
// The page is one HTML file with everything inline: the token compiler (tokens/core.ts and
// tokens/roundcube.ts with the types stripped), the four presets, the mock webmail
// (customizer/mock.html and mock.css, our own markup, no Roundcube or Elastic file), the Sora font
// and the Luminare logos. It makes no network request. CI rebuilds it and fails when the committed
// page is not current.
//
// --core-only prints just the compiler script (tests/parity runs it in a sandbox).

import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PRESETS = ["luminare", "graphite", "aurora", "contrast"];

/** core.ts + roundcube.ts as one classic script that defines `LumenTokens`. */
export function coreScript() {
  const names = [];
  const parts = ["core.ts", "roundcube.ts"].map((file) => {
    let js = stripTypeScriptTypes(readFileSync(join(root, "tokens", file), "utf8"), { mode: "strip" });
    js = js.replace(/^import [^;]*;\s*$/gm, "");
    js = js.replace(/^export (function|const|let) ([A-Za-z0-9_]+)/gm, (_m, kind, name) => {
      names.push(name);
      return `${kind} ${name}`;
    });
    if (/^\s*export\b/m.test(js)) throw new Error(`${file}: an export form the build does not handle`);
    return `// ---- tokens/${file} (types stripped) ----\n${js}`;
  });
  return (
    "(function (root) {\n\"use strict\";\n" + parts.join("\n") +
    `\nroot.LumenTokens = { ${names.join(", ")} };\n})(typeof window !== "undefined" ? window : globalThis);\n`
  );
}

function dataUrl(path, type) {
  return `data:${type};base64,${readFileSync(path).toString("base64")}`;
}

function json(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

function build(out) {
  const images = join(root, "skin", "images");
  const font = dataUrl(join(root, "skin", "fonts", "Sora-Variable.woff"), "font/woff");
  const brand = {};
  for (const name of ["luminare-mark.svg", "luminare-mark-brand-deep.svg", "luminare-lockup-horizontal-dark.svg",
    "luminare-lockup-compact-dark.svg"]) {
    brand[`/images/${name}`] = dataUrl(join(images, name), "image/svg+xml");
  }
  brand["/images/luminare-favicon.ico"] = dataUrl(join(images, "luminare-favicon.ico"), "image/x-icon");
  const embedded = {
    css:
      `@font-face { font-family: "Sora"; font-weight: 100 800; font-display: swap; src: url("${font}") format("woff"); }\n` +
      readFileSync(join(root, "customizer", "mock.css"), "utf8"),
    brand,
  };
  const presets = Object.fromEntries(
    PRESETS.map((n) => [n, JSON.parse(readFileSync(join(root, "tokens", "presets", `${n}.json`), "utf8"))]),
  );
  const version = readFileSync(join(root, "version.txt"), "utf8").trim();
  const page = readFileSync(join(root, "customizer", "template.html"), "utf8")
    .replace("<!--@MOCK@-->", () => readFileSync(join(root, "customizer", "mock.html"), "utf8"))
    .replace("@VERSION@", () => version)
    .replace("/*@PRESETS@*/{}", () => json(presets))
    .replace("/*@ASSETS@*/{}", () => json(embedded))
    .replace("/*@CORE@*/", () => coreScript());
  if (/@[A-Z]+@/.test(page)) throw new Error("template.html: a placeholder was not filled");
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, page);
  console.log(`${out}  ${page.length} bytes`);
}

const argv = process.argv.slice(2);
if (argv.includes("--core-only")) {
  process.stdout.write(coreScript());
} else {
  const i = argv.indexOf("--out");
  if (i < 0 || !argv[i + 1]) {
    console.error("usage: customizer/build.mjs --out FILE");
    process.exit(2);
  }
  build(argv[i + 1]);
}
