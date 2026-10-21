#!/usr/bin/env python3
"""Stand-in for compile.mjs in the tests (same JSON protocol, no Node needed).

For each job it follows the @import lines of the entry (relative paths, like LESS), collects
every url(...) and rewrites it relative to the entry's folder, as less does with
rewriteUrls: 'all'. The output is one rule per url plus a marker rule. Symlinks are not
resolved, like less. Set STUB_COMPILER_FAIL=1 to get a compile error back.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import sys

IMPORT_RE = re.compile(r"""@import\s+(?:\([^)]*\)\s*)?["']([^"']+)["']\s*;""")
URL_RE = re.compile(r"""url\(\s*(["']?)([^"')]+)\1\s*\)""")


def collect(path: str, seen: set[str], urls: list[str], entry_dir: str) -> None:
    path = os.path.normpath(path)
    if path in seen or not os.path.isfile(path):
        return
    seen.add(path)
    text = open(path, encoding="utf-8").read()
    here = os.path.dirname(path)
    for m in URL_RE.finditer(text):
        value = m.group(2)
        if re.match(r"^[a-z]+:", value) or value.startswith(("/", "#")):
            urls.append(value)
            continue
        target = os.path.normpath(os.path.join(here, value))
        urls.append(posixpath.normpath(os.path.relpath(target, entry_dir)))
    for m in IMPORT_RE.finditer(text):
        name = m.group(1)
        if not name.endswith(".less"):
            name += ".less"
        collect(os.path.join(here, name), seen, urls, entry_dir)


def main() -> int:
    job = json.load(sys.stdin)
    if os.environ.get("STUB_COMPILER_FAIL"):
        print(json.dumps({"ok": False, "error": "variable @color-x is undefined", "file": job["jobs"][0]["entry"],
                          "line": 3}))
        return 1
    results = []
    for item in job["jobs"]:
        urls: list[str] = []
        collect(item["entry"], set(), urls, os.path.dirname(item["entry"]))
        rules = "".join(f'.u{i} {{ background: url("{u}"); }}\n' for i, u in enumerate(urls))
        css = f"/* stub build of {os.path.basename(item['entry'])} */\n.stub {{ color: #0a1224; }}\n{rules}"
        with open(item["css"], "w", encoding="utf-8") as fh:
            fh.write(css)
        with open(item["min"], "w", encoding="utf-8") as fh:
            fh.write(css.replace("\n", "") + "\n")
        results.append({"entry": item["entry"], "css_bytes": len(css), "min_bytes": len(css), "imports": []})
    print(json.dumps({"ok": True, "versions": {"stub": "1"}, "results": results}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
