// Label-fit check: logs in to a test copy of Roundcube once per skin (Lumen and Elastic) and
// language, opens the mail list, a message and its menus, compose, contacts and settings at five
// screen sizes, and lists every label in the task rail, the toolbars, the column headers and
// footers, the sidebar lists and the open menus whose text is cut off (an ellipsis, or text clipped
// by a box that hides overflow). Same test copy as capture.mjs: Roundcube with Lumen installed and
// the lumen_screenshots plugin (invented example mail, any password logs in). How to set it up:
// docs/development.md, "Screenshots" and "Label fit".
//
//   node scripts/screenshots/label-fit.mjs http://127.0.0.1:8080
//
// Prints a table per language and size with the labels each skin cuts. Exit code 1 if Lumen cuts
// any label in de_DE, or in another language a label that Elastic shows in full at the same size
// (the failures name the views); 3 if the run itself fails (page error, failed request, login); 0
// otherwise.
//
// Needs playwright-core and a Chromium, like capture.mjs:
//   PLAYWRIGHT_CORE   module to import (default "playwright-core"; a path to its index.mjs works)
//   CHROMIUM          browser executable (default: Playwright's own browser lookup)
//   LUMEN_FIT_LOCALES comma-separated Roundcube languages (default: see LOCALES)
//   LUMEN_FIT_SIZES   comma-separated sizes (default all five): desktop (1280 x 800), normal
//                     (1100 x 800), touch (1024 x 768), tablet (800 x 1280), phone (360 x 740)
//   LUMEN_FIT_SKINS   lumen,elastic (default both; the verdict needs both)
//   LUMEN_FIT_JSON    write every finding to this file
//   LUMEN_FIT_SHOTS   save a screenshot of every view into this folder
//   LUMEN_FIT_STRICT  the language that must have no cut label in Lumen (default de_DE)
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const [base] = process.argv.slice(2);
if (!base) {
  console.error("usage: node scripts/screenshots/label-fit.mjs <roundcube-url>");
  process.exit(2);
}

const LOCALES = ["en_US", "de_DE", "fr_FR", "es_ES", "it_IT", "nl_NL", "pl_PL", "ru_RU", "pt_BR", "ar"];
const SIZES = {
  desktop: { width: 1280, height: 800, mobile: false },
  normal: { width: 1100, height: 800, mobile: false },
  touch: { width: 1024, height: 768, mobile: false },
  tablet: { width: 800, height: 1280, mobile: false },
  phone: { width: 360, height: 740, mobile: true },
};
const list = (name, fallback) => (process.env[name] ? process.env[name].split(",").map((s) => s.trim()).filter(Boolean) : fallback);
const locales = list("LUMEN_FIT_LOCALES", LOCALES);
const sizes = list("LUMEN_FIT_SIZES", ["desktop", "normal", "touch", "tablet", "phone"]);
const skins = list("LUMEN_FIT_SKINS", ["lumen", "elastic"]);
const strict = process.env.LUMEN_FIT_STRICT || "de_DE";
const shots = process.env.LUMEN_FIT_SHOTS ? resolve(process.env.LUMEN_FIT_SHOTS) : null;
if (shots) mkdirSync(shots, { recursive: true });
for (const s of sizes) if (!SIZES[s]) { console.error(`unknown size ${s}`); process.exit(2); }
for (const s of skins) if (!["lumen", "elastic"].includes(s)) { console.error(`unknown skin ${s}`); process.exit(2); }

const { chromium } = await import(process.env.PLAYWRIGHT_CORE || "playwright-core");
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || undefined,
  args: [
    ...(process.getuid?.() === 0 ? ["--no-sandbox"] : []),
    "--disable-gpu", "--disable-dev-shm-usage", "--renderer-process-limit=1", "--js-flags=--max-old-space-size=128",
  ],
});

const problems = [];
const findings = []; // { skin, locale, size, view, area, text, cut }

