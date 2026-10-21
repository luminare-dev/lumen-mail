// Entry of the palette build: skins/lumen/lumen-palette.js, one classic script (IIFE) that the
// skin's footer wrapper loads with defer on top-level pages. mount() checks the page again, so the
// file does nothing anywhere else. A failure is logged, never thrown: Roundcube must keep working
// without the palette.

import { mount } from "./mount";

function start(): void {
  try {
    mount(window);
  } catch (error) {
    console.warn("lumen: command palette not started", error);
  }
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
else start();
