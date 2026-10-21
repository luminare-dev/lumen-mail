// Mount the command palette on a Roundcube page that uses the Lumen skin.
//
// The dialog lives in a shadow root on its own host element, so Elastic's styles cannot reach it
// and its styles cannot reach Roundcube. Only the inherited --lm-* design tokens of the Lumen
// stylesheet pass through, which keeps it in the active light or dark mode.
//
// The visible trigger is different on purpose: it is an ordinary link in Elastic's task menu
// (#taskmenu .special-buttons), added by this script rather than by a copied template. Elastic's
// own menu rules lay it out like the other menu items on every screen size (icon and label in the
// wide menu, icon only in the narrow one, a list row on phones), and the skin's stylesheet gives
// it its icon (a.lumen-palette:before). It is the only way to open the palette on touch screens.

import { createRoot, type Root } from "react-dom/client";
import { translator } from "./i18n";
import { Palette } from "./Palette";
import { isApplePlatform, type NavigatorLike } from "./page";
import type { Rcmail } from "./types";
import css from "./palette.css?inline";

export const HOST_ID = "lumen-palette";
export const TRIGGER_ID = "lumen-palette-trigger";

/**
 * rcmail when the palette belongs on this page, else null: Roundcube's client is there, the skin
 * is Lumen, the page is a top-level page (not a frame, not an external compose window) and not
 * the login, print or error page. The footer wrapper applies the same rules on the server; this
 * check keeps the bundle harmless wherever else it might be loaded.
 */
export function shouldMount(win: Window): Rcmail | null {
  const rc = (win as Window & { rcmail?: Rcmail }).rcmail;
  const env = rc?.env;
  if (!rc || !env || typeof rc.command !== "function") return null;
  if (env.skin !== "lumen" || env.framed || env.extwin || env.server_error) return null;
  if (env.task === "login" || env.action === "print") return null;
  try {
    if (win.top !== win.self) return null;
  } catch {
    return null;
  }
  return rc;
}

export interface Mounted {
  host: HTMLElement;
  trigger: HTMLElement | null;
  root: Root;
  unmount: () => void;
}

function addTrigger(doc: Document, rc: Rcmail): HTMLElement | null {
  const menu = doc.getElementById("taskmenu");
  if (!menu) return null;
  const t = translator(rc);
  const apple = isApplePlatform(doc.defaultView?.navigator as NavigatorLike | undefined);
  const a = doc.createElement("a");
  a.id = TRIGGER_ID;
  a.className = "lumen-palette";
  a.href = "#";
  a.setAttribute("role", "button");
  a.setAttribute("aria-haspopup", "dialog");
  a.setAttribute("aria-expanded", "false");
  a.setAttribute("aria-keyshortcuts", apple ? "Meta+K" : "Control+K");
  a.title = `${t("palette_open")} (${apple ? "⌘K" : "Ctrl+K"})`;
  const inner = doc.createElement("span");
  inner.className = "inner";
  inner.textContent = t("palette_trigger");
  a.append(inner);
  const special = menu.querySelector(".special-buttons");
  if (special) special.prepend(a);
  else menu.append(a);
  return a;
}

export function mount(win: Window = window): Mounted | null {
  const doc = win.document;
  const rc = shouldMount(win);
  if (!rc || !doc.body || doc.getElementById(HOST_ID)) return null;
  const host = doc.createElement("div");
  host.id = HOST_ID;
  doc.body.append(host);
  const shadow = host.attachShadow({ mode: "open" });
  const style = doc.createElement("style");
  style.textContent = css;
  const container = doc.createElement("div");
  shadow.append(style, container);
  const trigger = addTrigger(doc, rc);
  // Errors after mounting must not reach Roundcube as uncaught errors.
  const root = createRoot(container, {
    onUncaughtError: (error) => console.warn("lumen: command palette stopped", error),
    onCaughtError: () => {},
    onRecoverableError: () => {},
  });
  root.render(<Palette rc={rc} doc={doc} trigger={trigger} />);
  return {
    host,
    trigger,
    root,
    unmount() {
      root.unmount();
      host.remove();
      trigger?.remove();
    },
  };
}
