// One skin preview page (preview.html?page=mail|settings|login&mode=light|dark&dir=ltr|rtl):
// the gallery's representative markup with the built Lumen stylesheet, the classes Elastic's
// ui.js would set for the window width, and the real command palette on a mocked rcmail.

import data from "virtual:lumen-gallery";
import { createRoot } from "react-dom/client";
import { mount } from "../../palette/src/mount";
import { Page } from "./markup";
import { mockRcmail } from "./mock";

const query = new URLSearchParams(window.location.search);
const page = query.get("page") ?? "mail";
const dark = query.get("mode") === "dark";
const html = document.documentElement;
const body = document.body;

html.classList.toggle("dark-mode", dark);
html.setAttribute("dir", query.get("dir") === "rtl" ? "rtl" : "ltr");
body.className = `task-${page === "settings" ? "settings" : page} action-none`;

for (const href of [
  data.skin?.bootstrap ? "skins/elastic/deps/bootstrap.min.css" : null,
  data.skin ? "skins/lumen/styles/styles.min.css" : null,
]) {
  if (!href) continue;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.append(link);
}

// Elastic's ui.js: layout-phone up to 480 px, small up to 768, normal up to 1200, then large;
// "touch" up to 1024. On narrow screens it shows one column at a time.
const width = window.innerWidth;
const mode = width <= 480 ? "phone" : width > 1200 ? "large" : width > 768 ? "normal" : "small";
html.classList.add(`layout-${mode}`);
if (width <= 1024) html.classList.add("touch");

const root = document.getElementById("root");
if (root) {
  root.style.display = "contents";
  createRoot(root).render(<Page page={page} dark={dark} />);
}

requestAnimationFrame(() => {
  const keep = page === "settings" ? "layout-content" : page === "login" ? "layout-content" : "layout-list";
  if (mode === "phone" || mode === "small") {
    for (const id of ["layout-menu", "layout-sidebar", "layout-list", "layout-content"]) {
      if (id !== keep) document.getElementById(id)?.classList.add("hidden");
    }
  } else if (mode === "normal" && page === "mail") {
    document.getElementById("layout-sidebar")?.classList.add("hidden");
  }
  // Elastic's mode button would switch html.dark-mode; the preview does the same.
  document.querySelector("#taskmenu a.theme")?.addEventListener("click", (event) => {
    event.preventDefault();
    html.classList.toggle("dark-mode");
  });
  if (page !== "login") {
    (window as Window & { rcmail?: unknown }).rcmail = mockRcmail(() => "en", page === "settings" ? "settings" : "mail");
    mount(window);
  }
});
