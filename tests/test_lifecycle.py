"""Tests for install, check, sync, rollback and uninstall against a FAKE Roundcube tree.

Everything runs in temporary folders with the Python stand-in compiler; nothing touches a real
Roundcube, /var/lib or systemd. A KeyHelp update is simulated the way KeyHelp does it: remove
everything in the Roundcube root except dot entries ("rm -rf <root>/*"), then write a fresh tree.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import sys
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from fake_roundcube import FAKE_VERSION, ROOT, FakeTreeCase, make_roundcube, write

sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail import STAMP_NAME  # noqa: E402
from lumen_mail import fsops  # noqa: E402
from lumen_mail.build import BuildOptions, build  # noqa: E402
from lumen_mail.cli import main as cli_main  # noqa: E402
from lumen_mail.lifecycle import (EXIT_COMPILE, EXIT_NOT_INSTALLED, EXIT_OK, EXIT_SYNC_NEEDED,  # noqa: E402
                                  EXIT_TEMPFAIL, SCRATCH_NAME, Lifecycle, RefusedError, integrity_problems,
                                  read_stamp)
from lumen_mail.log import Log  # noqa: E402
from lumen_mail.sources import Sources  # noqa: E402
from lumen_mail.state import BusyError, StatePaths, SyncState, locked  # noqa: E402
from lumen_mail.verify import verify  # noqa: E402
from lumen_mail.roundcube import Roundcube  # noqa: E402

FAIL_ENV = "STUB_COMPILER_FAIL"
MARK_ENV = "STUB_COMPILER_MARK"


def wipe(rc: Path) -> None:
    """What "rm -rf <rc>/*" does: every entry except the ones starting with a dot."""
    for child in rc.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


class LifecycleCase(FakeTreeCase):
    def setUp(self) -> None:
        super().setUp()
        self.state = StatePaths(self.tmp / "state")
        self.logbuf = io.StringIO()
        self.mark = self.tmp / "compiler-starts.txt"
        env = mock.patch.dict(os.environ, {MARK_ENV: str(self.mark)})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(FAIL_ENV, None)
        os.environ.pop("LUMEN_MAIL_STATE_DIR", None)
        os.environ.pop("STATE_DIRECTORY", None)

    def lc(self, **kw) -> Lifecycle:
        opts = dict(roundcube=self.rc, state=self.state, sources=Sources.locate(ROOT), log=Log(stream=self.logbuf),
                    owner_spec="", settle=0.0, wait=2.0, min_available_mb=0, lock_timeout=0.0,
                    compiler=self.compiler, work_dir=self.tmp / "work", palette="none")
        opts.update(kw)
        (self.tmp / "work").mkdir(exist_ok=True)
        return Lifecycle(**opts)

    def compiler_starts(self) -> int:
        return len(self.mark.read_text().splitlines()) if self.mark.exists() else 0

    def install(self, **kw) -> Lifecycle:
        lc = self.lc(**kw)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(lc.install(), EXIT_OK, self.logbuf.getvalue())
        return lc

    def set_version(self, version: str) -> None:
        write(self.rc / "program/include/iniset.php", f"<?php\ndefine('RCMAIL_VERSION', '{version}');\n")

    def simulate_keyhelp_update(self, version: str = FAKE_VERSION) -> None:
        wipe(self.rc)
        make_roundcube(self.tmp, version=version)

    @property
    def skin(self) -> Path:
        return self.rc / "skins" / "lumen"

    def notices(self) -> list[str]:
        return [line for line in self.logbuf.getvalue().splitlines() if line]


class InstallTest(LifecycleCase):
    def test_install_into_a_fresh_tree(self):
        lc = self.lc()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(lc.install(), EXIT_OK)
        self.assertEqual(verify(self.skin, Roundcube.at(self.rc), Sources.locate(ROOT)), [])
        self.assertEqual(read_stamp(self.state.last_good), read_stamp(self.skin))
        self.assertTrue(self.state.rollback_notes.is_file())
        self.assertIn("uninstall", out.getvalue())
        for path in [self.skin, *self.skin.rglob("*")]:
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o755 if path.is_dir() else 0o644, path)
        self.assertFalse((self.rc / SCRATCH_NAME).exists(), "the staging folder must be gone")
        self.assertEqual((self.skin / "LICENSE").read_text(), (ROOT / "LICENSE").read_text())
        self.assertEqual((self.skin / "NOTICE").read_text(), (ROOT / "NOTICE").read_text())

    def test_reinstall_swaps_atomically_and_rotates_backups(self):
        calls = []
        real = fsops.exchange

        def spy(a, b):
            calls.append((Path(a), Path(b)))
            return real(a, b)

        self.install(keep=3)
        with mock.patch("lumen_mail.fsops.exchange", side_effect=spy):
            for _ in range(5):
                self.install(keep=3)
        backups = fsops.list_backups(self.state.backups)
        self.assertEqual(len(backups), 3, [b.name for b in backups])
        for b in backups:
            self.assertTrue(b.name.endswith("-replaced-install"))
            self.assertEqual(integrity_problems(b / "lumen"), [])
        self.assertTrue(any(target == self.skin for _new, target in calls), "skins/lumen must be swapped in place")
        self.assertEqual(integrity_problems(self.skin), [])

    def test_swap_without_renameat2_still_replaces_the_folder(self):
        self.install()
        before = read_stamp(self.skin)["built_at"]
        time.sleep(1.1)
        with mock.patch("lumen_mail.fsops.exchange", return_value=False):
            self.install()
        self.assertNotEqual(read_stamp(self.skin)["built_at"], before)
        self.assertEqual(len(fsops.list_backups(self.state.backups)), 1)

    def test_owner_step_runs_as_root_with_the_owner_of_skins(self):
        skins = self.rc / "skins"
        want = (skins.stat().st_uid, skins.stat().st_gid)
        chowned = []
        with mock.patch("lumen_mail.fsops.os.geteuid", return_value=0), \
                mock.patch("lumen_mail.fsops.os.chown", side_effect=lambda p, u, g: chowned.append((str(p), u, g))), \
                mock.patch("lumen_mail.lifecycle.os.chown", side_effect=lambda p, u, g: chowned.append((str(p), u, g))):
            self.install(owner_spec="auto")
        targets = {p for p, _u, _g in chowned}
        self.assertTrue(chowned)
        self.assertTrue(all((u, g) == want for _p, u, g in chowned))
        self.assertTrue(any(p.endswith("/meta.json") for p in targets))
        self.assertTrue(any(p.startswith(str(self.state.root)) for p in targets), "the state folder gets the owner too")

    def test_owner_is_left_alone_when_not_root(self):
        with mock.patch("lumen_mail.fsops.os.geteuid", return_value=1000):
            self.assertIsNone(fsops.resolve_owner("auto", self.rc / "skins"))
        self.assertIsNone(fsops.resolve_owner("", self.rc / "skins"))

    def test_dry_run_writes_nothing(self):
        lc = self.lc(dry_run=True)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(lc.install(), EXIT_OK)
        self.assertIn("dry run: would build", out.getvalue())
        self.assertFalse(self.skin.exists())
        self.assertFalse(self.state.root.exists())
        self.assertEqual(self.compiler_starts(), 0)

    def test_install_from_a_built_folder(self):
        built = build(BuildOptions(roundcube=self.rc, out=self.tmp / "pkg/lumen", sources=Sources.locate(ROOT),
                                   palette=False, compiler=self.compiler, quiet=True)).out
        lc = self.lc()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(lc.install(from_dir=built), EXIT_OK)
        self.assertEqual(read_stamp(self.skin), read_stamp(built))
        (built / "lumen.js").write_text("// changed\n")
        with self.assertRaises(Exception) as ctx, redirect_stdout(io.StringIO()):
            lc.install(from_dir=built)
        self.assertIn("does not pass verify", str(ctx.exception))

    def test_install_from_a_package_for_another_release_needs_allow_mismatch(self):
        built = build(BuildOptions(roundcube=self.rc, out=self.tmp / "pkg/lumen", sources=Sources.locate(ROOT),
                                   palette=False, compiler=self.compiler, quiet=True)).out
        self.set_version("9.8.8")
        with self.assertRaises(Exception), redirect_stdout(io.StringIO()):
            self.lc().install(from_dir=built)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lc().install(from_dir=built, allow_mismatch=True), EXIT_OK)

    def test_rollback_restores_the_previous_build_and_holds_it(self):
        self.install()
        first = read_stamp(self.skin)
        time.sleep(1.1)
        self.install()
        lc = self.lc()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(lc.rollback(), EXIT_OK)
        self.assertEqual(read_stamp(self.skin)["built_at"], first["built_at"])
        self.assertEqual(read_stamp(self.state.last_good)["built_at"], first["built_at"])
        self.assertIsNotNone(SyncState.load(self.state).hold)
        # held: a stale stamp does not start a rebuild
        self.set_version("9.8.8")
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertEqual(read_stamp(self.skin)["built_at"], first["built_at"])
        code, report = self.lc().check()
        self.assertEqual(code, EXIT_OK)
        self.assertIn("hold", report)
        self.assertEqual(self.lc().resume(), EXIT_OK)
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertEqual(read_stamp(self.skin)["roundcube_version"], "9.8.8")


class CheckTest(LifecycleCase):
    def test_exit_codes(self):
        self.assertEqual(self.lc().check()[0], EXIT_NOT_INSTALLED)
        self.install()
        self.assertEqual(self.lc().check()[0], EXIT_OK)
        self.set_version("9.8.8")
        code, report = self.lc().check()
        self.assertEqual(code, EXIT_SYNC_NEEDED)
        self.assertIn("built for Roundcube 9.8.7, installed is 9.8.8", report["reasons"])

    def test_damaged_skin_or_missing_last_good_need_a_sync(self):
        self.install()
        (self.skin / "lumen.js").unlink()
        self.assertEqual(self.lc().check()[0], EXIT_SYNC_NEEDED)
        self.install()
        shutil.rmtree(self.state.last_good)
        code, report = self.lc().check()
        self.assertEqual(code, EXIT_SYNC_NEEDED)
        self.assertIn("the last good copy is missing or differs from skins/lumen", report["reasons"])

    def test_incomplete_tree_and_missing_root(self):
        self.install()
        wipe(self.rc)
        self.assertEqual(self.lc().check()[0], EXIT_SYNC_NEEDED)
        code, out, err = run_cli("check", "--roundcube", str(self.tmp / "nope"), "--state-dir", str(self.state.root))
        self.assertEqual(code, 1, err)

    def test_cli_check_json(self):
        self.install()
        code, out, _err = run_cli("check", "--roundcube", str(self.rc), "--state-dir", str(self.state.root),
                                  "--source", str(ROOT), "--no-palette", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "ok")


class SyncTest(LifecycleCase):
    def test_noop_is_cheap_and_silent(self):
        self.install()
        starts = self.compiler_starts()
        state_files = sorted(p.name for p in self.state.root.iterdir())
        self.logbuf.truncate(0)
        self.logbuf.seek(0)
        t0 = time.monotonic()
        for _ in range(5):
            self.assertEqual(self.lc(log=Log(stream=self.logbuf, quiet=True)).sync(), EXIT_OK)
        per_run = (time.monotonic() - t0) / 5
        self.assertEqual(self.compiler_starts(), starts, "a current skin must not start the compiler")
        self.assertEqual(self.logbuf.getvalue(), "", "nothing above info level when there is nothing to do")
        self.assertEqual(sorted(p.name for p in self.state.root.iterdir()), state_files, "the no-op writes nothing")
        self.assertLess(per_run, 1.0, f"a no-op sync took {per_run:.3f} s")

    def test_fast_restore_after_a_keyhelp_update(self):
        self.install()
        before = read_stamp(self.skin)
        starts = self.compiler_starts()
        self.simulate_keyhelp_update()
        self.assertFalse(self.skin.exists())
        os.environ[FAIL_ENV] = "1"          # a compile would fail: proves the restore needs none
        t0 = time.monotonic()
        self.assertEqual(self.lc().sync(), EXIT_OK, self.logbuf.getvalue())
        elapsed = time.monotonic() - t0
        self.assertEqual(read_stamp(self.skin), before)
        self.assertEqual(integrity_problems(self.skin), [])
        self.assertEqual(self.compiler_starts(), starts)
        self.assertLess(elapsed, 2.0, f"restore took {elapsed:.3f} s")
        self.assertRegex(self.logbuf.getvalue(), r"restored skins/lumen from the last good build in \d+\.\d{3} s")

    def test_restore_waits_for_the_extraction(self):
        self.install()
        before = read_stamp(self.skin)
        wipe(self.rc)                         # the run starts while the tree is gone (path unit fires on delete)

        def extract_later():
            time.sleep(0.4)
            make_roundcube(self.tmp)

        t = threading.Thread(target=extract_later)
        t.start()
        try:
            self.assertEqual(self.lc(wait=10.0).sync(), EXIT_OK, self.logbuf.getvalue())
        finally:
            t.join()
        self.assertEqual(read_stamp(self.skin), before)

    def test_incomplete_tree_times_out_with_75(self):
        self.install()
        wipe(self.rc)
        self.assertEqual(self.lc(wait=0.3).sync(), EXIT_TEMPFAIL)
        self.assertIn("still incomplete", self.logbuf.getvalue())

    def test_restore_retries_while_skins_is_not_writable(self):
        self.install()
        before = read_stamp(self.skin)
        shutil.rmtree(self.skin)
        lc = self.lc()
        real = lc.restore_last_good
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError(13, "Permission denied", str(self.rc / "skins"))
            return real()

        with mock.patch.object(lc, "restore_last_good", side_effect=flaky):
            self.assertEqual(lc.sync(), EXIT_OK)
        self.assertEqual(calls["n"], 3)
        self.assertEqual(read_stamp(self.skin), before)

    def test_stale_stamp_rebuilds_after_a_new_release(self):
        self.install()
        starts = self.compiler_starts()
        self.simulate_keyhelp_update(version="9.8.8")
        self.assertEqual(self.lc().sync(), EXIT_OK, self.logbuf.getvalue())
        self.assertEqual(read_stamp(self.skin)["roundcube_version"], "9.8.8")
        self.assertEqual(read_stamp(self.state.last_good), read_stamp(self.skin))
        self.assertEqual(self.compiler_starts(), starts + 1)
        self.assertTrue(any(b.name.endswith("-replaced-stale") for b in fsops.list_backups(self.state.backups)))
        log = self.logbuf.getvalue()
        self.assertLess(log.index("restored skins/lumen"), log.index("rebuilt skins/lumen for Roundcube 9.8.8"))
        self.assertEqual(verify(self.skin, Roundcube.at(self.rc), Sources.locate(ROOT)), [])

    def test_stale_stamp_without_a_wipe(self):
        self.install()
        self.set_version("9.9.0")
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertEqual(read_stamp(self.skin)["roundcube_version"], "9.9.0")

    def test_failed_rebuild_keeps_the_last_good_build_and_backs_off(self):
        self.install()
        before = read_stamp(self.skin)
        self.simulate_keyhelp_update(version="9.8.8")
        os.environ[FAIL_ENV] = "1"
        starts = self.compiler_starts()
        self.assertEqual(self.lc().sync(), EXIT_COMPILE)
        self.assertEqual(read_stamp(self.skin), before, "the restored build stays active")
        self.assertEqual(integrity_problems(self.skin), [])
        self.assertIn("rebuild failed (exit 4)", self.logbuf.getvalue())
        failure = SyncState.load(self.state).failure
        self.assertEqual(failure["attempts"], 1)
        self.assertEqual(self.compiler_starts(), starts + 1)
        # within the back-off: no new compile, exit 75
        self.assertEqual(self.lc().sync(), EXIT_TEMPFAIL)
        self.assertEqual(self.compiler_starts(), starts + 1)
        # new inputs: tried again at once, and it works now
        del os.environ[FAIL_ENV]
        self.set_version("9.8.9")
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertEqual(read_stamp(self.skin)["roundcube_version"], "9.8.9")
        self.assertIsNone(SyncState.load(self.state).failure)

    def test_an_os_error_during_the_rebuild_backs_off_too(self):
        self.install()
        self.set_version("9.8.8")
        lc = self.lc()
        with mock.patch.object(lc, "build_staged", side_effect=OSError(28, "No space left on device")):
            self.assertEqual(lc.sync(), 1)
        self.assertEqual(SyncState.load(self.state).failure["attempts"], 1)
        self.assertIn("No space left on device", self.logbuf.getvalue())
        self.assertEqual(self.lc().sync(), EXIT_TEMPFAIL, "within the back-off")

    def test_too_little_memory_defers_the_rebuild(self):
        self.install()
        self.set_version("9.8.8")
        starts = self.compiler_starts()
        lc = self.lc(min_available_mb=400, meminfo=lambda: 120)
        self.assertEqual(lc.sync(), EXIT_TEMPFAIL)
        self.assertEqual(self.compiler_starts(), starts)
        self.assertEqual(SyncState.load(self.state).deferred["kind"], "memory")
        self.assertEqual(self.logbuf.getvalue().count("rebuild deferred"), 1)
        quiet = io.StringIO()
        self.assertEqual(self.lc(min_available_mb=400, meminfo=lambda: 120, log=Log(stream=quiet, quiet=True)).sync(),
                         EXIT_TEMPFAIL)
        self.assertEqual(quiet.getvalue(), "", "a repeated deferral is logged at info level only")
        self.assertEqual(self.lc(min_available_mb=400, meminfo=lambda: 900).sync(), EXIT_OK)
        self.assertIsNone(SyncState.load(self.state).deferred)

    def test_lock_contention_exits_75(self):
        self.install()
        with locked(self.state.lock, 0):
            with self.assertRaises(BusyError):
                self.lc().sync()
            code, _out, _err = run_cli("sync", "--roundcube", str(self.rc), "--state-dir", str(self.state.root),
                                       "--lock-timeout", "0", "--source", str(ROOT), "--no-palette")
            self.assertEqual(code, EXIT_TEMPFAIL)
        self.assertEqual(self.lc().sync(), EXIT_OK)

    def test_leftovers_of_an_interrupted_run_are_removed(self):
        self.install()
        write(self.rc / SCRATCH_NAME / "run-abc" / "lumen" / "meta.json", "{}")
        write(self.state.root / ".last-good.new-123" / "x", "x")
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertFalse((self.rc / SCRATCH_NAME).exists())
        self.assertFalse((self.state.root / ".last-good.new-123").exists())

    def test_request_rebuild(self):
        self.install()
        starts = self.compiler_starts()
        self.assertEqual(self.lc().request_rebuild(), EXIT_OK)
        self.assertEqual(self.lc().check()[0], EXIT_SYNC_NEEDED)
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertEqual(self.compiler_starts(), starts + 1)
        self.assertFalse(self.state.rebuild_request.exists())

    def test_damaged_skin_is_replaced_and_kept_as_backup(self):
        self.install()
        (self.skin / "styles" / "styles.min.css").write_text("broken")
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertEqual(integrity_problems(self.skin), [])
        self.assertTrue(any(b.name.endswith("-replaced-broken") for b in fsops.list_backups(self.state.backups)))

    def test_missing_last_good_is_saved_from_a_current_skin(self):
        self.install()
        shutil.rmtree(self.state.last_good)
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertEqual(read_stamp(self.state.last_good), read_stamp(self.skin))

    def test_not_installed_is_a_quiet_noop(self):
        quiet = io.StringIO()
        self.assertEqual(self.lc(log=Log(stream=quiet, quiet=True)).sync(), EXIT_OK)
        self.assertEqual(quiet.getvalue(), "")
        self.assertFalse(self.skin.exists())
        self.assertEqual(self.compiler_starts(), 0)

    def test_lost_state_with_lumen_as_system_skin_builds_at_once(self):
        # The state folder is gone (no last good build) and an update removed skins/lumen while
        # lumen is the system skin: every page would fail, so sync builds instead of doing nothing.
        self.install()
        shutil.rmtree(self.state.root)
        self.simulate_keyhelp_update()
        write(self.rc / "config" / "config.inc.php",
              "<?php\n$config['des_key'] = 'SECRET-XYZ-123';\n$config[\"skin\"]  =  \"lumen\" ;\n")
        code, report = self.lc().check()
        self.assertEqual(code, EXIT_SYNC_NEEDED)
        self.assertIn("the system skin is lumen", " ".join(report["reasons"]))
        starts = self.compiler_starts()
        self.assertEqual(self.lc().sync(), EXIT_OK, self.logbuf.getvalue())
        self.assertEqual(self.compiler_starts(), starts + 1)
        self.assertEqual(integrity_problems(self.skin), [])
        self.assertEqual(read_stamp(self.state.last_good), read_stamp(self.skin))
        self.assertIn("building it now", self.logbuf.getvalue())
        self.assertNotIn("SECRET-XYZ-123", self.logbuf.getvalue())

    def test_lost_state_with_another_system_skin_stays_a_noop(self):
        self.install()
        shutil.rmtree(self.state.root)
        self.simulate_keyhelp_update()
        for config in ("<?php\n$config['skin'] = 'elastic';\n",
                       "<?php\n// $config['skin'] = 'lumen';\n$config['skin'] = 'elastic';\n",
                       "<?php\n/* $config['skin'] = 'lumen'; */\n"):
            write(self.rc / "config" / "config.inc.php", config)
            self.assertEqual(self.lc().check()[0], EXIT_NOT_INSTALLED, config)
            self.assertEqual(self.lc().sync(), EXIT_OK)
            self.assertFalse(self.skin.exists(), config)
        self.assertEqual(self.compiler_starts(), 1, "only the install compiled")

    def test_an_uninstall_is_respected_even_with_lumen_as_system_skin(self):
        self.install()
        write(self.rc / "config" / "config.inc.php", "<?php\n$config['skin'] = 'lumen';\n")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lc().uninstall(force=True), EXIT_OK)
        self.simulate_keyhelp_update()
        write(self.rc / "config" / "config.inc.php", "<?php\n$config['skin'] = 'lumen';\n")
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertFalse(self.skin.exists())

    def test_tree_change_during_a_run_triggers_another_pass(self):
        self.install()
        lc = self.lc()
        real = lc._sync_pass
        passes = []

        def pass_and_touch(force):
            passes.append(force)
            code = real(force)
            if len(passes) == 1:      # KeyHelp rewrites the config while this run is busy
                write(self.rc / "config" / "config.inc.php", "<?php\n$config['skin'] = 'lumen';\n")
            return code

        with mock.patch.object(lc, "_sync_pass", side_effect=pass_and_touch):
            self.assertEqual(lc.sync(), EXIT_OK)
        self.assertEqual(len(passes), 2)

    def test_dry_run_sync_changes_nothing(self):
        self.install()
        shutil.rmtree(self.skin)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.lc(dry_run=True).sync(), EXIT_OK)
        self.assertIn("would restore skins/lumen", out.getvalue())
        self.assertFalse(self.skin.exists())


class UninstallTest(LifecycleCase):
    def write_config(self, text: str) -> None:
        write(self.rc / "config" / "config.inc.php", text)

    def test_refused_while_lumen_is_the_system_skin(self):
        self.install()
        self.write_config("<?php\n$config['des_key'] = 'SECRET-XYZ-123';\n$config['skin'] = 'lumen';\n")
        with self.assertRaises(RefusedError):
            self.lc().uninstall()
        code, out, err = run_cli("uninstall", "--roundcube", str(self.rc), "--state-dir", str(self.state.root))
        self.assertEqual(code, 5)
        self.assertNotIn("SECRET-XYZ", out + err + self.logbuf.getvalue())
        self.assertTrue(self.skin.is_dir())

    def test_removes_the_skin_when_the_system_skin_is_elastic(self):
        self.install()
        self.write_config("<?php\n$config['skin'] = 'elastic';\n")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lc().uninstall(), EXIT_OK)
        self.assertFalse(self.skin.exists())
        self.assertFalse(self.state.last_good.exists())
        backups = fsops.list_backups(self.state.backups)
        self.assertTrue(backups[-1].name.endswith("-uninstall"))
        self.assertEqual(integrity_problems(backups[-1] / "lumen"), [])
        self.assertIn("now get the system skin", self.logbuf.getvalue())
        # sync does not bring it back
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertFalse(self.skin.exists())
        self.assertEqual(self.lc().check()[0], EXIT_NOT_INSTALLED)

    def test_force_and_unreadable_config(self):
        self.install()
        self.write_config("<?php\n$config['skin'] = 'lumen';\n")
        with mock.patch("lumen_mail.phpconfig.Path.read_text", side_effect=PermissionError(13, "Permission denied")):
            with self.assertRaises(RefusedError) as ctx:
                self.lc().uninstall()
        self.assertIn("cannot read", str(ctx.exception))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lc().uninstall(force=True), EXIT_OK)
        self.assertFalse(self.skin.exists())

    def test_no_config_falls_back_to_defaults(self):
        self.install()
        write(self.rc / "config" / "defaults.inc.php", "<?php\n$config['skin'] = 'elastic';\n")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lc().uninstall(), EXIT_OK)


class CliAndLogTest(LifecycleCase):
    def args(self, *extra: str) -> list[str]:
        return [*extra, "--roundcube", str(self.rc), "--state-dir", str(self.state.root), "--source", str(ROOT),
                "--no-palette"]

    def test_install_status_and_check_through_the_cli(self):
        code, out, err = run_cli(*self.args("install", "--owner", "", "--compiler", self.compiler,
                                            "--work-dir", str(self.tmp)))
        self.assertEqual(code, 0, err)
        self.assertIn("Undo:", out)
        code, out, _err = run_cli(*self.args("status"))
        self.assertEqual(code, 0)
        self.assertIn(f"Lumen {read_stamp(self.skin)['lumen_version']} for Roundcube {FAKE_VERSION}", out)
        self.assertIn("Check:       ok (exit 0)", out)
        code, out, _err = run_cli(*self.args("status", "--json"))
        info = json.loads(out)
        self.assertTrue(info["skin"]["intact"])
        self.assertEqual(info["check"]["exit_code"], 0)
        code, out, _err = run_cli(*self.args("check"))
        self.assertEqual((code, out.splitlines()[0][:29]), (0, "ok: skins/lumen is current (L"))

    def test_missing_roundcube_option_is_a_usage_error(self):
        with mock.patch.dict(os.environ, {"LUMEN_MAIL_ROUNDCUBE": ""}):
            code, _out, err = run_cli("check", "--state-dir", str(self.state.root))
        self.assertEqual(code, 2)
        self.assertIn("--roundcube is required", err)

    def test_journal_priorities(self):
        with open(self.tmp / "journal.txt", "w+", encoding="utf-8") as fh:
            st = os.fstat(fh.fileno())
            with mock.patch.dict(os.environ, {"JOURNAL_STREAM": f"{st.st_dev}:{st.st_ino}"}):
                log = Log(stream=fh)
                self.assertTrue(log.journal)
                log.notice("restored")
                log.error("broken\nsecond line")
                log.info("quiet")
            fh.seek(0)
            self.assertEqual(fh.read().splitlines(), ["<5>restored", "<3>broken", "<3>second line", "<6>quiet"])
        plain = io.StringIO()
        log = Log(stream=plain)
        self.assertFalse(log.journal)
        log.warning("careful")
        self.assertEqual(plain.getvalue(), "warning: careful\n")


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli_main(list(argv))
    return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
