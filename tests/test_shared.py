"""The shared token code is still the locked copy of the Hydrodactyl theme's (shared.lock)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SharedLockTest(unittest.TestCase):
    def test_copies_match_the_lock(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_shared.py")],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_changed_copy_is_reported(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_shared  # noqa: E402

        lock = check_shared.load_lock()
        lock["files"]["overlay/files/resources/lumen/presets/aurora.json"] = "0" * 64
        self.assertEqual(len(check_shared.verify(lock)), 1)


if __name__ == "__main__":
    unittest.main()
