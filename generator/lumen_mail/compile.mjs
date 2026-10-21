#!/usr/bin/env node
// Lumen compile driver (MIT, https://github.com/luminare-dev/lumen-mail).
//
// Reads one job as JSON on stdin:
//   {"node_modules": "/path/to/node_modules", "jobs": [{"entry": "...less", "css": "...css", "min": "...min.css"}]}
// compiles every entry with the pinned "less" package, minifies the result with "clean-css" and
// writes both files. Prints one JSON line on stdout: {"ok": true, "versions": {...}, "results": [...]}
// or {"ok": false, "error": "...", "file": "...", "line": N} (exit code 1).
//
// url() values are NOT rewritten (rewriteUrls "off", as in Elastic's own build): Elastic writes
// every url relative to its styles/ folder, also inside styles/widgets/, and data-uri() reads
// files relative to the entry. The Python side resolves each url afterwards (Lumen first, then
// Elastic, like Roundcube's own skin lookup). less warnings (for example a skipped data-uri) are
// returned in "warnings".
//
// No network access, no plugins, no inline JavaScript in LESS (javascriptEnabled stays off).

import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

function fail(error, extra = {}) {
    process.stdout.write(JSON.stringify({ ok: false, error: String(error), ...extra }) + '\n');
    process.exit(1);
}

let job;
try {
    job = JSON.parse(readFileSync(0, 'utf8'));
} catch (e) {
    fail(`cannot read the job from stdin: ${e.message}`);
}

const base = job.node_modules ? path.join(job.node_modules, '..', 'package.json') : import.meta.url;
const require = createRequire(base);
let less;
let CleanCSS;
try {
    less = require('less');
    CleanCSS = require('clean-css');
} catch (e) {
    fail(`cannot load the compiler (run npm ci): ${e.message}`);
}

const versions = {
    node: process.version,
    less: less.version.join('.'),
    'clean-css': require('clean-css/package.json').version,
};

const minifier = new CleanCSS({
    level: { 1: { specialComments: 0 }, 2: {} },
    rebase: false,
    inline: false,
    returnPromise: false,
});

const lessWarnings = [];
less.logger.addListener({ warn: (msg) => lessWarnings.push(String(msg)), error: (msg) => lessWarnings.push(String(msg)) });

const results = [];
for (const item of job.jobs || []) {
    const warningsBefore = lessWarnings.length;
    let source;
    try {
        source = readFileSync(item.entry, 'utf8');
    } catch (e) {
        fail(`cannot read ${item.entry}: ${e.message}`, { file: item.entry });
    }
    let output;
    try {
        output = await less.render(source, {
            filename: path.resolve(item.entry),
            rewriteUrls: 'off',
            javascriptEnabled: false,
        });
    } catch (e) {
        fail(e.message, { file: e.filename || item.entry, line: e.line || null, column: e.column || null, type: e.type || null });
    }
    const minified = minifier.minify(output.css);
    if (minified.errors && minified.errors.length) {
        fail(`clean-css: ${minified.errors.join('; ')}`, { file: item.entry });
    }
    writeFileSync(item.css, output.css.endsWith('\n') ? output.css : output.css + '\n');
    writeFileSync(item.min, minified.styles + '\n');
    results.push({
        entry: item.entry,
        css: item.css,
        min: item.min,
        css_bytes: Buffer.byteLength(output.css),
        min_bytes: Buffer.byteLength(minified.styles),
        imports: output.imports,
        warnings: lessWarnings.slice(warningsBefore).concat(minified.warnings || []),
    });
}

process.stdout.write(JSON.stringify({ ok: true, versions, results }) + '\n');