// Runs in the page (and in every same-origin frame): the labels of the checked areas that are cut
// off. A box that hides overflow cuts at its padding edge; with text-overflow: ellipsis the
// ellipsis replaces the end of the line as soon as the line's content (the text and the padding of
// the inline boxes around it, such as span.inner) passes its content edge, even by a fraction of
// a pixel. Lines that a box hides vertically count too. Text in a box that scrolls does not, nor
// do visually hidden headings; a toolbar or rail button pushed wholly out of its bar counts.
function cutLabels() {
  const AREAS = [
    ["rail", "#taskmenu"],
    ["menu", ".popover, .ui-menu"],
    ["toolbar", ".menu.toolbar, .toolbar, .formbuttons"],
    ["header", "#layout > div > .header, #layout > div > .footer, .header:not(.ui-dialog-titlebar)"],
    ["sidebar", "#layout-sidebar .listing, #layout-sidebar .header, #settings-menu"],
  ];
  const EPS_X = 0.05;
  const EPS_Y = 3; // glyphs may overhang a tight line box by a little without being cut
  const seen = new Set();
  const out = [];
  const px = (cs, p) => parseFloat(cs[p]) || 0;
  const hidden = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") return true;
      if (e.classList.contains("voice") || e.classList.contains("sr-only")) return true;
      if (cs.clip !== "auto" && cs.position === "absolute") return true;
    }
    return false;
  };
  for (const [area, selector] of AREAS) {
    for (const root of document.querySelectorAll(selector)) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = node.nodeValue.replace(/\s+/gu, " ").trim();
        const el = node.parentElement;
        if (!text || !el || seen.has(el) || el.closest("script, style, select, option, textarea")) continue;
        if (hidden(el)) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        const lines = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
        if (!lines.length) continue;
        // horizontal extent of the line content: the text and its inline boxes with their padding
        const inline = [...lines];
        for (let e = el; e && getComputedStyle(e).display === "inline"; e = e.parentElement) {
          inline.push(...[...e.getClientRects()].filter((r) => r.width > 0));
        }
        let cut = 0;
        const gone = new Set(); // lines wholly outside a box that clips them
        for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
          const cs = getComputedStyle(e);
          const clipX = ["hidden", "clip"].includes(cs.overflowX);
          const clipY = ["hidden", "clip"].includes(cs.overflowY);
          if (!clipX && !clipY) continue;
          const r = e.getBoundingClientRect();
          const ellipsis = clipX && cs.textOverflow === "ellipsis";
          const b = {
            left: r.left + px(cs, "borderLeftWidth") + (ellipsis ? px(cs, "paddingLeft") : 0),
            right: r.right - px(cs, "borderRightWidth") - (ellipsis ? px(cs, "paddingRight") : 0),
            top: r.top + px(cs, "borderTopWidth"),
            bottom: r.bottom - px(cs, "borderBottomWidth"),
          };
          for (const l of lines) {
            if ((clipX && (l.right <= b.left || l.left >= b.right)) || (clipY && (l.bottom <= b.top || l.top >= b.bottom))) {
              gone.add(l);
            } else if (clipY) {
              const over = Math.max(l.bottom - b.bottom, b.top - l.top);
              if (over > EPS_Y) cut = Math.max(cut, over);
            }
          }
          if (clipX) {
            for (const l of inline) {
              const over = Math.max(l.right - b.right, b.left - l.left);
              if (over > EPS_X && over < l.width) cut = Math.max(cut, over);
            }
          }
        }
        if (gone.size && gone.size < lines.length) {
          cut = Math.max(cut, ...[...gone].map((l) => l.height)); // some lines shown, others hidden
        } else if (gone.size) {
          // wholly outside: counts only for buttons of the rail and the toolbars (anything else
          // that is wholly clipped is hidden on purpose or scrolled away)
          if (!(area === "rail" || area === "toolbar") || !el.closest("a, button")) continue;
          cut = Math.max(...lines.map((l) => l.width));
        }
        seen.add(el);
        if (cut) out.push({ area, text, cut: Math.round(cut * 10) / 10 });
      }
    }
  }
  return out;
}

// Requests in flight per page (Playwright's "networkidle" state does not come back after some of
// Roundcube's in-page navigations, such as opening a message on a phone).
const inflight = new WeakMap();
function track(page) {
  inflight.set(page, 0);
  page.on("request", () => inflight.set(page, inflight.get(page) + 1));
  for (const done of ["requestfinished", "requestfailed"]) {
    page.on(done, () => inflight.set(page, Math.max(0, inflight.get(page) - 1)));
  }
}

// No request for 500 ms, Roundcube idle (no request running, no loading message) and every web
// font loaded.
async function settled(page) {
  const until = Date.now() + 20000;
  for (let quiet = 0; quiet < 500 && Date.now() < until; ) {
    await page.waitForTimeout(100);
    quiet = inflight.get(page) ? 0 : quiet + 100;
  }
  await page.waitForFunction(() => {
    const rc = window.rcmail;
    return document.fonts.status === "loaded" && (!rc || (!rc.busy && !document.querySelector("#messagestack .loading")));
  });
}

