import { afterEach, describe, expect, it, vi } from "vitest";
import { collect, parentPath } from "../src/collect";
import { translator } from "../src/i18n";
import type { Item } from "../src/types";
import { fakeRcmail, MAIL_PAGE, SETTINGS_PAGE, TASK_MENU } from "./fixtures";

function items(rc = fakeRcmail(), html = MAIL_PAGE): Item[] {
  document.body.innerHTML = html;
  return collect(rc, document, translator(rc));
}
const byId = (list: Item[], id: string) => list.find((i) => i.id === id);
const ids = (list: Item[], kind: Item["kind"]) => list.filter((i) => i.kind === kind).map((i) => i.id);

afterEach(() => {
  document.body.innerHTML = "";
});

describe("actions", () => {
  it("offers the enabled commands, the search field and Elastic's own buttons, in a fixed order", () => {
    expect(ids(items(), "action")).toEqual([
      "action:compose",
      "action:checkmail",
      "action:search",
      "action:theme",
      "action:about",
      "action:logout",
    ]);
  });

  it("hides commands that rcmail reports as disabled or does not know", () => {
    const rc = fakeRcmail({ commands: { compose: false, checkmail: false, logout: false } });
    expect(ids(items(rc), "action")).toEqual(["action:search", "action:theme", "action:about"]);
  });

  it("runs commands through rcmail.command()", () => {
    const rc = fakeRcmail();
    const list = items(rc);
    byId(list, "action:compose")!.run();
    byId(list, "action:logout")!.run();
    expect(rc.command.mock.calls).toEqual([["compose", undefined], ["logout", undefined]]);
  });

  it("switches dark mode and opens About with Elastic's own menu buttons", () => {
    const list = items();
    const theme = document.querySelector<HTMLElement>("#taskmenu a.theme")!;
    const about = document.querySelector<HTMLElement>("#taskmenu a.about")!;
    const clicks = vi.fn();
    theme.addEventListener("click", clicks);
    about.addEventListener("click", clicks);
    expect(byId(list, "action:theme")!.label).toBe("Dark mode");
    byId(list, "action:theme")!.run();
    byId(list, "action:about")!.run();
    expect(clicks).toHaveBeenCalledTimes(2);
  });

  it("labels the mode switch from Elastic's button, which names the mode it switches to", () => {
    document.body.innerHTML = TASK_MENU;
    const theme = document.querySelector<HTMLElement>("#taskmenu a.theme")!;
    theme.className = "theme light";
    theme.textContent = "";
    const rc = fakeRcmail();
    expect(byId(collect(rc, document, translator(rc)), "action:theme")!.label).toBe("Light mode");
  });

  it("focuses and selects the list's search field", () => {
    const list = items();
    const input = document.getElementById("mailsearchform") as HTMLInputElement;
    input.value = "minutes";
    byId(list, "action:search")!.run();
    expect(document.activeElement).toBe(input);
    expect(input.selectionStart).toBe(0);
    expect(input.selectionEnd).toBe(7);
  });

  it("falls back to the about command without Elastic's About button", () => {
    const rc = fakeRcmail();
    const list = items(rc, "<div></div>");
    byId(list, "action:about")!.run();
    expect(rc.command).toHaveBeenCalledWith("about", undefined);
    expect(byId(list, "action:theme")).toBeUndefined();
    expect(byId(list, "action:search")).toBeUndefined();
  });
});

describe("tasks", () => {
  it("lists the core tasks and plugin tasks from the menu, marks the current one, skips disabled ones", () => {
    const list = items();
    expect(ids(list, "task")).toEqual(["task:mail", "task:addressbook", "task:settings", "task:menu:Calendar"]);
    expect(byId(list, "task:mail")!.current).toBe(true);
    expect(byId(list, "task:addressbook")!.label).toBe("Contacts");
  });

  it("opens core tasks with rcmail.command() and plugin tasks with their own menu link", () => {
    const rc = fakeRcmail();
    const list = items(rc);
    byId(list, "task:addressbook")!.run();
    expect(rc.command).toHaveBeenCalledWith("addressbook", undefined);
    const calendar = document.querySelector<HTMLElement>("#taskmenu a.calendar")!;
    const click = vi.fn((event: Event) => event.preventDefault());
    calendar.addEventListener("click", click);
    byId(list, "task:menu:Calendar")!.run();
    expect(click).toHaveBeenCalledTimes(1);
  });
});

