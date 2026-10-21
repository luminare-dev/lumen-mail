"""Tests for scripts/package.py (release package) with a fake Roundcube and the stand-in compiler."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import shutil
import sys
import tarfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from fake_roundcube import FAKE_VERSION, ROOT, FakeTreeCase

spec = importlib.util.spec_from_file_location("lumen_package", ROOT / "scripts" / "package.py")
package = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(package)

VERSION = (ROOT / "version.txt").read_text().strip()


class PackageTest(FakeTreeCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1792540800"})
        env.start()
        self.addCleanup(env.stop)

    def build(self, out_name="dist"):
        with redirect_stderr(io.StringIO()):
            return package.build_package(self.rc, self.tmp / out_name, compiler=self.compiler)

    def test_archives_hold_one_lumen_folder_with_the_legal_files(self):
        tgz, zipf, sums = self.build()
        base = f"lumen-{VERSION}-roundcube-{FAKE_VERSION}"
        self.assertEqual((tgz.name, zipf.name), (f"{base}.tar.gz", f"{base}.zip"))
        with tarfile.open(tgz) as tar:
            names = tar.getnames()
            members = tar.getmembers()
        self.assertTrue(all(n == "lumen" or n.startswith("lumen/") for n in names))
        for rel in ("meta.json", "LICENSE", "NOTICE", "README.md", "lumen-build.stamp", "styles/styles.min.css",
                    "templates/includes/footer.html", "fonts/Sora-OFL.txt"):
            self.assertIn(f"lumen/{rel}", names)
        self.assertTrue(all(m.uid == 0 and m.gid == 0 and m.mtime == 1792540800 for m in members))
        self.assertTrue(all(m.mode == (0o755 if m.isdir() else 0o644) for m in members))
        with zipfile.ZipFile(zipf) as zf:
            self.assertEqual(sorted(n.rstrip("/") for n in zf.namelist()), sorted(names))
            self.assertIn("CC BY-SA 3.0", zf.read("lumen/styles/styles.css").decode()[:2000])
        sums_lines = sums.read_text().splitlines()
        for f in (tgz, zipf):
            self.assertIn(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}", sums_lines)

    def test_reproducible(self):
        a = self.build("a")
        b = self.build("b")
        for x, y in zip(a[:2], b[:2]):
            self.assertEqual(x.read_bytes(), y.read_bytes(), x.name)

    def test_sums_keep_other_files(self):
        out = self.tmp / "dist"
        out.mkdir()
        (out / "SHA256SUMS").write_text("abc  lumen-mail-0.1.0.tar.gz\n")
        self.build()
        self.assertIn("abc  lumen-mail-0.1.0.tar.gz", (out / "SHA256SUMS").read_text())

    def release_archive(self, extra: tarfile.TarInfo | None = None) -> Path:
        archive = self.tmp / "roundcubemail-test.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(self.rc, arcname="roundcubemail-9.8.7")
            if extra is not None:
                tar.addfile(extra, io.BytesIO(b"x"))
        return archive

    def test_fetch_checks_the_checksum_and_strips_the_top_folder(self):
        archive = self.release_archive()
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        with redirect_stderr(io.StringIO()):
            dest = package.fetch(self.tmp / "rc", "9.8.7", digest, archive)
        self.assertTrue((dest / "program" / "include" / "iniset.php").is_file())
        self.assertTrue((dest / "skins" / "elastic" / "meta.json").is_file())
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            package.fetch(self.tmp / "rc2", "9.8.7", "0" * 64, archive)
        self.assertFalse((self.tmp / "rc2").exists())

    def test_fetch_refuses_paths_outside_the_folder(self):
        evil = tarfile.TarInfo("roundcubemail-9.8.7/../../escape.txt")
        evil.size = 1
        archive = self.release_archive(evil)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        with self.assertRaises(tarfile.FilterError), redirect_stderr(io.StringIO()):
            package.fetch(self.tmp / "rc", "9.8.7", digest, archive)
        self.assertFalse((self.tmp / "escape.txt").exists())
        self.assertFalse((self.tmp / "rc").exists(), "a failed extraction leaves nothing behind")

    def test_cli_requires_version_and_sha_together(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            package.main(["fetch", "--dest", str(self.tmp / "x"), "--roundcube-version", "9.9.9"])

    def test_cli_build(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = package.main(["build", "--roundcube", str(self.rc), "--out", str(self.tmp / "d"),
                                 "--compiler", self.compiler])
        self.assertEqual(code, 0)
        self.assertIn(".tar.gz", out.getvalue())
        shutil.rmtree(self.tmp / "d")


if __name__ == "__main__":
    unittest.main()
