"""apply-custom: put a customizer ZIP in place and rebuild skins/lumen.

Without --yes nothing is written: the ZIP (or folder) is checked and the command says what would
change. With --yes:

1. the current customization folder (``<state dir>/custom`` by default) is moved to
   ``<state dir>/custom-backups/<timestamp>/`` and the checked new one takes its place;
2. ``install`` runs as usual: build against the installed Elastic, verify, keep a backup of the
   current skins/lumen and swap the new build in;
3. if the install fails, the previous customization folder is put back (skins/lumen stays as it
   was, because install only swaps a build that passed verify).

``--reset`` moves the customization to the backups and installs the plain Lumen look.
Undo: apply-custom with the backup folder it printed (or --reset when there was none), or
``rollback`` for the skin itself.
"""

from __future__ import annotations

import datetime as _dt
import shutil
from dataclasses import replace
from pathlib import Path

from . import custom as _custom
from .lifecycle import Lifecycle
from .util import LumenError


def _describe(c: _custom.Custom, out) -> None:
    out(f"customization: {c.name or '(no name)'} ({c.sha256[:19]})")
    for key, value in c.branding.items():
        if value and key not in ("themeLight", "themeDark"):
            out(f"  {key}: {value}")
    for name in c.media:
        out(f"  file: custom/{name}")


def apply_custom(lc: Lifecycle, source: Path | None, *, reset: bool = False, yes: bool = False,
                 now: _dt.datetime | None = None, out=print) -> int:
    target = lc.sources.custom_dir
    if target is None:
        raise LumenError("no customization folder (--custom)")
    stamp = (now or _dt.datetime.now(_dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    backup = target.parent / "custom-backups" / stamp
    with _custom.new_temp_dir() as tmp_name:
        tmp = Path(tmp_name)
        if reset:
            new = None
            out("customization: none (reset to the plain Lumen look)")
        else:
            assert source is not None
            if not source.exists():
                raise LumenError(f"{source} does not exist (or the Roundcube owner cannot read it; copy it "
                                 "somewhere that user can read, such as /tmp)")
            new = _custom.read_source(source, lc.sources.skin_dir / "images", tmp)
            _describe(new, out)
        if not yes:
            if target.exists():
                out(f"dry run: would move {target} to {backup}")
            out(f"dry run: would {'remove' if reset else 'write'} {target}, then build, verify and install "
                f"skins/lumen in {lc.roundcube}; nothing was written (add --yes)")
            return 0
        had_previous = target.exists()
        if had_previous:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(backup))
            out(f"moved the previous customization to {backup}")
        if new is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            _custom.copy_to(new, target)
            out(f"wrote {target}")
        try:
            code = replace(lc, dry_run=False).install()
        except BaseException:
            code = None
            _restore(target, backup if had_previous else None, out)
            raise
        if code != 0:
            _restore(target, backup if had_previous else None, out)
            return code
    undo = f"apply-custom {backup} --yes" if had_previous else "apply-custom --reset --yes"
    out(f"done. Undo: lumen-mail {undo} --roundcube {lc.roundcube}")
    return 0


def _restore(target: Path, backup: Path | None, out) -> None:
    if target.exists():
        shutil.rmtree(target)
    if backup is not None:
        shutil.move(str(backup), str(target))
    out(f"the install failed; the previous customization is back in {target} (skins/lumen was not changed)")
