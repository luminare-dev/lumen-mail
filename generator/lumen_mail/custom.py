"""A customization: the files a Lumen token file compiles to (customizer ZIP or tokens/compile.mjs).

Folder layout (``<state dir>/custom/`` by default, see --custom):

    lumen.tokens.json   the token set (read for its name; the LESS and CSS are already compiled)
    lumen-custom.less   the skin's @lm-* variables; the build imports it after lumen-tokens.less
    lumen-custom.css    appended to styles.css and styles.min.css (--lumen-* variables, custom CSS)
    branding.json       logos, favicon and browser colours
    README.txt          optional
    custom/<file>       uploaded logos, images and fonts (built into skins/lumen/images/custom/)

Everything is checked before a build reads it: the LESS file may only set @lm-* variables to hex
colours, mix() of two hex colours, pixel sizes or a font list (so it cannot @import, call plugins
or read files), the CSS must be a compiled override without </style>, uploads must be images or
fonts of their declared type (SVG without scripts or outside references), and the branding values
must name files of the skin.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .util import LumenError

TOP_FILES = {"lumen.tokens.json", "lumen-custom.less", "lumen-custom.css", "branding.json"}
OPTIONAL_FILES = {"README.txt"}
MEDIA_DIR = "custom"
MEDIA_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".svg", ".woff", ".woff2"}
MAX_MEDIA = 4 * 1024 * 1024
MAX_TEXT = 512 * 1024
MAX_TOTAL = 24 * 1024 * 1024
MAX_FILES = 64
BRANDING_KEYS = ("app", "login", "compact", "favicon", "productName", "themeLight", "themeDark")
LESS_HEAD = "// Lumen tokens v1: "
CSS_HEAD = "/* Lumen tokens v1: "
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
HEX = r"#[0-9A-Fa-f]{6}"
LESS_LINE = re.compile(
    rf"^@lm-[a-z0-9-]+: (?:{HEX}|mix\({HEX}, {HEX}, \d{{1,3}}%\)|\d{{1,3}}(?:\.\d{{1,2}})?px|"
    r"~'[A-Za-z0-9 ,\"_.-]{1,400}');$")
SVG_FORBIDDEN = re.compile(
    rb"<script|<foreignobject|<!entity|<!doctype|<use\b|<animate|<set\b|\son[a-z]+\s*=|javascript:|@import|"
    rb"(?:href|src)\s*=\s*[\"'](?!#)|url\(\s*[\"']?(?!#)",
    re.IGNORECASE)
MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"), ".ico": (b"\x00\x00\x01\x00",), ".woff": (b"wOFF",), ".woff2": (b"wOF2",),
}


class CustomError(LumenError):
    def __init__(self, problems: list[str]):
        super().__init__("the customization was rejected", problems)
        self.problems = problems


@dataclass(frozen=True)
class Custom:
    folder: Path
    name: str
    sha256: str
    less: str
    css: str
    branding: dict[str, str]
    media: tuple[str, ...] = field(default=())


def folder_digest(folder: Path) -> str | None:
    """sha256 over a customization folder's files, or None when there is none (no or an empty folder)."""
    if not folder.is_dir():
        return None
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        rel = path.relative_to(folder).as_posix()
        digest.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _files(folder: Path, problems: list[str]) -> list[str]:
    out: list[str] = []
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            problems.append(f"{rel}: symbolic links are not allowed")
        elif stat.S_ISDIR(mode):
            if rel != MEDIA_DIR:
                problems.append(f"{rel}/: unexpected folder")
        elif rel in TOP_FILES or rel in OPTIONAL_FILES:
            out.append(rel)
        elif rel.startswith(MEDIA_DIR + "/") and "/" not in rel[len(MEDIA_DIR) + 1:]:
            name = rel[len(MEDIA_DIR) + 1:]
            if not NAME_RE.match(name) or name.startswith(".") or Path(name).suffix.lower() not in MEDIA_TYPES:
                problems.append(f"{rel}: only images (png, jpg, webp, gif, ico, svg) and fonts (woff, woff2) "
                                "with plain names are allowed")
            else:
                out.append(rel)
        else:
            problems.append(f"{rel}: unexpected file")
    return out


def _check_media(folder: Path, rel: str, problems: list[str]) -> None:
    data = (folder / rel).read_bytes()
    if len(data) > MAX_MEDIA:
        problems.append(f"{rel}: larger than {MAX_MEDIA // (1024 * 1024)} MB")
        return
    suffix = Path(rel).suffix.lower()
    if suffix == ".webp":
        ok = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    elif suffix == ".svg":
        if b"<svg" not in data[:4096].lower() or SVG_FORBIDDEN.search(data):
            problems.append(f"{rel}: not an SVG, or it contains scripts, event handlers, <use>, animations, "
                            "entities or references outside the file")
        return
    else:
        ok = data.startswith(MAGIC[suffix])
    if not ok:
        problems.append(f"{rel}: content does not match the {suffix} type")


