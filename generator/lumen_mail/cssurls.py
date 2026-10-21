"""Find and rewrite url(...) references in compiled CSS.

A small tokenizer instead of one regular expression: quoted values may contain ")" (data URIs),
and comments or strings elsewhere must not be mistaken for a url().
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Callable, Iterator

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


@dataclass(frozen=True)
class CssUrl:
    start: int      # offset of "url("
    end: int        # offset after ")"
    quote: str      # "", "'" or '"'
    value: str      # the raw value between the quotes (or parentheses)

    @property
    def is_local(self) -> bool:
        """A relative reference to a file (not data:, not http:, not //host, not #fragment)."""
        v = self.value.strip()
        return bool(v) and not SCHEME_RE.match(v) and not v.startswith(("//", "#", "/"))

    @property
    def is_absolute_path(self) -> bool:
        v = self.value.strip()
        return v.startswith("/") and not v.startswith("//")

    def parts(self) -> tuple[str, str, str]:
        """(path, query, fragment) of the value."""
        v = self.value.strip()
        frag = ""
        if "#" in v:
            v, frag = v.split("#", 1)
        query = ""
        if "?" in v:
            v, query = v.split("?", 1)
        return v, query, frag


def iter_urls(css: str) -> Iterator[CssUrl]:
    i, n = 0, len(css)
    while i < n:
        c = css[i]
        if c == "/" and css.startswith("/*", i):
            j = css.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'":
            i = _skip_string(css, i)
            continue
        if (c in "uU" and css[i:i + 4].lower() == "url(" and (i == 0 or not (css[i - 1].isalnum() or css[i - 1] in "-_"))):
            j = i + 4
            while j < n and css[j] in " \t\r\n\f":
                j += 1
            if j < n and css[j] in "\"'":
                quote = css[j]
                k = _skip_string(css, j)
                value = css[j + 1:k - 1]
                m = k
                while m < n and css[m] in " \t\r\n\f":
                    m += 1
                if m < n and css[m] == ")":
                    yield CssUrl(i, m + 1, quote, value)
                    i = m + 1
                    continue
                i = k
                continue
            k = css.find(")", j)
            if k < 0:
                return
            yield CssUrl(i, k + 1, "", css[j:k].strip())
            i = k + 1
            continue
        i += 1


def _skip_string(css: str, i: int) -> int:
    quote, j, n = css[i], i + 1, len(css)
    while j < n:
        if css[j] == "\\":
            j += 2
            continue
        if css[j] == quote:
            return j + 1
        if css[j] == "\n":
            return j
        j += 1
    return n


def rewrite_urls(css: str, fn: Callable[[CssUrl], str | None]) -> str:
    """Replace each url(...) for which fn returns a new value (keeping its quote style)."""
    out: list[str] = []
    last = 0
    for url in iter_urls(css):
        new = fn(url)
        if new is None:
            continue
        q = url.quote or ('"' if any(ch in new for ch in " ()'\"") else "")
        out.append(css[last:url.start])
        out.append(f"url({q}{new}{q})")
        last = url.end
    out.append(css[last:])
    return "".join(out)


def resolve(base_dir: str, rel_path: str) -> str:
    """posix join + normpath of a relative url path against a directory (both posix)."""
    return posixpath.normpath(posixpath.join(base_dir, rel_path))
