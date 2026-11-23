// Parity: the compiler embedded in the customizer page (customizer/build.mjs, types stripped) and
// tokens/roundcube.ts run natively give the same files and the same replaced paths for every preset
// and every case in cases.json. With a built page as argument, its embedded compiler must also be
// the current one.
//   node --experimental-strip-types tests/parity/run.mjs [customizer/lumen-mail-customizer.html]
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { normalize } from "../../tokens/core.ts";
import { customizationFiles } from "../../tokens/roundcube.ts";

const root = fileURLToPath(new URL("../..", import.meta.url));
const script = execFileSync(process.execPath, ["--no-warnings", root + "customizer/build.mjs", "--core-only"], { encoding: "utf8" });
const sandbox = {};
vm.runInNewContext(script, sandbox);
const LT = sandbox.LumenTokens;

let failed = 0;
const page = process.argv[2];
if (page) {
  const html = readFileSync(page, "utf8");
  const embedded = html.match(/<script id="lumen-core">\n([\s\S]*?)\n<\/script>/)[1];
  if (embedded !== script) {
    failed++;
    console.error(`${page}: the embedded compiler is not the current one (rebuild the page)`);
  } else console.log(`ok ${page} embeds the current compiler`);
}

const preset = (n) => JSON.parse(readFileSync(`${root}tokens/presets/${n}.json`, "utf8"));
const docs = Object.fromEntries(["luminare", "graphite", "aurora", "contrast"].map((n) => [`preset:${n}`, preset(n)]));
Object.assign(docs, JSON.parse(readFileSync(`${root}tests/parity/cases.json`, "utf8")));
const defaults = preset("luminare");
for (const [name, doc] of Object.entries(docs)) {
  const a = normalize(doc, defaults);
  const b = LT.normalize(JSON.parse(JSON.stringify(doc)), JSON.parse(JSON.stringify(defaults)));
  if (JSON.stringify(a.errors) !== JSON.stringify(b.errors)) {
    failed++;
    console.error(`${name}: replaced paths differ\n  ts: ${a.errors}\n  js: ${b.errors}`);
  }
  const fa = customizationFiles(a.tokens);
  const fb = LT.customizationFiles(b.tokens);
  for (const file of Object.keys(fa)) {
    if (fa[file] !== fb[file]) {
      failed++;
      const x = fa[file].split("\n"), y = (fb[file] ?? "").split("\n");
      const i = x.findIndex((l, k) => l !== y[k]);
      console.error(`${name}/${file}: differs at line ${i + 1}\n  ts: ${x[i]}\n  js: ${y[i]}`);
    }
  }
  if (JSON.stringify(Object.keys(fa)) !== JSON.stringify(Object.keys(fb))) failed++;
  console.log(`ok ${name} (${a.errors.length} replaced)`);
}
// Things a customization must never contain, whatever the input.
for (const [name, doc] of Object.entries(docs)) {
  const files = customizationFiles(normalize(doc, defaults).tokens);
  for (const [file, text] of Object.entries(files)) {
    if (file === "lumen.tokens.json") continue; // data; the CSS is where it must be clean
    if (/<\/?\s*style|javascript:|\/etc\/passwd/i.test(text)) {
      failed++;
      console.error(`${name}/${file}: unsafe text survived`);
    }
  }
}
if (failed) {
  console.error(`${failed} difference(s)`);
  process.exit(1);
}