def _text(folder: Path, rel: str, problems: list[str]) -> str:
    raw = (folder / rel).read_bytes()
    if len(raw) > MAX_TEXT:
        problems.append(f"{rel}: larger than {MAX_TEXT // 1024} KB")
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(f"{rel}: not UTF-8")
        return ""


def _check_less(text: str, problems: list[str]) -> None:
    lines = text.splitlines()
    if not lines or not lines[0].startswith(LESS_HEAD):
        problems.append(f"lumen-custom.less: must start with '{LESS_HEAD.strip()}'")
        return
    for no, line in enumerate(lines[1:], start=2):
        if line.startswith("// ") and "*/" not in line and "/*" not in line:
            continue
        if not LESS_LINE.match(line):
            problems.append(f"lumen-custom.less line {no}: only @lm-* variables with colours, mix() of two colours, "
                            f"px sizes or a font list are allowed: {line[:80]!r}")
            return


def _check_branding(value: object, key: str, media: set[str], skin_images: Path, problems: list[str]) -> str:
    if not isinstance(value, str):
        problems.append(f"branding.json: {key} must be a string")
        return ""
    if key == "productName":
        if len(value) > 60 or re.search(r"[<>{}\"]", value):
            problems.append("branding.json: productName must be at most 60 characters without < > { } \"")
            return ""
        return value
    if key in ("themeLight", "themeDark"):
        if not re.fullmatch(HEX, value):
            problems.append(f"branding.json: {key} must be #RRGGBB")
            return ""
        return value
    if value == "":
        return ""
    if value.startswith("/images/custom/"):
        if value[len("/images/custom/"):] not in media:
            problems.append(f"branding.json: {key} names {value}, which is not in the customization")
        return value
    if value.startswith("/images/"):
        name = value[len("/images/"):]
        if not NAME_RE.match(name) or not (skin_images / name).is_file():
            problems.append(f"branding.json: {key} names {value}, which is not a file of the skin")
        return value
    problems.append(f"branding.json: {key} must be /images/<file>, /images/custom/<file> or empty "
                    "(Roundcube serves skin files only; upload the file)")
    return ""


def load(folder: Path, skin_images: Path) -> Custom:
    """Check a customization folder and read it; raises CustomError listing every problem."""
    problems: list[str] = []
    if not folder.is_dir():
        raise CustomError([f"{folder}: not a folder"])
    files = _files(folder, problems)
    problems += [f"{name}: missing" for name in sorted(TOP_FILES - set(files))]
    if len(files) > MAX_FILES:
        problems.append(f"more than {MAX_FILES} files")
    if sum((folder / rel).stat().st_size for rel in files) > MAX_TOTAL:
        problems.append(f"larger than {MAX_TOTAL // (1024 * 1024)} MB in total")
    if problems:
        raise CustomError(problems)
    media = [rel[len(MEDIA_DIR) + 1:] for rel in files if rel.startswith(MEDIA_DIR + "/")]
    for name in media:
        _check_media(folder, f"{MEDIA_DIR}/{name}", problems)
    less = _text(folder, "lumen-custom.less", problems)
    if less:
        _check_less(less, problems)
    css = _text(folder, "lumen-custom.css", problems)
    if css and (not css.startswith(CSS_HEAD) or re.search(r"</\s*style", css, re.IGNORECASE)):
        problems.append(f"lumen-custom.css: not a compiled Lumen override (it must start with "
                        f"'{CSS_HEAD.strip()}' and contain no </style>)")
    name = ""
    try:
        tokens = json.loads(_text(folder, "lumen.tokens.json", problems) or "null")
        if not isinstance(tokens, dict) or tokens.get("version") != 1:
            problems.append("lumen.tokens.json: not a Lumen token file of version 1")
        else:
            name = str(tokens.get("meta", {}).get("name", ""))[:200]
    except ValueError:
        problems.append("lumen.tokens.json: not valid JSON")
    branding: dict[str, str] = {}
    try:
        raw = json.loads(_text(folder, "branding.json", problems) or "null")
    except ValueError:
        raw = None
    if not isinstance(raw, dict) or set(raw) != set(BRANDING_KEYS):
        problems.append(f"branding.json: must be an object with exactly {', '.join(BRANDING_KEYS)}")
    else:
        for key in BRANDING_KEYS:
            branding[key] = _check_branding(raw[key], key, set(media), skin_images, problems)
    if problems:
        raise CustomError(problems)
    return Custom(folder=folder, name=re.sub(r"[^\x20-\x7e]", "", name), sha256=folder_digest(folder) or "",
                  less=less, css=css, branding=branding, media=tuple(media))


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """Unpack a customizer ZIP into ``dest`` (an empty folder) without trusting its paths. The files
    may sit at the top or inside one folder."""
    problems: list[str] = []
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CustomError([f"{zip_path}: not a ZIP file ({exc})"]) from exc
    with archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES:
            raise CustomError([f"{zip_path}: more than {MAX_FILES} files"])
        if sum(i.file_size for i in infos) > MAX_TOTAL:
            raise CustomError([f"{zip_path}: larger than {MAX_TOTAL // (1024 * 1024)} MB unpacked"])
        names = [i.filename for i in infos]
        prefix = ""
        if names and all("/" in n for n in names):
            first = names[0].split("/", 1)[0] + "/"
            if all(n.startswith(first) for n in names) and first + "lumen.tokens.json" in names:
                prefix = first
        for info in infos:
            rel = info.filename[len(prefix):]
            parts = rel.split("/")
            if (info.filename.startswith("/") or "\\" in rel or any(p in ("", ".", "..") for p in parts)
                    or len(parts) > 2 or (info.external_attr >> 16) & 0o170000 == 0o120000):
                problems.append(f"{info.filename}: unsafe path or link")
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "xb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
    if problems:
        raise CustomError(problems)
    return dest