describe("folders", () => {
  it("lists rcmail.env.mailboxes in Roundcube's order, without virtual folders", () => {
    const list = items();
    expect(ids(list, "folder")).toEqual([
      "folder:INBOX",
      "folder:Drafts",
      "folder:Sent",
      "folder:Junk",
      "folder:Archive",
      "folder:Archive/2024",
      "folder:Shared/Team",
      "folder:Entw&APw-rfe",
    ]);
    expect(byId(list, "folder:INBOX")!.current).toBe(true);
    expect(byId(list, "folder:Archive/2024")).toMatchObject({ label: "2024", detail: "Archive" });
    expect(byId(list, "folder:Shared/Team")!.detail).toBe("Shared");
    expect(byId(list, "folder:Entw&APw-rfe")!.label).toBe("Entwürfe alt");
  });

  it("opens a folder with the list command and its IMAP name", () => {
    const rc = fakeRcmail();
    byId(items(rc), "folder:Archive/2024")!.run();
    expect(rc.command).toHaveBeenCalledWith("list", "Archive/2024");
  });

  it("keeps folder names as given (they are rendered as text, never as HTML)", () => {
    const name = '<img src=x onerror="alert(1)">';
    const rc = fakeRcmail({ env: { mailboxes: { INBOX: { id: "INBOX", name } }, mailboxes_list: ["INBOX"] } });
    expect(byId(items(rc), "folder:INBOX")!.label).toBe(name);
  });

  it("always offers Inbox: outside the mail task it opens the mail task (which shows Inbox)", () => {
    const rc = fakeRcmail({ env: { task: "addressbook", mailboxes: undefined, mailboxes_list: undefined } });
    const list = items(rc);
    expect(ids(list, "folder")).toEqual(["folder:INBOX"]);
    expect(byId(list, "folder:INBOX")!.current).toBe(false);
    byId(list, "folder:INBOX")!.run();
    expect(rc.command).toHaveBeenCalledWith("mail", undefined);
  });

  it("offers no folder list when the list command is disabled", () => {
    const rc = fakeRcmail({ commands: { list: false } });
    expect(ids(items(rc), "folder")).toEqual(["folder:INBOX"]);
  });

  it("builds parent paths from the display names", () => {
    const rc = fakeRcmail();
    expect(parentPath(rc, "Archive/2024")).toBe("Archive");
    expect(parentPath(rc, "INBOX")).toBeUndefined();
    expect(parentPath(fakeRcmail({ env: { delimiter: "" } }), "Archive/2024")).toBeUndefined();
  });
});

describe("settings", () => {
  it("offers the four core settings pages through switch-task outside the settings task", () => {
    const rc = fakeRcmail();
    const list = items(rc);
    expect(ids(list, "setting")).toEqual([
      "setting:preferences",
      "setting:folders",
      "setting:identities",
      "setting:responses",
    ]);
    byId(list, "setting:identities")!.run();
    expect(rc.command).toHaveBeenCalledWith("switch-task", "settings/identities");
  });

  it("reads the settings menu and the preference sections in the settings task", () => {
    const select = vi.fn();
    const rc = fakeRcmail({ env: { task: "settings", mailboxes: undefined } });
    rc.sections_list = { select };
    const list = items(rc, SETTINGS_PAGE);
    expect(list.filter((i) => i.kind === "setting").map((i) => i.label)).toEqual([
      "Preferences",
      "Folders",
      "Identities",
      "Filters",
      "User Interface",
      "Mailbox View",
    ]);
    expect(byId(list, "setting:settingstabpreferences")!.current).toBe(true);
    expect(byId(list, "section:mailbox")).toMatchObject({ current: true, detail: "Preferences" });
    byId(list, "section:general")!.run();
    expect(select).toHaveBeenCalledWith("general");
  });

  it("offers nothing that needs a disabled switch-task command", () => {
    const rc = fakeRcmail({ commands: { "switch-task": false } });
    expect(ids(items(rc), "setting")).toEqual([]);
  });
});

describe("labels", () => {
  it("uses Roundcube's labels, shows the key of a label that was not registered and fills $n", () => {
    const rc = fakeRcmail({ labels: { compose: "Verfassen", "lumen.palette_results": "Treffer: $n" } });
    delete rc.labels["checkmail"];
    const t = translator(rc);
    expect(t("compose")).toBe("Verfassen");
    expect(t("checkmail")).toBe("checkmail");
    expect(t("palette_results", { n: 3 })).toBe("Treffer: 3");
    expect(translator(null)("palette_title")).toBe("lumen.palette_title");
    const broken = translator({
      get_label: () => {
        throw new Error("no labels yet");
      },
    });
    expect(broken("inbox")).toBe("inbox");
  });
});
