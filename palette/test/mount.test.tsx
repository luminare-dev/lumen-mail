import { act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { HOST_ID, mount, shouldMount, TRIGGER_ID, type Mounted } from "../src/mount";
import type { RcmailEnv } from "../src/types";
import { fakeRcmail, MAIL_PAGE } from "./fixtures";

type TestWindow = Window & { rcmail?: unknown };
let mounted: Mounted | null = null;

function withRcmail(env: Partial<RcmailEnv> = {}) {
  (window as TestWindow).rcmail = fakeRcmail({ env });
}

function start() {
  act(() => {
    mounted = mount(window);
  });
  return mounted;
}

function shadow() {
  const root = document.getElementById(HOST_ID)?.shadowRoot;
  if (!root) throw new Error("no shadow root");
  return within(root as unknown as HTMLElement);
}

beforeEach(() => {
  document.documentElement.setAttribute("lang", "en");
  document.body.innerHTML = MAIL_PAGE;
  withRcmail();
});

afterEach(() => {
  act(() => mounted?.unmount());
  mounted = null;
  delete (window as TestWindow).rcmail;
  document.body.innerHTML = "";
});

describe("shouldMount", () => {
  it("needs rcmail with the Lumen skin on a top-level page", () => {
    expect(shouldMount(window)).not.toBeNull();
    delete (window as TestWindow).rcmail;
    expect(shouldMount(window)).toBeNull();
    (window as TestWindow).rcmail = { env: { skin: "lumen" } };
    expect(shouldMount(window)).toBeNull(); // no command()
  });

  it.each<[string, Partial<RcmailEnv>]>([
    ["another skin", { skin: "elastic" }],
    ["the login page", { task: "login" }],
    ["a print page", { action: "print" }],
    ["an error page", { server_error: 500 }],
    ["a framed page", { framed: 1 }],
    ["an external compose window", { extwin: 1 }],
  ])("stays away from %s", (_name, env) => {
    withRcmail(env);
    expect(shouldMount(window)).toBeNull();
    start();
    expect(mounted).toBeNull();
    expect(document.getElementById(HOST_ID)).toBeNull();
    expect(document.getElementById(TRIGGER_ID)).toBeNull();
  });

  it("stays away from a page inside a frame", () => {
    const fake = { rcmail: fakeRcmail(), top: {}, self: {} } as unknown as Window;
    expect(shouldMount(fake)).toBeNull();
  });
});

describe("mount", () => {
  it("renders into its own shadow root, once", () => {
    start();
    const host = document.getElementById(HOST_ID)!;
    expect(host.parentElement).toBe(document.body);
    expect(host.shadowRoot?.querySelector("style")?.textContent).toContain("--lm-surface-raised");
    // Nothing of the dialog in the page's own DOM: Elastic's CSS and scripts cannot reach it.
    expect(document.querySelector(".lm, [role='dialog'], [role='listbox']")).toBeNull();
    expect(mount(window)).toBeNull();
    expect(document.querySelectorAll(`#${HOST_ID}`)).toHaveLength(1);
  });

  it("adds a labelled trigger as the first special button of Elastic's task menu", () => {
    start();
    const trigger = document.getElementById(TRIGGER_ID)!;
    expect(trigger.parentElement?.classList.contains("special-buttons")).toBe(true);
    expect(trigger.nextElementSibling?.classList.contains("theme")).toBe(true);
    expect(trigger.className).toBe("lumen-palette");
    expect(trigger.getAttribute("role")).toBe("button");
    expect(trigger.getAttribute("aria-haspopup")).toBe("dialog");
    expect(trigger.getAttribute("aria-keyshortcuts")).toBe("Control+K");
    expect(trigger.title).toBe("Open the command palette (Ctrl+K)");
    expect(trigger.querySelector("span.inner")?.textContent).toBe("Jump to");
  });

  it("opens from the trigger and from Ctrl+K, inside the shadow root", async () => {
    const user = userEvent.setup();
    start();
    await user.click(document.getElementById(TRIGGER_ID)!);
    expect(shadow().getByRole("dialog", { name: "Command palette" })).toBeTruthy();
    expect(shadow().getAllByRole("option").length).toBeGreaterThan(10);
    await user.keyboard("{Escape}");
    expect(shadow().queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(document.getElementById(TRIGGER_ID));
    await user.keyboard("{Control>}k{/Control}");
    expect(shadow().getByRole("dialog")).toBeTruthy();
  });

  it("works without Elastic's task menu (no trigger) and cleans up on unmount", () => {
    document.body.innerHTML = "<main></main>";
    start();
    expect(mounted?.trigger).toBeNull();
    expect(document.getElementById(HOST_ID)).not.toBeNull();
    act(() => mounted?.unmount());
    mounted = null;
    expect(document.getElementById(HOST_ID)).toBeNull();
  });
});
