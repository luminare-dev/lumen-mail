// Gallery entry: the page itself, and the real command palette mounted exactly as in Roundcube
// (mount() with window.rcmail, its own shadow root), on a mocked rcmail.

import { createRoot } from "react-dom/client";
import { mount } from "../../palette/src/mount";
import { App } from "./App";
import { mockRcmail, type Lang } from "./mock";
import "./gallery.css";

let lang: Lang = "en";
(window as Window & { rcmail?: unknown }).rcmail = mockRcmail(() => lang);

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <App
      setLang={(next) => {
        lang = next;
      }}
    />,
  );
}
mount(window);
