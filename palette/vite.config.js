// Build the command palette as one classic script: palette/dist/lumen-palette.js (IIFE).
// React and React DOM are bundled in (production build); the stylesheet is inlined as a string
// for the shadow root. No code splitting, no dynamic imports, no network requests at run time
// (scripts/check-palette.mjs checks the built file). The generator copies the file into
// skins/lumen/, where Roundcube serves it with a ?s=<mtime> cache-buster.
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const version = readFileSync(new URL("../version.txt", import.meta.url), "utf8").trim();
const BANNER =
  `/*! lumen-mail ${version} command palette | MIT | https://github.com/luminare-dev/lumen-mail | ` +
  "includes React and React DOM (MIT, Copyright (c) Meta Platforms, Inc. and affiliates) */\n";

// The licence banner is added after minification (the minifier drops output banners).
const licenceBanner = {
  name: "lumen-licence-banner",
  generateBundle(_options, bundle) {
    for (const file of Object.values(bundle)) {
      if (file.type === "chunk" && !file.code.startsWith("/*! lumen-mail ")) file.code = BANNER + file.code;
    }
  },
};

export default defineConfig({
  root,
  publicDir: false,
  plugins: [react(), licenceBanner],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "palette/dist",
    emptyOutDir: true,
    copyPublicDir: false,
    sourcemap: false,
    minify: true,
    target: ["chrome111", "edge111", "firefox121", "safari16.4"],
    lib: {
      entry: "palette/src/main.ts",
      name: "LumenPalette",
      formats: ["iife"],
      fileName: () => "lumen-palette.js",
    },
  },
});
