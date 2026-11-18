"""Translations can improve while archived calculation inputs stay immutable."""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
from ledger import archived, freeze, packed


class TranslationLedgerTests(unittest.TestCase):
    def test_label_upgrade_keeps_original_archive_and_rejects_calculation_changes(self):
        match = {"home": "Example United", "away": "Example City", "competition": "Example League",
                 "kickoff": "2025-01-03T15:00:00Z", "as_of": "2025-01-02T10:00:00Z",
                 "home_zh": "埃克桑普尔联", "home_aliases": ["Example United"],
                 "translation": {"home": {"original": "Example United", "provisional": True}},
                 "provenance": {"provider_id": "fixture-42"}}
        first = {"input": match, "prediction": {"probs": [.5, .3, .2], "expected_goals": [1.4, 1.]}}
        second = copy.deepcopy(first)
        second["input"].update(home_zh="示例联队", home_aliases=["示例联", "Example United"],
                               translation={"home": {"original": "Example United", "method": "wikidata"}})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forecasts.sqlite"
            freeze(path, [first], [], captured_at="2025-01-02T10:01:00Z")
            freeze(path, [second], [], captured_at="2025-01-02T10:02:00Z")
            saved = archived(path, match, match["as_of"])
            self.assertEqual(saved["input"], match)
            self.assertEqual(len(saved["reports"]), 2)
            self.assertEqual(saved["reports"][0]["report"], first)
            self.assertEqual(saved["reports"][0]["sha256"], hashlib.sha256(packed(first).encode()).hexdigest())
            self.assertEqual(saved["reports"][1]["report"], second)
            mutations = [lambda m: m["input"].update(home_elo=1800),
                         lambda m: m["input"]["provenance"].update(provider_id="fixture-99"),
                         lambda m: m["prediction"].update(probs=[.6, .2, .2])]
            for mutate in mutations:
                changed = copy.deepcopy(second)
                mutate(changed)
                with self.assertRaises(ValueError):
                    freeze(path, [changed], [], captured_at="2025-01-02T10:03:00Z")
            with self.assertRaises(ValueError):
                freeze(path, [second], [{"new_history": True}], captured_at="2025-01-02T10:03:00Z")
            self.assertEqual(archived(path, match, match["as_of"])["input"], match)


if __name__ == "__main__":
    unittest.main()
