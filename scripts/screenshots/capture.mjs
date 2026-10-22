// Capture the README screenshots of the Lumen skin (docs/screenshots/) from a scratch copy of
// Roundcube that runs Lumen with the lumen_screenshots plugin: invented example mail, nothing
// real. How to set that up: docs/development.md, "Screenshots".
//
//   node scripts/screenshots/capture.mjs http://127.0.0.1:8080 docs/screenshots
//
// Needs playwright-core and a Chromium (not dependencies of this repository):
//   PLAYWRIGHT_CORE  module to import (default "playwright-core"; a path to its index.mjs works)
//   CHROMIUM         browser executable (default: Playwright's own browser lookup)
//   LUMEN_SHOTS      comma-separated view names (e.g. lumen-login) to take only those
// Each view is checked before it is saved (skin, colour mode, font, content); any page error,
// failed request or failed check ends the run with exit code 1.
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

const [base, outArg] = process.argv.slice(2);
if (!base || !outArg) {
  console.error("usage: node scripts/screenshots/capture.mjs <roundcube-url> <output-folder>");
  process.exit(2);
}
const out = resolve(outArg);
mkdirSync(out, { recursive: true });

const { chromium } = await import(process.env.PLAYWRIGHT_CORE || "playwright-core");
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || undefined,
  args: [
    ...(process.getuid?.() === 0 ? ["--no-sandbox"] : []),
    "--disable-gpu", "--disable-dev-shm-usage", "--renderer-process-limit=1", "--js-flags=--max-old-space-size=128",
  ],
});

const problems = [];
const DESKTOP = { viewport: { width: 1280, height: 800 } };
const PHONE = { viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true };
// message: an HTML message; plainMessage: a text-only one (Elastic shows HTML bodies on white in dark mode)
const ENGLISH = {
  locale: "en-US", user: "alex@example.com",
  message: "Agenda for the planning day", plainMessage: "Draft: release notes for version 2.4",
};

async function open(name, { device, dark, lang }) {
  const context = await browser.newContext({
    ...device, deviceScaleFactor: 1, colorScheme: dark ? "dark" : "light", locale: lang.locale, timezoneId: "UTC",
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => problems.push(`${name}: page error: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") problems.push(`${name}: console: ${m.text()}`); });
  page.on("response", (r) => {
    if (r.status() >= 400) problems.push(`${name}: HTTP ${r.status()} ${r.url().replace(/^https?:\/\/[^/]+/u, "")}`);
  });
  page.on("request", (r) => {
    if (!r.url().startsWith(base) && !r.url().startsWith("data:") && !r.url().startsWith("about:")) {
      problems.push(`${name}: request outside the test server: ${r.url()}`);
    }
  });
  return { context, page };
}

async function login(page, lang) {
  await page.goto(base + "/", { waitUntil: "networkidle" });
  await page.fill("#rcmloginuser", lang.user);
  await page.fill("#rcmloginpwd", "example");
  await Promise.all([page.waitForURL(/_task=mail/u), page.click("#rcmloginsubmit")]);
  await settled(page);
  await page.waitForFunction(() => document.querySelectorAll("#messagelist tbody tr").length >= 10);
}

// Roundcube idle (no request running, no loading message) and every web font loaded.
async function settled(page) {
  await page.waitForLoadState("networkidle");
  await page.waitForFunction(() => {
    const rc = window.rcmail;
    return document.fonts.status === "loaded" && (!rc || (!rc.busy && !document.querySelector("#messagestack .loading")));
  });
  await page.waitForTimeout(300);
}

async function openMessage(page, subject) {
  await page.locator("#messagelist tbody tr", { hasText: subject }).first().click();
  const frame = page.frameLocator("#messagecontframe");
  await frame.locator("#messagebody").waitFor();
  await frame.locator("#attachment-list li").first().waitFor();
  await settled(page);
  await page.mouse.move(205, 700); // empty folder pane: no hover effect anywhere
}

async function check(page, name, { dark }) {
  const facts = await page.evaluate(() => ({
    skin: window.rcmail ? window.rcmail.env.skin : document.querySelector('link[href*="skins/lumen/"]') ? "lumen" : null,
    dark: document.documentElement.classList.contains("dark-mode"),
    sora: [...document.fonts].some((f) => /Sora/u.test(f.family) && f.status === "loaded"),
    hScroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  }));
  const fail = [];
  if (facts.skin !== "lumen") fail.push(`skin ${facts.skin}`);
  if (facts.dark !== dark) fail.push(`dark mode ${facts.dark}`);
  if (!facts.sora) fail.push("Sora not loaded");
  if (facts.hScroll) fail.push("horizontal scroll");
  if (fail.length) problems.push(`${name}: ${fail.join(", ")}`);
  return facts;
}

async function shot(page, name, options) {
  const facts = await check(page, name, options);
  await page.screenshot({ path: join(out, `${name}.png`), animations: "disabled", caret: "hide" });
  console.log(`${name}.png`, JSON.stringify(facts));
}

const views = [
  ["lumen-login", { device: DESKTOP, dark: false, lang: ENGLISH }, async (page) => {
    await page.goto(base + "/", { waitUntil: "networkidle" });
    await settled(page);
  }],
  ["lumen-mail-dark", { device: DESKTOP, dark: true, lang: ENGLISH }, async (page) => {
    await login(page, ENGLISH);
    await openMessage(page, ENGLISH.plainMessage);
  }],
  ["lumen-command-palette", { device: DESKTOP, dark: false, lang: ENGLISH }, async (page) => {
    await login(page, ENGLISH);
    await openMessage(page, ENGLISH.message);
    await page.keyboard.press("Control+k");
    const dialog = page.locator("#lumen-palette").locator('[role="dialog"]');
    await dialog.waitFor();
    await page.keyboard.type("se");
    await page.waitForTimeout(300);
  }],
  ["lumen-settings-phone-dark", { device: PHONE, dark: true, lang: ENGLISH }, async (page) => {
    await login(page, ENGLISH);
    await page.goto(base + "/?_task=settings&_action=preferences", { waitUntil: "networkidle" });
    await settled(page);
    await page.locator("#sections-table tr", { hasText: "User Interface" }).first().click();
    const frame = page.frameLocator("#preferences-frame");
    const skins = frame.locator("legend", { hasText: "Interface skin" });
    await skins.waitFor();
    await settled(page);
    // down to the skin chooser, with Lumen selected, starting at a whole row; no focus ring
    await skins.evaluate((legend) => {
      const doc = legend.ownerDocument;
      doc.activeElement?.blur();
      const row = doc.querySelector('select[name="_date_format"]')?.closest("tr");
      (row || legend).scrollIntoView({ block: "start" });
    });
    if (!(await frame.locator('input[name="_skin"][value="lumen"]').isChecked())) {
      throw new Error("Lumen is not the selected skin");
    }
    await page.waitForTimeout(300);
  }],
];

const only = process.env.LUMEN_SHOTS ? process.env.LUMEN_SHOTS.split(",") : null;
for (const [name, options, prepare] of views) {
  if (only && !only.includes(name)) continue;
  const { context, page } = await open(name, options);
  try {
    await prepare(page);
    await shot(page, name, options);
  } catch (e) {
    problems.push(`${name}: ${e.message.split("\n")[0]}`);
  } finally {
    await context.close();
  }
}
await browser.close();

if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}