async function measure(page, ctx, view) {
  await settled(page);
  for (const frame of page.frames()) {
    let found;
    try {
      found = await frame.evaluate(cutLabels);
    } catch {
      continue; // a frame that went away or is not same-origin
    }
    const where = frame === page.mainFrame() ? view : `${view} (frame)`;
    for (const f of found) findings.push({ ...ctx, view: where, ...f });
  }
  if (shots) {
    await page.screenshot({ path: join(shots, `${ctx.skin}-${ctx.locale}-${ctx.size}-${view}.png`), animations: "disabled", caret: "hide" });
  }
}

async function goto(page, query) {
  await page.goto(`${base}/?${query}`, { waitUntil: "load" });
  await settled(page);
}

async function login(page, user) {
  await page.goto(base + "/", { waitUntil: "load" });
  await page.fill("#rcmloginuser", user);
  await page.fill("#rcmloginpwd", "example");
  await Promise.all([page.waitForURL(/_task=mail/u), page.click("#rcmloginsubmit")]);
  await settled(page);
}

// The user's skin, through the preferences form like a person would choose it. Saving a new skin
// reloads the page, so wait for the save and then load the mail view afresh.
async function chooseSkin(page, skin) {
  if (await page.evaluate(() => window.rcmail.env.skin) === skin) return;
  await goto(page, "_task=settings&_action=edit-prefs&_section=general&_framed=1");
  await page.check(`input[name="_skin"][value="${skin}"]`);
  await Promise.all([
    page.waitForResponse((r) => r.request().method() === "POST" && /_action=save-prefs/u.test(r.request().postData() || "")),
    page.evaluate(() => window.rcmail.command("save")),
  ]);
  await settled(page);
  await goto(page, "_task=mail&_mbox=INBOX");
  const now = await page.evaluate(() => window.rcmail.env.skin);
  if (now !== skin) throw new Error(`skin is ${now}, not ${skin}`);
}

// Opens a popover through the button that owns it, measures, closes it again.
async function withPopover(page, ctx, view, button) {
  const link = page.locator(button).filter({ visible: true }).first();
  if (!(await link.count())) return false;
  await link.click();
  await page.locator(".popover:visible").first().waitFor({ timeout: 5000 });
  await measure(page, ctx, view);
  const close = page.locator("#layout-menu .popover-header a.cancel").filter({ visible: true });
  if (await close.count()) await close.first().click();
  else await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  await page.locator(".popover:visible").first().waitFor({ state: "hidden", timeout: 5000 }).catch(() => {});
  return true;
}

async function checkSize(page, ctx, phone) {
  await goto(page, "_task=mail&_mbox=INBOX");
  await page.waitForFunction(() => document.querySelectorAll("#messagelist tbody tr").length >= 5);
  await measure(page, ctx, "mail");
  if (phone) {
    await withPopover(page, ctx, "mail-taskmenu", "a.task-menu-button");
    await page.locator("#layout-list > .header a.back-sidebar-button").click();
    await page.locator("#folderlist-content").waitFor();
    await measure(page, ctx, "mail-folders");
    await page.locator("#folderlist-content li.inbox > a").first().click();
    await page.locator("#messagelist").waitFor();
  }
  await withPopover(page, ctx, "mail-folder-menu", "#layout-sidebar .header a.toolbar-button, #layout-sidebar .header a[data-popup]");

  // a message with an attachment ("Agenda" in the English and the German example data)
  await page.locator("#messagelist tbody tr", { hasText: "Agenda" }).first().click();
  await page.frameLocator("#messagecontframe").locator("#messagebody").waitFor();
  await measure(page, ctx, "message");
  if (phone) await withPopover(page, ctx, "message-toolbar", "#layout-content > .header a.toolbar-menu-button");
  for (const [name, button] of [["more", "a.more"], ["mark", "a.flag, a.markmessage"], ["reply-all", "a.reply-all + a.dropdown"], ["forward", "a.forward + a.dropdown"]]) {
    if (!phone) await withPopover(page, ctx, `message-${name}-menu`, `#layout-content > .header ${button}`);
  }

  await goto(page, "_task=mail&_action=compose");
  await page.locator("#compose-subject").waitFor();
  await measure(page, ctx, "compose");
  if (phone) await withPopover(page, ctx, "compose-toolbar", "#layout-content > .header a.toolbar-menu-button");

  await goto(page, "_task=addressbook");
  await measure(page, ctx, "contacts");
  if (phone) await withPopover(page, ctx, "contacts-toolbar", "#layout-content > .header a.toolbar-menu-button, #layout-list > .header a.toolbar-menu-button");

  for (const action of ["preferences", "folders", "identities", "responses"]) {
    await goto(page, `_task=settings&_action=${action}`);
    await measure(page, ctx, `settings-${action}`);
  }
}