def read_source(path: Path, skin_images: Path, tmp: Path) -> Custom:
    """A ZIP or a customization folder (for example a backup), checked."""
    if path.is_dir():
        return load(path, skin_images)
    folder = tmp / "unpacked"
    folder.mkdir()
    extract_zip(path, folder)
    return load(folder, skin_images)


def copy_to(custom: Custom, dest: Path) -> None:
    """Write exactly the checked files of a customization to ``dest`` (a new folder)."""
    dest.mkdir(parents=True)
    for name in sorted(TOP_FILES | OPTIONAL_FILES):
        if (custom.folder / name).is_file():
            shutil.copyfile(custom.folder / name, dest / name)
    if custom.media:
        (dest / MEDIA_DIR).mkdir()
        for name in custom.media:
            shutil.copyfile(custom.folder / MEDIA_DIR / name, dest / MEDIA_DIR / name)


def new_temp_dir() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="lumen-mail-custom-")


# ---------------------------------------------------------------------------------------------
# What a build does with it
# ---------------------------------------------------------------------------------------------

FOOTER_SCRIPT_RE = re.compile(r'<script src="/lumen\.js"[^>]*></script>')


def footer_script(branding: dict[str, str]) -> str:
    """The lumen.js tag of templates/includes/footer.html for a customization."""
    attrs = ['src="/lumen.js"']
    for key, attr in (("app", "data-src-app"), ("login", "data-src-login"), ("compact", "data-src-compact")):
        if branding[key]:
            attrs.append(f'{attr}="{html.escape(branding[key], quote=True)}"')
    attrs.append(f'data-theme-light="{branding["themeLight"]}"')
    attrs.append(f'data-theme-dark="{branding["themeDark"]}"')
    if branding["productName"]:
        attrs.append(f'data-alt="{html.escape(branding["productName"], quote=True)}"')
    return f"<script {' '.join(attrs)}></script>"


def apply_to_skin(custom: Custom, skin: Path) -> None:
    """Before the compile: the uploads, the lumen.js tag and the favicon of meta.json."""
    if custom.media:
        (skin / "images" / MEDIA_DIR).mkdir(parents=True, exist_ok=True)
        for name in custom.media:
            shutil.copyfile(custom.folder / MEDIA_DIR / name, skin / "images" / MEDIA_DIR / name)
    footer = skin / "templates" / "includes" / "footer.html"
    text = footer.read_text(encoding="utf-8")
    new, count = FOOTER_SCRIPT_RE.subn(lambda _m: footer_script(custom.branding), text, count=1)
    if count != 1:
        raise LumenError("templates/includes/footer.html: the lumen.js tag was not found")
    footer.write_text(new, encoding="utf-8")
    meta_path = skin / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    config = meta.setdefault("config", {})
    if custom.branding["favicon"]:
        config["favicon"] = custom.branding["favicon"]
    else:
        config.pop("favicon", None)
    meta["meta"] = {
        "theme-color": [
            {"content": custom.branding["themeLight"], "media": "(prefers-color-scheme: light)"},
            {"content": custom.branding["themeDark"], "media": "(prefers-color-scheme: dark)"},
        ],
        "msapplication-navbutton-color": custom.branding["themeDark"],
    }
    meta_path.write_text(json.dumps(meta, indent="\t") + "\n", encoding="utf-8")
