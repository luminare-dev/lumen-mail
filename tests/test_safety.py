"""Production safety: privilege handling as root, links planted by the Roundcube owner, the
restore sources, the outage path, deferrals, the re-check after settling and durable writes.

Like test_lifecycle.py, everything runs in temporary folders against a FAKE Roundcube tree with
the Python stand-in compiler. Tests that need root (chown to another user) are skipped otherwise;
the privilege drop itself is never performed in the test process (drop_to is mocked).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import os
import shutil
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from fake_roundcube import ROOT, write
from test_lifecycle import FAIL_ENV, LifecycleCase, run_cli, wipe

sys.path.insert(0, str(ROOT / "generator"))

from lumen_mail import cli, fsops, privileges  # noqa: E402
from lumen_mail.lifecycle import (DEFERRAL_WARN_SECONDS, EXIT_ERROR, EXIT_OK, EXIT_TEMPFAIL,  # noqa: E402
                                  SCRATCH_NAME, integrity_problems, read_stamp)
from lumen_mail.log import Log  # noqa: E402
from lumen_mail.state import SyncState, atomic_write  # noqa: E402
from lumen_mail.util import LumenError  # noqa: E402

ROOT_ONLY = unittest.skipUnless(os.geteuid() == 0, "needs root (chown to another user)")
OTHER = (65534, 65534)   # nobody:nogroup, a user that is neither root nor the test runner
LUMEN_CONFIG = "<?php\n$config['skin'] = 'lumen';\n"


class PlantedLinksTest(LifecycleCase):
    """What a compromised Roundcube owner could plant must never be followed."""

    def setUp(self) -> None:
        super().setUp()
        self.victim = self.tmp / "victim"
        write(self.victim / "file.txt", "keep me\n")
        write(self.victim / "dir" / "canary", "keep me too\n")

    def victim_intact(self) -> None:
        self.assertEqual((self.victim / "file.txt").read_text(), "keep me\n")
        self.assertEqual((self.victim / "dir" / "canary").read_text(), "keep me too\n")

    def test_a_linked_lock_is_refused(self):
        self.install()
        self.state.lock.unlink()
        os.symlink(self.victim / "file.txt", self.state.lock)
        with self.assertRaises(LumenError) as ctx:
            self.lc().request_rebuild()
        self.assertIn("symbolic link", str(ctx.exception))
        self.victim_intact()

    def test_a_linked_scratch_folder_is_refused_and_never_emptied(self):
        self.install()
        os.symlink(self.victim / "dir", self.rc / SCRATCH_NAME)
        with self.assertRaises(LumenError) as ctx:
            self.lc().sync(rebuild=True)
        self.assertIn("not a plain folder", str(ctx.exception))
        self.victim_intact()

    def test_only_run_folders_are_removed_from_the_scratch_folder(self):
        self.install()
        write(self.rc / SCRATCH_NAME / "run-old" / "x", "x")
        write(self.rc / SCRATCH_NAME / "something-else", "keep")
        self.assertEqual(self.lc().sync(), EXIT_OK)
        self.assertFalse((self.rc / SCRATCH_NAME / "run-old").exists())
        self.assertTrue((self.rc / SCRATCH_NAME / "something-else").exists())
        self.assertIn("leaving", self.logbuf.getvalue())

    @ROOT_ONLY
    def test_a_scratch_folder_of_another_user_is_refused(self):
        self.install()
        (self.rc / SCRATCH_NAME).mkdir()
        os.chown(self.rc / SCRATCH_NAME, *OTHER)
        with self.assertRaises(LumenError) as ctx:
            self.lc().sync(rebuild=True)
        self.assertIn("belongs to uid 65534", str(ctx.exception))

    def test_a_linked_skins_folder_is_refused(self):
        self.install()
        real = self.rc / "skins-real"
        (self.rc / "skins").rename(real)
        os.symlink(real, self.rc / "skins")
        with self.assertRaises(LumenError) as ctx:
            self.lc().install()
        self.assertIn("not a plain folder", str(ctx.exception))

    def test_notes_and_requests_replace_a_planted_link_instead_of_writing_through_it(self):
        self.install()
        for path in (self.state.rollback_notes, self.state.rebuild_request, self.state.sync_state):
            if path.exists():
                path.unlink()
            os.symlink(self.victim / "file.txt", path)
        self.assertEqual(self.lc().request_rebuild(), EXIT_OK)
        self.lc().write_notes("notes\n")
        state = SyncState.load(self.state)
        state.hold = {"since": "now"}
        state.save(self.state)
        self.victim_intact()
        for path in (self.state.rollback_notes, self.state.rebuild_request, self.state.sync_state):
            self.assertFalse(path.is_symlink(), path)

    def test_set_tree_modes_refuses_links(self):
        tree = self.tmp / "tree"
        write(tree / "a.txt", "a")
        os.symlink(self.victim / "file.txt", tree / "link")
        with self.assertRaises(LumenError):
            fsops.set_tree_modes(tree, None)

    def test_atomic_write_leaves_no_temporary_file(self):
        target = self.tmp / "out.txt"
        atomic_write(target, "x\n")
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".out.txt")], [])
        self.assertEqual(target.read_text(), "x\n")
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)


class PrivilegesTest(LifecycleCase):
    def args(self, command: str, **kw) -> argparse.Namespace:
        values = dict(command=command, roundcube=str(self.rc), state_dir=str(self.state.root), owner="auto",
                      dry_run=False)
        values.update(kw)
        return argparse.Namespace(**values)

    def test_a_linked_roundcube_path_is_refused(self):
        link = self.tmp / "rc-link"
        os.symlink(self.rc, link)
        with self.assertRaises(privileges.PrivilegeError) as ctx:
            privileges.target_owner(link, "auto", strict=True)
        self.assertIn("--roundcube", " ".join(ctx.exception.details))

    def test_a_linked_skins_folder_is_refused(self):
        real = self.rc / "skins-real"
        (self.rc / "skins").rename(real)
        os.symlink(real, self.rc / "skins")
        with self.assertRaises(privileges.PrivilegeError):
            privileges.target_owner(self.rc, "auto", strict=False)

    def test_explicit_owners(self):
        self.assertIsNone(privileges.target_owner(self.rc, "", strict=True))
        self.assertIsNone(privileges.target_owner(self.rc, "0:0", strict=True))
        self.assertEqual(privileges.target_owner(self.rc, "65534:65534", strict=True), OTHER)

    @ROOT_ONLY
    def test_a_tree_of_root_is_refused_for_writers_and_kept_for_readers(self):
        self.assertEqual(os.lstat(self.rc / "skins").st_uid, 0)
        with self.assertRaises(privileges.PrivilegeError) as ctx:
            privileges.target_owner(self.rc, "auto", strict=True)
        self.assertIn("--owner", " ".join(ctx.exception.details))
        self.assertIsNone(privileges.target_owner(self.rc, "auto", strict=False))
        code, _out, err = run_cli("sync", "--roundcube", str(self.rc), "--state-dir", str(self.state.root),
                                  "--source", str(ROOT))
        self.assertEqual(code, 5, err)

    @ROOT_ONLY
    def test_root_prepares_the_state_folder_then_drops_to_the_owner_of_skins(self):
        os.chown(self.rc / "skins", *OTHER)
        write(self.state.root / "backups" / "x" / "lumen" / "meta.json", "{}")
        write(self.tmp / "victim.txt", "root's\n")
        os.symlink(self.tmp / "victim.txt", self.state.root / "lock")
        args = self.args("sync")
        with mock.patch.object(privileges, "drop_to") as drop:
            cli.continue_as_owner(args)
        drop.assert_called_once_with(OTHER)
        self.assertEqual(args.owner, "", "after the drop nothing is chowned")
        for path in (self.state.root, self.state.root / "backups" / "x" / "lumen" / "meta.json"):
            self.assertEqual((os.lstat(path).st_uid, os.lstat(path).st_gid), OTHER, path)
        self.assertEqual(os.stat(self.tmp / "victim.txt").st_uid, 0, "a planted link is never followed")

    @ROOT_ONLY
    def test_readers_drop_without_touching_the_state_folder(self):
        os.chown(self.rc / "skins", *OTHER)
        with mock.patch.object(privileges, "drop_to") as drop, \
                mock.patch.object(privileges, "prepare_state_root") as prep:
            cli.continue_as_owner(self.args("status"))
            cli.continue_as_owner(self.args("sync", dry_run=True))
            cli.continue_as_owner(self.args("build"))
            cli.continue_as_owner(self.args("verify"))
        self.assertEqual(drop.call_count, 3, "verify reads only and stays as it is")
        prep.assert_not_called()

    @ROOT_ONLY
    def test_a_linked_state_folder_is_refused(self):
        real = self.tmp / "state-real"
        real.mkdir()
        os.symlink(real, self.state.root)
        with self.assertRaises(privileges.PrivilegeError):
            privileges.prepare_state_root(self.state.root, OTHER)
        self.assertEqual(os.stat(real).st_uid, 0)

    @ROOT_ONLY
    def test_a_state_folder_in_a_folder_others_can_change_is_refused(self):
        loose = self.tmp / "loose"
        loose.mkdir()
        os.chmod(loose, 0o777)
        with self.assertRaises(privileges.PrivilegeError):
            privileges.prepare_state_root(loose / "state", OTHER)

    def test_unreadable_sources_get_a_clear_message(self):
        args = argparse.Namespace(source=str(ROOT), node_modules=None, palette=None)
        with mock.patch.object(cli.Sources, "locate", side_effect=PermissionError(13, "Permission denied", "/root/x")):
            with self.assertRaises(LumenError) as ctx:
                cli.sources_from(args)
        self.assertIn("install-runtime", " ".join(ctx.exception.details))

    @ROOT_ONLY
    def test_sources_out_of_reach_after_the_drop_are_named(self):
        src = self.tmp / "private" / "src"
        shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns("node_modules", ".git", "gallery", "dist"))
        os.chmod(self.tmp / "private", 0o700)
        args = argparse.Namespace(source=str(src), node_modules=None, palette=None)
        pid = os.fork()
        if pid == 0:                                   # the drop happens in a child only
            code = 0
            try:
                privileges.drop_to(OTHER)
                cli.sources_from(args)
            except LumenError as exc:
                code = 7 if "cannot read the lumen-mail sources" in str(exc) else 8
            except BaseException:
                code = 9
            os._exit(code)
        _pid, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 7)


class RestoreSourcesTest(LifecycleCase):
    def damage_last_good(self) -> None:
        with open(self.state.last_good / "lumen.js", "a", encoding="utf-8") as fh:
            fh.write("x")

    def test_the_newest_intact_backup_replaces_a_damaged_last_good(self):
        self.install()
        self.install()                       # the first build is now a backup
        before = read_stamp(self.skin)
        self.damage_last_good()
        self.simulate_keyhelp_update()
        os.environ[FAIL_ENV] = "1"           # a compile would fail: the restore needs none
        starts = self.compiler_starts()
        self.assertEqual(self.lc().sync(), EXIT_OK, self.logbuf.getvalue())
        self.assertEqual(self.compiler_starts(), starts)
        self.assertEqual(integrity_problems(self.skin), [])
        self.assertRegex(self.logbuf.getvalue(), r"restored skins/lumen from the backup \d{8}T\d{12}Z-replaced-install")
        self.assertEqual(read_stamp(self.skin)["lumen_version"], before["lumen_version"])
        self.assertEqual(integrity_problems(self.state.last_good), [], "last good is repaired from the restored copy")

    def test_backups_made_by_uninstall_are_never_restored(self):
        self.install()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lc().uninstall(force=True), EXIT_OK)
        state = SyncState.load(self.state)
        state.uninstalled = None              # even without the marker
        state.save(self.state)
        self.assertIsNone(self.lc().restore_source())

    def test_a_failed_copy_gives_a_readable_message(self):
        self.install()
        shutil.rmtree(self.skin)
        err = shutil.Error([(str(self.state.last_good / "a"), str(self.rc / "b"), "[Errno 27] File too large: 'b'")])
        with mock.patch("lumen_mail.lifecycle.copy_tree", side_effect=err):
            code = self.lc().sync()
        self.assertEqual(code, EXIT_TEMPFAIL)
        log = self.logbuf.getvalue()
        self.assertIn("could not restore skins/lumen from", log)
        self.assertIn("[Errno 27] File too large: 'b' (1 files)", log)
        self.assertNotIn("[(", log, "no raw Python list in the journal")
        self.assertFalse(any(p.name.startswith("run-") for p in (self.rc / SCRATCH_NAME).glob("*")))
        self.assertEqual(self.lc().sync(), EXIT_OK)


class OutageTest(LifecycleCase):
    """System skin lumen, no usable skins/lumen, nothing to restore: webmail is down."""

    def lose_everything(self, damaged_last_good: bool = False) -> None:
        self.install()
        if damaged_last_good:
            with open(self.state.last_good / "lumen.js", "a", encoding="utf-8") as fh:
                fh.write("x")
        else:
            shutil.rmtree(self.state.last_good)
        self.simulate_keyhelp_update()
        write(self.rc / "config" / "config.inc.php", LUMEN_CONFIG)

    def test_low_memory_does_not_defer_the_build_below_the_emergency_floor(self):
        self.lose_everything()
        starts = self.compiler_starts()
        self.assertEqual(self.lc(min_available_mb=300, meminfo=lambda: 200).sync(), EXIT_OK, self.logbuf.getvalue())
        self.assertEqual(self.compiler_starts(), starts + 1)
        self.assertEqual(integrity_problems(self.skin), [])
        self.assertIn("webmail is down", self.logbuf.getvalue())

    def test_too_little_memory_even_for_an_emergency_build_is_an_error_on_every_run(self):
        self.lose_everything(damaged_last_good=True)
        for _ in range(2):
            self.logbuf.truncate(0)
            self.logbuf.seek(0)
            self.assertEqual(self.lc(min_available_mb=300, meminfo=lambda: 120).sync(), EXIT_ERROR)
            self.assertIn("error: webmail is down: no usable skins/lumen", self.logbuf.getvalue())
        self.assertFalse(self.skin.exists())

    def test_the_back_off_does_not_apply_while_webmail_is_down(self):
        self.lose_everything()
        os.environ[FAIL_ENV] = "1"
        self.assertNotEqual(self.lc().sync(), EXIT_OK)
        self.assertIsNotNone(SyncState.load(self.state).failure)
        os.environ.pop(FAIL_ENV)
        starts = self.compiler_starts()
        self.assertEqual(self.lc().sync(), EXIT_OK, self.logbuf.getvalue())
        self.assertEqual(self.compiler_starts(), starts + 1, "no back-off while webmail is down")

    def test_a_failed_emergency_build_is_not_reported_as_try_again_later(self):
        self.lose_everything()
        os.environ[FAIL_ENV] = "1"
        code = self.lc().sync()
        self.assertNotIn(code, (EXIT_OK, EXIT_TEMPFAIL))
        self.assertIn("webmail is down", self.logbuf.getvalue())

    def test_a_missing_elastic_footer_keeps_lumen_out(self):
        self.install()
        self.simulate_keyhelp_update()
        (self.rc / "skins/elastic/templates/includes/footer.html").unlink()
        self.assertFalse(self.lc().extracted())
        self.assertEqual(self.lc(wait=0.2).sync(), EXIT_TEMPFAIL)
        self.assertFalse(self.skin.exists(), "Lumen's footer wrapper would include itself without Elastic's footer")
        write(self.rc / "config" / "config.inc.php", LUMEN_CONFIG)
        self.assertEqual(self.lc(wait=0.2).sync(), EXIT_ERROR)
        self.assertIn("webmail is down", self.logbuf.getvalue())


class DeferralAndRecheckTest(LifecycleCase):
    def test_a_long_deferral_is_logged_as_a_warning_every_six_hours(self):
        self.install()
        self.set_version("9.8.8")
        t0 = _dt.datetime(2026, 10, 22, 2, 0, tzinfo=_dt.timezone.utc)

        def run(hours: float) -> str:
            buf = io.StringIO()
            lc = self.lc(min_available_mb=300, meminfo=lambda: 250, log=Log(stream=buf, quiet=True),
                         now=lambda: t0 + _dt.timedelta(hours=hours))
            self.assertEqual(lc.sync(), EXIT_TEMPFAIL)
            return buf.getvalue()

        first = run(0)
        self.assertIn("rebuild deferred", first, "the first deferral is a notice")
        self.assertNotIn("warning", first)
        self.assertEqual(run(1), "")
        self.assertIn("warning: rebuild deferred", run(DEFERRAL_WARN_SECONDS / 3600 + 0.1))
        self.assertEqual(run(7), "", "not again within the next six hours")
        self.assertIn("deferred since 2026-10-22T02:00:00Z", run(12.5))

    def test_a_digest_of_a_half_extracted_tree_does_not_cause_a_rebuild(self):
        self.install()
        lc = self.lc()
        real = lc.wanted
        calls = {"n": 0}

        def wanted(rc):
            calls["n"] += 1
            want = real(rc)
            if calls["n"] <= 2:              # the first look, while KeyHelp is still extracting
                return want.__class__(want.roundcube_version, "sha256:partial", want.lumen_version, want.source_digest)
            return want

        starts = self.compiler_starts()
        with mock.patch.object(lc, "wanted", side_effect=wanted):
            self.assertEqual(lc.sync(), EXIT_OK, self.logbuf.getvalue())
        self.assertEqual(self.compiler_starts(), starts, "the settled tree is current: no compile")
        self.assertGreaterEqual(calls["n"], 3)


class DurabilityTest(LifecycleCase):
    def test_new_builds_are_flushed_and_the_fast_restore_is_not(self):
        with mock.patch("lumen_mail.lifecycle.fsync_tree", wraps=fsops.fsync_tree) as tree, \
                mock.patch("lumen_mail.lifecycle.fsync_dir", wraps=fsops.fsync_dir) as folder:
            self.install()
            self.assertGreaterEqual(tree.call_count, 2, "the staged build and the last good copy")
            self.assertGreaterEqual(folder.call_count, 2, "skins/ and the state folder after the renames")
            tree.reset_mock()
            wipe(self.rc)
            self.simulate_keyhelp_update()
            self.assertEqual(self.lc().sync(), EXIT_OK)
            tree.assert_not_called()


if __name__ == "__main__":
    unittest.main()