for (const skin of skins) {
  for (const locale of locales) {
    const device = sizes.filter((s) => !SIZES[s].mobile);
    const mobile = sizes.filter((s) => SIZES[s].mobile);
    for (const group of [device, mobile]) {
      if (!group.length) continue;
      const first = SIZES[group[0]];
      const context = await browser.newContext({
        viewport: { width: first.width, height: first.height }, isMobile: first.mobile, hasTouch: first.mobile,
        deviceScaleFactor: 1, locale: locale.replace("_", "-"), timezoneId: "UTC",
      });
      const page = await context.newPage();
      track(page);
      const name = `${skin} ${locale}`;
      page.on("pageerror", (e) => problems.push(`${name}: page error: ${e.message}`));
      page.on("response", (r) => {
        if (r.status() >= 400) problems.push(`${name}: HTTP ${r.status()} ${r.url().replace(/^https?:\/\/[^/]+/u, "")}`);
      });
      try {
        await login(page, `${locale.replace("_", "").toLowerCase()}${skin[0]}@example.com`); // dedel@, arl@ ...
        await chooseSkin(page, skin);
        const lang = await page.evaluate(() => window.rcmail.env.locale);
        if (lang !== locale) throw new Error(`Roundcube chose ${lang} for ${locale}`);
        for (const size of group) {
          const s = SIZES[size];
          await page.setViewportSize({ width: s.width, height: s.height });
          await checkSize(page, { skin, locale, size }, s.mobile);
        }
      } catch (e) {
        problems.push(`${name} ${group.join("+")}: ${e.message.split("\n")[0]}`);
      } finally {
        await context.close();
      }
      console.error(`checked ${skin} ${locale} ${group.join(", ")}`);
    }
  }
}
await browser.close();

// One finding per label: a label cut in several views (the rail on every page) counts once, with
// the views listed.
const key = (f) => `${f.area}|${f.text}`;
const labels = (rows) => {
  const map = new Map();
  for (const f of rows) {
    const k = key(f);
    if (!map.has(k)) map.set(k, { area: f.area, text: f.text, cut: f.cut, views: new Set() });
    const row = map.get(k);
    row.cut = Math.max(row.cut, f.cut);
    row.views.add(f.view);
  }
  return [...map.values()].map((r) => ({ ...r, views: [...r.views] }));
};
const failures = [];
const table = [];
for (const locale of locales) {
  for (const size of sizes) {
    const pick = (skin) => labels(findings.filter((f) => f.skin === skin && f.locale === locale && f.size === size));
    const lumen = pick("lumen");
    const elastic = pick("elastic");
    const elasticKeys = new Set(elastic.map(key));
    const worse = lumen.filter((f) => !elasticKeys.has(key(f)));
    table.push({ locale, size, elastic, lumen, worse });
    if (!skins.includes("lumen")) continue;
    const say = (f) => `"${f.text}" (${f.area}, ${f.cut}px; ${f.views.join(", ")})`;
    if (locale === strict) {
      failures.push(...lumen.map((f) => `${locale} ${size}: Lumen cuts ${say(f)}`));
    } else if (skins.includes("elastic")) {
      failures.push(...worse.map((f) => `${locale} ${size}: Lumen cuts ${say(f)}, Elastic does not`));
    }
  }
}

const cell = (rows) => rows.map((f) => f.text).join("; ") || "-";
console.log("| Language | Size | Elastic | Lumen | Cut by Elastic | Cut by Lumen |");
console.log("|---|---|---:|---:|---|---|");
for (const row of table) {
  console.log(`| ${row.locale} | ${row.size} | ${row.elastic.length} | ${row.lumen.length} | ${cell(row.elastic)} | ${cell(row.lumen)} |`);
}
if (process.env.LUMEN_FIT_JSON) {
  writeFileSync(process.env.LUMEN_FIT_JSON, JSON.stringify({ locales, sizes, skins, table, findings, problems, failures }, null, 2) + "\n");
}
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(3);
}
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
