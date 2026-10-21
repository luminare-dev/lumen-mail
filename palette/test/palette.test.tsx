import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Palette } from "../src/Palette";
import { inEditor, isToggleKey } from "../src/page";
import { fakeRcmail, MAIL_PAGE, type FakeRcmail } from "./fixtures";

function setup(rc: FakeRcmail = fakeRcmail(), trigger: HTMLElement | null = null) {
  const user = userEvent.setup();
  const view = render(<Palette rc={rc} trigger={trigger} />);
  return { rc, user, view };
}

const open = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.keyboard("{Control>}k{/Control}");
  return screen.getByRole("dialog");
};
const input = () => screen.getByRole("combobox");
const options = () => screen.queryAllByRole("option");
const selected = () => options().find((o) => o.getAttribute("aria-selected") === "true");

beforeEach(() => {
  document.documentElement.setAttribute("lang", "en");
  document.documentElement.removeAttribute("dir");
  document.documentElement.className = "";
  document.body.innerHTML = MAIL_PAGE;
});

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

describe("opening and closing", () => {
  it("renders nothing until Ctrl+K, then a labelled modal dialog with the focus in the search field", async () => {
    const { user } = setup();
    expect(screen.queryByRole("dialog")).toBeNull();
    const dialog = await open(user);
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBe(dialog);
    expect(document.activeElement).toBe(input());
    expect(options().length).toBeGreaterThan(10);
  });

  it("toggles closed with the same shortcut; Meta+K does nothing outside Apple platforms", async () => {
    const { user } = setup();
    await user.keyboard("{Meta>}k{/Meta}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await open(user);
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("uses Cmd+K on Apple platforms and follows the physical K key on non-Latin layouts", () => {
    const base = { ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, key: "k", code: "KeyK" };
    expect(isToggleKey({ ...base, metaKey: true }, true)).toBe(true);
    expect(isToggleKey({ ...base, ctrlKey: true }, true)).toBe(false);
    expect(isToggleKey({ ...base, ctrlKey: true }, false)).toBe(true);
    expect(isToggleKey({ ...base, ctrlKey: true, shiftKey: true }, false)).toBe(false);
    expect(isToggleKey({ ...base, ctrlKey: true, key: "л" }, false)).toBe(true);
    expect(isToggleKey({ ...base, ctrlKey: true, key: "t" }, false)).toBe(false);
  });

  it("leaves Ctrl+K to text areas, contenteditable elements and TinyMCE, but not to input fields", async () => {
    const { user } = setup();
    const area = document.createElement("textarea");
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    editable.tabIndex = 0;
    const tox = document.createElement("div");
    tox.className = "tox";
    const toxButton = document.createElement("button");
    tox.append(toxButton);
    document.body.append(area, editable, tox);
    for (const el of [area, editable, toxButton]) {
      el.focus();
      await user.keyboard("{Control>}k{/Control}");
      expect(screen.queryByRole("dialog")).toBeNull();
    }
    document.getElementById("subject")!.focus();
    await open(user);
  });

  it("stays closed while a Roundcube modal dialog is open, so the dialog keeps its keys", async () => {
    const trigger = document.createElement("a");
    trigger.href = "#";
    document.body.append(trigger);
    const { user } = setup(fakeRcmail(), trigger);
    const field = document.createElement("input");
    const dialog = document.createElement("div");
    dialog.className = "ui-dialog";
    dialog.append(field);
    const overlay = document.createElement("div");
    overlay.className = "ui-widget-overlay";
    document.body.append(dialog, overlay);
    // what jQuery UI does for a modal dialog: focus anywhere else goes back into it
    const refocus = (event: FocusEvent) => {
      if (!(event.target as Element).closest?.(".ui-dialog")) field.focus();
    };
    document.addEventListener("focusin", refocus);
    try {
      field.focus();
      await user.keyboard("{Control>}k{/Control}");
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(document.activeElement).toBe(field);
      fireEvent.click(trigger);
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(trigger.getAttribute("aria-expanded")).toBe("false");
    } finally {
      document.removeEventListener("focusin", refocus);
    }
    overlay.remove();
    dialog.remove();
    expect(await open(user)).toBeTruthy();
  });

  it("closes with Escape and gives the focus back", async () => {
    const { user } = setup();
    const subject = document.getElementById("subject")!;
    subject.focus();
    await open(user);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(subject);
  });

  it("closes with the close button and on a click on the backdrop, not on the dialog", async () => {
    const { user } = setup();
    await open(user);
    await user.click(screen.getByRole("button", { name: "Close (Esc)" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    const dialog = await open(user);
    fireEvent.mouseDown(dialog);
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.mouseDown(dialog.parentElement!);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps Tab and Shift+Tab inside the dialog", async () => {
    const { user } = setup();
    await open(user);
    const close = screen.getByRole("button", { name: "Close (Esc)" });
    await user.tab();
    expect(document.activeElement).toBe(close);
    await user.tab();
    expect(document.activeElement).toBe(input());
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(close);
  });

  it("brings the focus back into the dialog when something moves it out", async () => {
    const { user } = setup();
    await open(user);
    act(() => document.getElementById("subject")!.focus());
    expect(document.activeElement).toBe(input());
  });
});

describe("listbox", () => {
  it("is a combobox controlling a listbox, with aria-activedescendant on the highlighted option", async () => {
    const { user } = setup();
    await open(user);
    const listbox = screen.getByRole("listbox", { name: "Command palette" });
    expect(input().getAttribute("aria-controls")).toBe(listbox.id);
    expect(input().getAttribute("aria-activedescendant")).toBe(options()[0]!.id);
    expect(selected()).toBe(options()[0]);
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(input().getAttribute("aria-activedescendant")).toBe(options()[2]!.id);
    expect(selected()).toBe(options()[2]);
    await user.keyboard("{ArrowUp}{ArrowUp}{ArrowUp}");
    expect(selected()).toBe(options()[options().length - 1]);
  });

  it("filters while typing, shows the group, and runs the highlighted item with Enter", async () => {
    const { user, rc } = setup();
    await open(user);
    await user.type(input(), "2024");
    expect(options()).toHaveLength(1);
    expect(options()[0]!.textContent).toContain("Archive");
    expect(within(options()[0]!).getByText("Folders", { selector: ".group" })).toBeTruthy();
    await user.keyboard("{Enter}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(rc.command).toHaveBeenCalledWith("list", "Archive/2024");
  });

  it("names each option with its group and marks the current item", async () => {
    const { user } = setup();
    await open(user);
    const inbox = screen.getByRole("option", { name: "Inbox, current, Folders" });
    expect(inbox.querySelector(".badge")?.textContent).toBe("current");
  });

  it("runs an item on click", async () => {
    const { user, rc } = setup();
    await open(user);
    await user.click(screen.getByRole("option", { name: /^Compose/u }));
    expect(rc.command).toHaveBeenCalledWith("compose", undefined);
  });

  it("hides disabled commands", async () => {
    const { user } = setup(fakeRcmail({ commands: { compose: false, logout: false } }));
    await open(user);
    expect(screen.queryByRole("option", { name: /^Compose/u })).toBeNull();
    expect(screen.queryByRole("option", { name: /^Logout/u })).toBeNull();
    expect(screen.getByRole("option", { name: /^Check for new messages/u })).toBeTruthy();
  });

  it("says when nothing matches and announces the count", async () => {
    const { user } = setup();
    await open(user);
    await user.type(input(), "zzzz");
    expect(options()).toHaveLength(0);
    expect(screen.getByText("No matches")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("Results: 0");
    expect(input().hasAttribute("aria-activedescendant")).toBe(false);
  });

  it("renders folder names as text, never as markup", async () => {
    const name = '<img src=x onerror="window.pwned=1">Evil';
    const rc = fakeRcmail({ env: { mailboxes: { INBOX: { id: "INBOX", name: "Inbox" }, X: { id: "X", name } }, mailboxes_list: ["INBOX", "X"] } });
    const { user } = setup(rc);
    const dialog = await open(user);
    await user.type(input(), "evil");
    expect(options()[0]!.textContent).toContain(name);
    expect(dialog.querySelector("img")).toBeNull();
    expect((window as Window & { pwned?: number }).pwned).toBeUndefined();
  });
});

describe("page state", () => {
  it("follows Elastic's dark mode while open", async () => {
    const { user } = setup();
    const dialog = await open(user);
    const root = dialog.closest(".lm")!;
    expect(root.classList.contains("is-dark")).toBe(false);
    await act(async () => document.documentElement.classList.add("dark-mode"));
    expect(root.classList.contains("is-dark")).toBe(true);
  });

  it("is right-to-left on a right-to-left page or in a right-to-left language", async () => {
    const { user } = setup();
    const dialog = await open(user);
    const root = dialog.closest(".lm")!;
    expect(root.getAttribute("dir")).toBe("ltr");
    await act(async () => document.documentElement.setAttribute("dir", "rtl"));
    expect(root.getAttribute("dir")).toBe("rtl");
    await act(async () => {
      document.documentElement.removeAttribute("dir");
      document.documentElement.setAttribute("lang", "he");
    });
    expect(root.getAttribute("dir")).toBe("rtl");
    expect(root.getAttribute("lang")).toBe("he");
  });

  it("speaks the user's language through Roundcube's labels", async () => {
    document.documentElement.setAttribute("lang", "de");
    const rc = fakeRcmail({
      labels: { "lumen.palette_placeholder": "Ordner, Einstellungen und Aktionen suchen", compose: "Verfassen" },
    });
    const { user } = setup(rc);
    await open(user);
    expect(input().getAttribute("placeholder")).toBe("Ordner, Einstellungen und Aktionen suchen");
    expect(screen.getByRole("option", { name: /^Verfassen/u })).toBeTruthy();
  });
});

describe("trigger and frames", () => {
  it("opens from the trigger, reflects aria-expanded and returns the focus to it", async () => {
    const trigger = document.createElement("a");
    trigger.href = "#";
    document.body.append(trigger);
    const { user } = setup(fakeRcmail(), trigger);
    await user.click(trigger);
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    await user.keyboard("{Escape}");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger);
    trigger.focus();
    fireEvent.keyDown(trigger, { key: " " });
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("opens with Ctrl+K pressed inside a same-origin frame, except in its text editors", async () => {
    const frame = document.createElement("iframe");
    document.body.append(frame);
    const frameDoc = frame.contentDocument!;
    frameDoc.body.innerHTML = '<p>Message</p><textarea></textarea>';
    setup();
    const FrameKeyboardEvent = (frame.contentWindow as unknown as typeof globalThis).KeyboardEvent;
    const press = (target: Element) =>
      act(() => {
        target.dispatchEvent(new FrameKeyboardEvent("keydown", { key: "k", code: "KeyK", ctrlKey: true, bubbles: true }));
      });
    await press(frameDoc.querySelector("textarea")!);
    expect(screen.queryByRole("dialog")).toBeNull();
    await press(frameDoc.querySelector("p")!);
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("listens again each time a frame loads a new document", () => {
    const frame = document.createElement("iframe");
    document.body.append(frame);
    const add = vi.spyOn(frame.contentWindow!, "addEventListener");
    setup();
    add.mockClear();
    frame.dispatchEvent(new Event("load"));
    frame.dispatchEvent(new Event("load"));
    expect(add.mock.calls.filter(([type, , capture]) => type === "keydown" && capture === true)).toHaveLength(2);
  });

  it("recognises editor targets from other documents (duck-typed)", () => {
    const frame = document.createElement("iframe");
    document.body.append(frame);
    const area = frame.contentDocument!.createElement("textarea");
    frame.contentDocument!.body.append(area);
    const FrameKeyboardEvent = (frame.contentWindow as unknown as typeof globalThis).KeyboardEvent;
    const event = new FrameKeyboardEvent("keydown", { key: "k" });
    Object.defineProperty(event, "target", { value: area });
    expect(inEditor(event)).toBe(true);
  });

  it("does not stop on an item that throws", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const rc = fakeRcmail();
    rc.command.mockImplementation(() => {
      throw new Error("busy");
    });
    const { user } = setup(rc);
    await open(user);
    await user.keyboard("{Enter}");
    expect(warn).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
