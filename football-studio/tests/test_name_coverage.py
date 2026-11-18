"""Offline display and provenance checks against a real multi-league audit."""
import copy
import json
import os
import re
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import localization


def audit_offline():
    fixture = json.loads((ROOT / "tests/fixtures/name_coverage_audit.json").read_text(encoding="utf-8"))
    original = fixture["fixtures"]
    untouched = copy.deepcopy(original)
    with tempfile.TemporaryDirectory(prefix="football-name-audit-") as folder:
        with patch.dict(os.environ, {"FOOTBALL_STUDIO_DATA": folder}), patch.object(localization, "_can_retry", return_value=False):
            translated = localization.localize_rows(original)
    counts = {}
    for kind, fields in (("teams", ("home", "away")), ("competitions", ("competition",)), ("stages", ("stage",))):
        names, readable, provisional, methods = set(), set(), set(), defaultdict(set)
        for row in translated:
            for field in fields:
                if not row.get(field):
                    continue
                name = row[field]
                names.add(name)
                if re.search(r"[\u3400-\u9fff]", row.get(field + "_zh", "")):
                    readable.add(name)
                info = row["translation"][field]
                methods[info["method"]].add(name)
                if info.get("provisional"):
                    provisional.add(name)
        counts[kind] = {"unique_original_names": len(names), "with_chinese": len(readable),
                        "provisional_names": len(provisional), "missing_chinese": sorted(names - readable),
                        "methods": {method: len(values) for method, values in methods.items()}}
    return original, untouched, translated, {"audited_at": fixture["observed_at"], "fixtures": len(original),
                                            "mode": "network disabled; fresh isolated cache", **counts}


class NameCoverageTests(unittest.TestCase):
    def test_all_collected_names_have_chinese_even_without_network(self):
        original, untouched, translated, counts = audit_offline()
        self.assertEqual(original, untouched)
        self.assertGreaterEqual(counts["fixtures"], 600)
        for group in ("teams", "competitions", "stages"):
            self.assertEqual(counts[group]["missing_chinese"], [], group)
        for raw, row in zip(original, translated):
            for field in ("id", "home", "away", "competition", "competition_id", "kickoff", "source_url"):
                self.assertEqual(row.get(field), raw.get(field), (raw.get("id"), field))
            for field in ("home", "away", "competition", "stage"):
                if not raw.get(field):
                    continue
                self.assertIn(raw[field], row[field + "_aliases"])
                self.assertIn(row[field + "_zh"], row[field + "_aliases"])
                info = row["translation"][field]
                if info.get("provisional"):
                    self.assertEqual(info["method"], "offline-transliteration")
                    self.assertIn("待核验", info["label"])


if __name__ == "__main__":
    unittest.main()
