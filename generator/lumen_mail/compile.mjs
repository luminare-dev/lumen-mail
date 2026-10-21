#!/usr/bin/env node
// Lumen compile driver (MIT, https://github.com/luminare-dev/lumen-mail).
//
// Reads one job as JSON on stdin:
//   {"node_modules": "/path/to/node_modules", "allowed_roots": ["/mirror/skins", "/rc/skins/elastic"],
//    "jobs": [{"entry": "...less", "css": "...css", "min": "...min.css"}]}
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
// Part of the LESS comes from Elastic's folder, which the Roundcube owner can change (on KeyHelp
// the user that also runs the webmail's PHP). So the compile runs nothing from it and reads
// nothing outside its folders:
//   - no inline JavaScript (javascriptEnabled stays off);
//   - @plugin never runs, wherever it is (less applies its own disablePluginRule only to the
//     entry file): the plugin loader refuses before it reads the file;
//   - @import and data-uri() read only files whose real path is inside "allowed_roots" (the
//     mirror tree and Elastic's folder), and imports over the network are refused.
// The generator also runs the compile as the Roundcube owner, never as root (privileges.py), and
// its drift check names any @plugin in Elastic's LESS before the compile starts.

import { readFileSync, realpathSync, writeFileSync } from 'node:fs';
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

// --- hardening (see the header) ---------------------------------------------------------------
const allowedRoots = [];
for (const root of job.allowed_roots || []) {
    try {
        allowedRoots.push(realpathSync(root));
    } catch (e) {
        fail(`cannot resolve the allowed folder ${root}: ${e.message}`);
    }
}
if (!allowedRoots.length) {
    fail('the job names no allowed_roots');
}

function isAllowed(file) {
    let real;
    try {
        real = realpathSync(file);
    } catch {
        return false;
    }
    return allowedRoots.some((root) => real === root || real.startsWith(root + path.sep));
}

function refused(message, filename) {
    return { type: 'File', message, filename: filename || null };
}

const pluginMessage = (name) => `@plugin${name ? ` "${name}"` : ''} is not allowed in a Lumen build`;
const loaders = [less.PluginLoader && less.PluginLoader.prototype, less.AbstractPluginLoader && less.AbstractPluginLoader.prototype];
for (const proto of loaders.filter(Boolean)) {
    proto.loadPlugin = (filename) => Promise.reject(refused(pluginMessage(filename), filename));
    proto.loadPluginSync = (filename) => refused(pluginMessage(filename), filename);
    proto.evalPlugin = (contents, context, imports, options, fileInfo) => {
        const name = fileInfo && (typeof fileInfo === 'string' ? fileInfo : fileInfo.filename);
        return new less.LessError(refused(pluginMessage(name), name), (imports && imports.contents) || {}, name);
    };
}

const baseLoadFile = less.FileManager.prototype.loadFile;
less.FileManager.prototype.loadFile = function loadFile(filename, currentDirectory, options, environment, callback) {
    const outside = (file) => refused(`${file} is outside the folders a Lumen build may read`, file);
    if (options && options.syncImport) {
        // data-uri() and synchronous imports
        let result = baseLoadFile.call(this, filename, currentDirectory, options, environment);
        if (result && result.filename && !isAllowed(result.filename)) {
            result = { error: outside(result.filename) };
        }
        if (callback) {
            callback(result && result.error, result);
            return undefined;
        }
        return result;
    }
    return baseLoadFile.call(this, filename, currentDirectory, options, environment).then((data) => {
        if (!isAllowed(data.filename)) {
            throw outside(data.filename);
        }
        return data;
    });
};
if (less.UrlFileManager) {
    const network = (filename) => refused(`${filename}: imports over the network are not allowed in a Lumen build`, filename);
    less.UrlFileManager.prototype.loadFile = (filename) => Promise.reject(network(filename));
    less.UrlFileManager.prototype.loadFileSync = (filename) => ({ error: network(filename) });
}
// ------------------------------------------------------------------------------------------------

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
    if (!isAllowed(item.entry)) {
        fail(`${item.entry} is outside the folders a Lumen build may read`, { file: item.entry });
    }
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
            plugins: [],
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
