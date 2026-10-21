"""Static checks of the example systemd units in contrib/systemd/ (nothing is installed).

When systemd-analyze is available, the units are also verified from a temporary copy whose
ExecStart points at an existing binary (verify refuses a missing executable).
"""

from __future__ import annotations

import configparser
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNITS = ROOT / "contrib" / "systemd"
RC = "/home/keyhelp/www/roundcube"


def load(name: str) -> dict[str, dict[str, list[str]]]:
    """Unit file sections as {section: {key: [values in order]}} (keys may repeat)."""
    out: dict[str, dict[str, list[str]]] = {}
    section = None
    for raw in (UNITS / name).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            out.setdefault(section, {})
            continue
        key, _, value = line.partition("=")
        assert section is not None, raw
        out[section].setdefault(key, []).append(value)
    return out


class UnitsTest(unittest.TestCase):
    def test_service(self):
        u = load("lumen-mail-sync.service")
        svc, unit = u["Service"], u["Unit"]
        self.assertEqual(svc["Type"], ["oneshot"])
        self.assertEqual((svc["User"], svc["Group"]), (["keyhelp"], ["keyhelp"]))
        self.assertEqual(svc["ExecStart"], [f"/opt/lumen-mail/bin/lumen-mail sync --roundcube {RC}"])
        self.assertEqual(svc["SuccessExitStatus"], ["75"])
        self.assertEqual(svc["StateDirectory"], ["lumen-mail"])
        self.assertEqual(svc["LogLevelMax"], ["notice"])
        self.assertEqual(unit["StartLimitIntervalSec"], ["0"])
        self.assertEqual(svc["ProtectSystem"], ["strict"])
        self.assertEqual(svc["ProtectHome"], ["tmpfs"])
        self.assertEqual(svc["BindPaths"], [RC], "the Roundcube root, not skins/ (KeyHelp removes skins/)")
        self.assertNotIn("ReadWritePaths", svc)
        self.assertEqual(svc["PrivateNetwork"], ["yes"])
        self.assertEqual(svc["NoNewPrivileges"], ["yes"])
        self.assertEqual(svc["MemoryMax"], ["350M"])
        self.assertEqual(svc["OOMScoreAdjust"], ["1000"])
        self.assertEqual(svc["Nice"], ["19"])
        self.assertEqual(svc["IOSchedulingClass"], ["idle"])
        self.assertNotIn("MemoryDenyWriteExecute", svc, "Node's JIT needs W+X memory")
        self.assertNotIn("ProcSubset", svc, "the memory check reads /proc/meminfo")
        self.assertIn("NODE_OPTIONS=--max-old-space-size=256", svc["Environment"])

    def test_path_watches_the_files_an_update_removes(self):
        p = load("lumen-mail-sync.path")["Path"]
        self.assertEqual(p["PathChanged"], [f"{RC}/config/config.inc.php", f"{RC}/program/include/iniset.php",
                                            f"{RC}/skins/lumen/meta.json"])
        self.assertEqual(p["Unit"], ["lumen-mail-sync.service"])
        for value in p["PathChanged"]:
            self.assertFalse(value.endswith("/skins") or value.endswith("/skins/"),
                             "watching skins/ would see lumen-mail's own renames")

    def test_timer(self):
        t = load("lumen-mail-sync.timer")["Timer"]
        self.assertEqual(t["OnUnitActiveSec"], ["2min"])
        self.assertEqual(t["OnBootSec"], ["1min"])

    def test_units_parse(self):
        for name in ("lumen-mail-sync.service", "lumen-mail-sync.path", "lumen-mail-sync.timer"):
            cp = configparser.ConfigParser(strict=False, interpolation=None)
            cp.optionxform = str  # type: ignore[assignment]
            cp.read_string((UNITS / name).read_text(encoding="utf-8"))
            self.assertIn("Unit", cp.sections())

    @unittest.skipUnless(shutil.which("systemd-analyze"), "systemd-analyze not available")
    def test_systemd_analyze_verify(self):
        with tempfile.TemporaryDirectory(prefix="lumen-mail-units-") as tmp:
            for f in UNITS.glob("lumen-mail-sync.*"):
                text = f.read_text(encoding="utf-8").replace("/opt/lumen-mail/bin/lumen-mail", shutil.which("true") or
                                                             "/bin/true")
                (Path(tmp) / f.name).write_text(text, encoding="utf-8")
            files = sorted(str(p) for p in Path(tmp).iterdir())
            proc = subprocess.run(["systemd-analyze", "verify", "--man=no", *files], capture_output=True, text=True,
                                  timeout=120)
        if "Failed to" in proc.stderr and "bus" in proc.stderr.lower():
            self.skipTest("systemd-analyze cannot run here: " + proc.stderr.strip()[:200])
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
