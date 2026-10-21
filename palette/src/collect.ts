// What the palette offers, read from Roundcube each time it opens. Nothing is fetched and
// nothing is stored: every item comes from the page and from rcmail, so it always matches what
// the signed-in user can do right now.
//
//   Actions   compose, check mail, search, dark/light mode, about, logout
//   Go to     the tasks (mail, contacts, settings) and tasks that plugins add to the menu
//   Folders   rcmail.env.mailboxes in the mail task; Inbox always
//   Settings  the settings menu and preference sections when they are on the page, otherwise
//             the four core settings pages
//
// Every item runs through Roundcube itself: rcmail.command() for commands that rcmail reports
// as enabled (rcmail.commands), a click on Elastic's own button where the skin implements the
// action (dark mode, about, plugin tasks, settings tabs). Unsaved-compose checks, busy states
// and plugin hooks therefore work exactly as with Roundcube's own buttons.

import type { Translate } from "./i18n";
import type { Item, Rcmail } from "./types";

/** The four settings pages every Roundcube has (settings/<action>). */
export const CORE_SETTINGS = ["preferences", "folders", "identities", "responses"] as const;

/** The search fields of Elastic's mail, contacts and folder lists. */
export const SEARCH_INPUTS = "#mailsearchform, #searchform, #foldersearch";

export function text(node: Node | null | undefined): string {
  return node ? String(node.textContent ?? "").replace(/\s+/gu, " ").trim() : "";
}

function usable(el: Element): boolean {
  return !el.matches(".disabled, [aria-disabled='true'], [hidden]");
}

/** "Archive / 2024" for the folder "Archive/2024/Q1", with each level's display name. */
export function parentPath(rc: Rcmail, id: string): string | undefined {
  const delimiter = rc.env.delimiter;
  const boxes = rc.env.mailboxes ?? {};
  if (!delimiter) return undefined;
  const parts = id.split(delimiter);
  const names: string[] = [];
  for (let i = 1; i < parts.length; i += 1) {
    const parentId = parts.slice(0, i).join(delimiter);
    names.push(String(boxes[parentId]?.name ?? parts[i - 1]));
  }
  return names.length ? names.join(" / ") : undefined;
}

export function collect(rc: Rcmail, doc: Document, t: Translate): Item[] {
  const env = rc.env ?? {};
  const task = env.task;
  const items: Item[] = [];
  const seen = new Set<string>();
  const on = (command: string) => Boolean(rc.commands?.[command]);
  const command = (name: string, props?: unknown) => () => {
    rc.command(name, props);
  };
  const add = (item: Item) => {
    if (!item.label || seen.has(item.id)) return;
    seen.add(item.id);
    items.push(item);
  };
  const click = (el: HTMLElement) => () => el.click();

  // Actions
  const actions = t("palette_group_actions");
  if (on("compose")) add({ id: "action:compose", kind: "action", label: t("compose"), group: actions, run: command("compose") });
  if (on("checkmail")) {
    add({ id: "action:checkmail", kind: "action", label: t("checkmail"), group: actions, run: command("checkmail") });
  }
  const search = doc.querySelector<HTMLInputElement>(SEARCH_INPUTS);
  if (search && !search.disabled) {
    add({
      id: "action:search",
      kind: "action",
      label: t("search"),
      group: actions,
      run: () => {
        search.focus();
        search.select();
      },
    });
  }
  const theme = doc.querySelector<HTMLElement>("#taskmenu a.theme");
  if (theme && usable(theme)) {
    const label = text(theme) || t(theme.classList.contains("light") ? "lightmode" : "darkmode");
    add({ id: "action:theme", kind: "action", label, group: actions, run: click(theme) });
  }
  const about = doc.querySelector<HTMLElement>("#taskmenu a.about");
  if (about && usable(about)) {
    add({ id: "action:about", kind: "action", label: text(about) || t("about"), group: actions, run: click(about) });
  } else if (on("about")) {
    add({ id: "action:about", kind: "action", label: t("about"), group: actions, run: command("about") });
  }
  if (on("logout")) add({ id: "action:logout", kind: "action", label: t("logout"), group: actions, run: command("logout") });

  // Go to: the core tasks, then tasks that plugins add to Elastic's menu
  const tasks = t("palette_group_tasks");
  const core: [string, "mail" | "contacts" | "settings"][] = [["mail", "mail"], ["addressbook", "contacts"], ["settings", "settings"]];
  for (const [name, label] of core) {
    if (on(name)) add({ id: `task:${name}`, kind: "task", label: t(label), group: tasks, current: task === name, run: command(name) });
  }
  for (const a of doc.querySelectorAll<HTMLElement>("#taskmenu > a")) {
    if (a.matches(".mail, .contacts, .settings, .compose") || !usable(a)) continue;
    const label = text(a);
    add({ id: `task:menu:${label}`, kind: "task", label, group: tasks, current: a.classList.contains("selected"), run: click(a) });
  }

  // Folders
  const folders = t("palette_group_folders");
  const boxes = task === "mail" && on("list") ? env.mailboxes : undefined;
  if (boxes) {
    const order = Array.isArray(env.mailboxes_list) ? env.mailboxes_list : Object.keys(boxes);
    for (const id of order) {
      const box = boxes[id];
      if (!box || box.virtual) continue;
      add({
        id: `folder:${id}`,
        kind: "folder",
        label: String(box.name ?? id),
        detail: parentPath(rc, id),
        group: folders,
        current: env.mailbox === id,
        run: command("list", id),
      });
    }
  }
  if (!seen.has("folder:INBOX")) {
    // Without the folder list (contacts, settings, compose) only Inbox is known for certain.
    const run = task === "mail" && on("list") ? command("list", "INBOX") : on("mail") ? command("mail") : null;
    if (run) add({ id: "folder:INBOX", kind: "folder", label: t("inbox"), group: folders, current: task === "mail" && env.mailbox === "INBOX", run });
  }

  // Settings
  const settings = t("palette_group_settings");
  const tabs = doc.querySelectorAll<HTMLElement>("#settings-menu a");
  for (const a of tabs) {
    const li = a.closest("li");
    if (!usable(a) || (li && !usable(li))) continue;
    const label = text(a);
    add({ id: `setting:${li?.id || label}`, kind: "setting", label, group: settings, current: Boolean(li?.classList.contains("selected")), run: click(a) });
  }
  if (tabs.length === 0 && on("switch-task")) {
    for (const action of CORE_SETTINGS) {
      add({ id: `setting:${action}`, kind: "setting", label: t(action), group: settings, run: command("switch-task", `settings/${action}`) });
    }
  }
  const sections = rc.sections_list;
  if (sections && typeof sections.select === "function") {
    const preferences = t("preferences");
    for (const row of doc.querySelectorAll<HTMLElement>("#sections-table tr[id^='rcmrow']")) {
      const id = row.id.slice("rcmrow".length);
      add({
        id: `section:${id}`,
        kind: "setting",
        label: text(row),
        detail: preferences,
        group: settings,
        current: row.classList.contains("selected"),
        run: () => sections.select?.(id),
      });
    }
  }
  return items;
}
