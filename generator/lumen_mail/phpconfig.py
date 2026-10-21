"""Read one setting from a Roundcube config file without running PHP (read-only).

Used by uninstall to find the configured system skin. The file holds secrets (database password,
des_key), so nothing from it is ever printed except the value that was asked for, and only when
it is a plain name.

A small PHP tokenizer: it skips comments (//, #, /* */), text outside <?php ... ?>, and reads
single- and double-quoted strings, so "// $config['skin'] = 'lumen';" or the same text inside a
string does not count. It understands

    $config['skin'] = 'lumen';      $config["skin"]="lumen" ;      $rcmail_config['skin'] = ...

The last assignment wins, as in PHP. Any other form that may set the key (an expression, a
'skin' => ... pair, an include) makes the result uncertain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_VARS = ("config", "rcmail_config")
PLAIN_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_DQ_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "v": "\v", "f": "\f", "e": "\x1b", "\\": "\\", "$": "$", '"': '"'}


@dataclass(frozen=True)
class Tok:
    kind: str    # "var", "str", "expr" (a string with interpolation or a heredoc), "word", "op"
    value: str


@dataclass(frozen=True)
class Setting:
    value: str | None      # the literal value, or None
    found: bool            # an assignment to the key was found
    certain: bool          # the value (or its absence) is known for sure
    source: Path | None = None

    @property
    def printable(self) -> str:
        if not self.found:
            return f"{self.value} (Roundcube default)" if self.value else "(not set)"
        if self.value is None:
            return "(not a plain string)"
        return self.value if PLAIN_NAME_RE.match(self.value) else "(not a plain name)"


def tokenize(text: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n = 0, len(text)
    php = False
    while i < n:
        if not php:
            j = text.find("<?", i)
            if j < 0:
                break
            if text.startswith("<?php", j):
                i = j + 5
            elif text.startswith("<?=", j):
                i = j + 3
            else:
                i = j + 2
            php = True
            continue
        c = text[i]
        if text.startswith("?>", i):
            toks.append(Tok("op", ";"))
            php = False
            i += 2
            continue
        if c.isspace():
            i += 1
            continue
        if text.startswith("//", i) or (c == "#" and not text.startswith("#[", i)):
            while i < n and text[i] != "\n" and not text.startswith("?>", i):
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "'":
            j, buf = i + 1, []
            while j < n and text[j] != "'":
                if text[j] == "\\" and j + 1 < n and text[j + 1] in "\\'":
                    buf.append(text[j + 1])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            toks.append(Tok("str", "".join(buf)))
            i = j + 1
            continue
        if c == '"':
            j, buf, plain = i + 1, [], True
            while j < n and text[j] != '"':
                ch = text[j]
                if ch == "\\" and j + 1 < n:
                    nxt = text[j + 1]
                    buf.append(_DQ_ESCAPES.get(nxt, "\\" + nxt))
                    j += 2
                    continue
                if ch == "$" or (ch == "{" and j + 1 < n and text[j + 1] == "$"):
                    plain = False
                buf.append(ch)
                j += 1
            toks.append(Tok("str" if plain else "expr", "".join(buf)))
            i = j + 1
            continue
        if text.startswith("<<<", i):
            m = re.match(r"<<<[ \t]*(['\"]?)([A-Za-z_]\w*)\1\r?\n", text[i:])
            if m:
                label = m.group(2)
                end = re.compile(r"^[ \t]*" + re.escape(label) + r"\b", re.MULTILINE)
                e = end.search(text, i + m.end())
                toks.append(Tok("expr", ""))
                i = n if not e else e.end()
                continue
        if c == "$":
            m = re.match(r"\$([A-Za-z_]\w*)", text[i:])
            if m:
                toks.append(Tok("var", m.group(1)))
                i += m.end()
                continue
        if c.isalnum() or c == "_" or c == "\\":
            m = re.match(r"[\\\w]+", text[i:])
            assert m
            toks.append(Tok("word", m.group(0)))
            i += m.end()
            continue
        two = text[i:i + 2]
        if two in ("==", "=>", "!=", "<=", ">=", ".=", "+=", "-=", "*=", "/=", "|=", "&=", "^=", "%=", "??", "->", "::"):
            three = text[i:i + 3]
            if three in ("===", "!==", "??="):
                toks.append(Tok("op", three))
                i += 3
            else:
                toks.append(Tok("op", two))
                i += 2
            continue
        toks.append(Tok("op", c))
        i += 1
    return toks


def _is(tok: Tok | None, kind: str, value: str | None = None) -> bool:
    return tok is not None and tok.kind == kind and (value is None or tok.value == value)


def find_setting(text: str, key: str) -> Setting:
    toks = tokenize(text)
    value: str | None = None
    found = False
    certain = True
    k = 0
    while k < len(toks):
        t = toks[k]
        nxt = toks[k + 1:k + 5] + [None] * 4
        if (_is(t, "var") and t.value in CONFIG_VARS and _is(nxt[0], "op", "[") and _is(nxt[1], "str", key)
                and _is(nxt[2], "op", "]")):
            if _is(nxt[3], "op", "="):
                j = k + 5
                expr: list[Tok] = []
                depth = 0
                while j < len(toks):
                    tj = toks[j]
                    if tj.kind == "op" and tj.value in "([{":
                        depth += 1
                    elif tj.kind == "op" and tj.value in ")]}":
                        depth -= 1
                    elif tj.kind == "op" and tj.value == ";" and depth <= 0:
                        break
                    expr.append(tj)
                    j += 1
                found = True
                if len(expr) == 1 and expr[0].kind == "str":
                    value, certain = expr[0].value, True
                else:
                    value, certain = None, False
                k = j
                continue
            if nxt[3] is not None and nxt[3].kind == "op" and nxt[3].value in (".=", "??=", "+=", "|="):
                found, value, certain = True, None, False   # a compound assignment: value unknown
        elif _is(t, "str", key) and _is(nxt[0], "op", "=>"):
            found, value, certain = True, None, False      # 'skin' => ... inside an array
        elif _is(t, "word") and t.value.lower() in ("include", "include_once", "require", "require_once",
                                                       "extract", "eval"):
            certain = False   # may set the key; a later literal assignment makes it certain again
        k += 1
    return Setting(value=value, found=found, certain=certain)


def read_setting(path: Path, key: str) -> Setting:
    """Read ``key`` from the config file at ``path``. Raises OSError if it cannot be read."""
    text = path.read_text(encoding="utf-8", errors="replace")
    s = find_setting(text, key)
    return Setting(s.value, s.found, s.certain, path)


def system_skin(roundcube: Path, config: Path | None = None) -> Setting:
    """The configured system skin: config.inc.php, then defaults.inc.php, then 'elastic'.

    Raises OSError when config.inc.php exists but cannot be read (for example as a user without
    access to the mode-600 file); the caller decides what that means.
    """
    config = config or roundcube / "config" / "config.inc.php"
    if config.is_file() or config.exists():
        s = read_setting(config, "skin")
        if s.found or not s.certain:
            return s
    defaults = roundcube / "config" / "defaults.inc.php"
    if defaults.is_file():
        try:
            d = read_setting(defaults, "skin")
        except OSError:
            d = Setting(None, False, False, defaults)
        if d.found:
            return d
    return Setting("elastic", False, True, None)
