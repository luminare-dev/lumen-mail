"""The contrast table (docs/contrast.md) is current and every token pair passes WCAG 2.2 AA."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import contrast  # noqa: E402


class ContrastTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = contrast.TOKENS.read_text(encoding="utf-8")
        self.pairs = json.loads(contrast.PAIRS.read_text(encoding="utf-8"))["pairs"]

    def test_every_pair_passes_and_every_mix_is_right(self):
        _rows, problems = contrast.analyse(self.text, self.pairs)
        self.assertEqual(problems, [])

    def test_document_is_current(self):
        rows, _ = contrast.analyse(self.text, self.pairs)
        self.assertEqual(contrast.DOC.read_text(encoding="utf-8"), contrast.render(rows),
                         "run python3 scripts/contrast.py")

    def test_a_failing_pair_is_reported(self):
        pairs = [{"fg": "text-muted", "bg": "rail", "min": 4.5, "use": "test"}]
        _rows, problems = contrast.analyse(self.text, pairs)
        self.assertTrue(any("text-muted on rail" in p for p in problems), problems)

    def test_a_wrong_mix_is_reported(self):
        broken = self.text.replace("#F2F4FB; // mix(royal 6%, white)", "#F2F4FC; // mix(royal 6%, white)")
        _rows, problems = contrast.analyse(broken, self.pairs)
        self.assertTrue(any("is not mix(royal 6%, white)" in p for p in problems), problems)

    def test_every_role_exists_in_both_modes(self):
        broken = self.text.replace("@lm-dark-highlight:", "@lm-dark-highlite:")
        _rows, problems = contrast.analyse(broken, self.pairs)
        self.assertTrue(any("@lm-dark-highlight is missing" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
