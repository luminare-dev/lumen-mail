// The design-system gallery: a static React app (gallery/dist, relative paths, so it can be served
// from any folder). Two pages:
//   index.html    tokens with their contrast numbers, type, shape, and the real command palette on a
//                 mocked rcmail;
//   preview.html  skin preview pages written for the gallery with Elastic's structural ids and
//                 classes (mail, settings, login), styled by a BUILT Lumen skin when one is given.
//
// LUMEN_GALLERY_SKINS=<folder> points at a folder with a built skin in lumen/ and the Elastic it
// was built against in elastic/, for example <roundcube>/skins after `lumen-mail install`. The dev
// server serves it under skins/; `vite build` copies lumen/ and Elastic's fonts, images and
// bootstrap.min.css into dist/skins/. Without it, the gallery shows tokens and the palette only.
// A gallery built with LUMEN_GALLERY_SKINS contains the compiled skin (CC BY-SA 3.0) and Elastic's
// files: it is for local review; CI builds it without.
import react from "@vitejs/plugin-react";
import { cpSync, createReadStream, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { findSkin, galleryData } from "./data.mjs";

const here = fileURLToPath(new URL(".", import.meta.url));
const root = resolve(here, "..");
const skins = process.env.LUMEN_GALLERY_SKINS ? resolve(process.env.LUMEN_GALLERY_SKINS) : null;
const VIRTUAL = "virtual:lumen-gallery";
const TYPES = {
  ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
  ".woff": "font/woff", ".woff2": "font/woff2", ".json": "application/json",
};
const BANNER =
  "/*! lumen-mail gallery | MIT | https://github.com/luminare-dev/lumen-mail | includes React and React DOM " +
  "(MIT, Copyright (c) Meta Platforms, Inc. and affiliates) */\n";

function lumenGallery() {
  const skin = findSkin(skins);
  let outDir = join(here, "dist");
  return {
    name: "lumen-gallery",
    configResolved(config) {
      outDir = config.build.outDir;
    },
    resolveId(id) {
      return id === VIRTUAL ? `\0${VIRTUAL}` : null;
    },
    load(id) {
      return id === `\0${VIRTUAL}` ? `export default ${JSON.stringify(galleryData(root, skins))};` : null;
    },
    configureServer(server) {
      if (!skin) return;
      server.middlewares.use("/skins/", (req, res, next) => {
        const rel = normalize(decodeURIComponent((req.url || "").split("?")[0])).replace(/^([/\\])+/u, "");
        const file = join(skin.dir, rel);
        if (!file.startsWith(skin.dir + sep) || !existsSync(file) || !statSync(file).isFile()) return next();
        res.setHeader("Content-Type", TYPES[extname(file)] || "application/octet-stream");
        createReadStream(file).pipe(res);
        return undefined;
      });
    },
    generateBundle(_options, bundle) {
      // The licence banner is added after minification (the minifier drops output banners).
      for (const file of Object.values(bundle)) {
        if (file.type === "chunk" && !file.code.startsWith("/*! lumen-mail ")) file.code = BANNER + file.code;
      }
    },
    closeBundle() {
      // The gallery bundles React (MIT) and the Sora font (OFL-1.1): the licences travel with it.
      cpSync(join(root, "LICENSE"), join(outDir, "LICENSE"));
      cpSync(join(root, "NOTICE"), join(outDir, "NOTICE"));
      cpSync(join(root, "skin", "fonts", "Sora-OFL.txt"), join(outDir, "Sora-OFL.txt"));
      for (const name of readdirSync(join(outDir, "assets"))) {
        if (name.endsWith(".js") && !readFileSync(join(outDir, "assets", name), "utf8").startsWith("/*! lumen-mail ")) {
          throw new Error(`gallery/dist/assets/${name} lacks the licence banner`);
        }
      }
      if (!skin) return;
      const target = join(outDir, "skins");
      mkdirSync(target, { recursive: true });
      cpSync(join(skin.dir, "lumen"), join(target, "lumen"), { recursive: true, dereference: true });
      for (const part of ["fonts", "images", "README.md", "LICENSE"]) {
        const from = join(skin.dir, "elastic", part);
        if (existsSync(from)) cpSync(from, join(target, "elastic", part), { recursive: true, dereference: true });
      }
      if (skin.bootstrap) {
        cpSync(join(skin.dir, "elastic", "deps", "bootstrap.min.css"), join(target, "elastic", "deps", "bootstrap.min.css"));
      }
    },
  };
}

export default defineConfig({
  root: here,
  base: "./",
  publicDir: false,
  plugins: [react(), lumenGallery()],
  build: {
    outDir: join(here, "dist"),
    emptyOutDir: true,
    sourcemap: false,
    target: ["chrome111", "edge111", "firefox121", "safari16.4"],
    rolldownOptions: {
      input: { index: join(here, "index.html"), preview: join(here, "preview.html") },
    },
  },
  server: {
    fs: { allow: [root] },
  },
});
