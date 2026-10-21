# Third-party notices

## Included in this repository

| Component | Version | Licence | Where | Source |
|---|---|---|---|---|
| Sora (variable font) | 2.000 | SIL Open Font License 1.1 ([text](skin/fonts/Sora-OFL.txt)) | `skin/fonts/Sora-Variable.woff`, the unchanged font in a WOFF container | <https://github.com/sora-xor/sora-font> |

## Bundled into built files (not in the repository)

`npm run build:palette` writes `palette/dist/lumen-palette.js`, which every skin build copies into
`skins/lumen/` (so it is also in each release package), and `npm run build:gallery` writes
`gallery/dist/`. Both bundle React. Every bundle starts with a banner that names React and React
DOM and their licence (`scripts/check-palette.mjs` and the gallery build fail without it), and
this file travels with them: the generator copies it into every `skins/lumen/` and the gallery
build into `gallery/dist/`.

| Component | Version | Licence | Built file |
|---|---|---|---|
| React, React DOM, scheduler | 19.3.1, 19.3.1, 0.28.0 (`package-lock.json`) | MIT, Copyright (c) Meta Platforms, Inc. and affiliates | `skins/lumen/lumen-palette.js`, `gallery/dist/assets/` |

Build and test tools (Vite, Rolldown, lightningcss, TypeScript, Vitest, jsdom, Testing Library
and their dependencies) are used to build and test, not distributed; `package-lock.json` lists
them with their licences. The LESS compiler (less, Apache-2.0) and the minifier (clean-css, MIT)
run on the server to compile the skin's stylesheets and are not part of the output.

### React, React DOM and scheduler: MIT licence

```text
MIT License

Copyright (c) Meta Platforms, Inc. and affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Not included

No file of Roundcube or of its Elastic skin (templates, stylesheets, LESS sources, scripts,
images, fonts) is part of this repository. The generator reads them from the local installation
at build time; the compiled stylesheets are an adaptation of Elastic under CC BY-SA 3.0 (see
`NOTICE`). Not affiliated with or endorsed by the Roundcube project.
