// What the palette reads from the page around it, observed rather than read once:
//   dark mode  html.dark-mode, the class Elastic's ui.js toggles (no reload)
//   direction  <html dir> or <body dir>; Roundcube does not set either for Elastic, so a
//              right-to-left interface language also turns the palette right-to-left
//   language   <html lang>, which Roundcube sets from the user's language

import { useEffect, useState } from "react";

export interface PageState {
  dark: boolean;
  dir: "ltr" | "rtl";
  lang: string;
}

const RTL_LANGS = /^(?:ar|dv|fa|he|ps|sd|ug|ur|yi)(?:[-_]|$)/iu;

export function readPage(doc: Document): PageState {
  const html = doc.documentElement;
  const lang = html.getAttribute("lang") || "en";
  const dir = (html.getAttribute("dir") || doc.body?.getAttribute("dir") || "").toLowerCase();
  return {
    dark: html.classList.contains("dark-mode"),
    dir: dir === "rtl" || (!dir && RTL_LANGS.test(lang)) ? "rtl" : "ltr",
    lang,
  };
}

export function usePageState(doc: Document): PageState {
  const [state, setState] = useState(() => readPage(doc));
  useEffect(() => {
    const update = () =>
      setState((old) => {
        const next = readPage(doc);
        return old.dark === next.dark && old.dir === next.dir && old.lang === next.lang ? old : next;
      });
    const observer = new MutationObserver(update);
    const attributeFilter = ["class", "dir", "lang"];
    observer.observe(doc.documentElement, { attributes: true, attributeFilter });
    if (doc.body) observer.observe(doc.body, { attributes: true, attributeFilter: ["dir"] });
    update();
    return () => observer.disconnect();
  }, [doc]);
  return state;
}

/** The focused element, looking into shadow roots (the palette lives in one). */
export function deepActiveElement(doc: Document): Element | null {
  let el: Element | null = doc.activeElement;
  while (el?.shadowRoot?.activeElement) el = el.shadowRoot.activeElement;
  return el;
}

export interface NavigatorLike {
  platform?: string;
  userAgent?: string;
  userAgentData?: { platform?: string };
}

/** Apple platforms use the Command key, all others Ctrl. */
export function isApplePlatform(nav: NavigatorLike | null | undefined): boolean {
  if (!nav) return false;
  return /mac|iphone|ipad|ipod/iu.test(nav.userAgentData?.platform || nav.platform || nav.userAgent || "");
}

type ShortcutEvent = Pick<KeyboardEvent, "ctrlKey" | "metaKey" | "altKey" | "shiftKey" | "key" | "code">;

/**
 * Cmd+K on Apple platforms, Ctrl+K elsewhere (on a Mac, Ctrl+K stays with text fields). The
 * physical K key also counts where the layout types a non-Latin letter there (Russian, Greek),
 * but not on Latin layouts that put another letter on it (Dvorak).
 */
export function isToggleKey(event: ShortcutEvent, apple: boolean): boolean {
  const mod = apple ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
  if (!mod || event.altKey || event.shiftKey) return false;
  const key = String(event.key || "").toLowerCase();
  return key === "k" || (event.code === "KeyK" && !/^[a-z]$/u.test(key));
}

// Text the user is writing: plain-text message bodies, signatures and other text areas, rich
// text (TinyMCE's editable body and its toolbar, any contenteditable element).
const EDITOR = "textarea, [contenteditable=''], [contenteditable='true'], [contenteditable='plaintext-only'], .tox";

/** The key event comes from a text editor, where Ctrl+K belongs to the editor (TinyMCE: link). */
export function inEditor(event: Event): boolean {
  const target = (event.composedPath?.()[0] ?? event.target) as Element | null;
  // Duck-typed: events from a frame's document carry that frame's Element class.
  return Boolean(target && typeof target.closest === "function" && target.closest(EDITOR));
}

/**
 * A Roundcube modal dialog is open (jQuery UI adds .ui-widget-overlay for modal dialogs, such as
 * Create folder). jQuery UI pulls the focus back into its dialog from anywhere outside it, so a
 * palette opened over one could not be used: its keys would reach the hidden dialog. Checks the
 * page and the document the key was pressed in (a frame).
 */
export function modalDialogOpen(doc: Document, event?: Event): boolean {
  const docs = new Set<Document>([doc]);
  const target = event?.target as Node | null | undefined;
  if (target?.ownerDocument) docs.add(target.ownerDocument);
  for (const d of docs) {
    if (d.querySelector(".ui-widget-overlay")) return true;
  }
  return false;
}
