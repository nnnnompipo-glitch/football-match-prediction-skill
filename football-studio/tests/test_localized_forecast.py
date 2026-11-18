"""Regression checks for display labels crossing the identity and freeze boundary."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_engine
from model import predict_match


class LocalizedForecastTests(unittest.TestCase):
    def test_aliases_translation_and_source_survive_freeze_without_changing_probabilities(self):
        match = {"home": "Manchester City FC", "away": "Chelsea FC",
                 "competition": "English Premier League",
                 "kickoff": "2025-04-12T15:00:00Z", "as_of": "2025-04-11T12:00:00Z",
                 "source_url": "https://example.com/test-fixture",
                 "provenance": {"provider": "test fixture", "web_url": "https://example.com/test-fixture",
                                "original_names": {"home": "Manchester City FC", "away": "Chelsea FC"}}}
        aliases = {"Manchester City FC": "Manchester City", "Chelsea FC": "Chelsea"}
        baseline_input = {**match, "home": "Manchester City", "away": "Chelsea"}
        baseline = predict_match(baseline_input, [])
        with tempfile.TemporaryDirectory(prefix="studio-label-test-") as folder:
            with patch.dict(os.environ, {"FOOTBALL_STUDIO_DATA": folder}):
                payload = {"input": match, "aliases": aliases, "matrix": True, "ledger": True}
                result = studio_engine.run("forecast", payload)
                item = result["matches"][0]
                translated = item["input"]
                self.assertEqual(translated["home"], "Manchester City")
                self.assertEqual(translated["away"], "Chelsea")
                self.assertRegex(translated["home_zh"], r"[\u3400-\u9fff]")
                self.assertRegex(translated["away_zh"], r"[\u3400-\u9fff]")
                self.assertRegex(translated["competition_zh"], r"[\u3400-\u9fff]")
                for field in ("probs", "score_matrix", "expected_goals"):
                    self.assertEqual(item["prediction"][field], baseline[field])
                repeated = studio_engine.run("forecast", payload)
                self.assertEqual(item["input"], repeated["matches"][0]["input"])
                replay = studio_engine.run("archive", {
                    key: translated[key] for key in ("home", "away", "kickoff", "as_of")})
                self.assertEqual(replay["input"]["home_zh"], translated["home_zh"])
                self.assertEqual(replay["input"]["provenance"], match["provenance"])
                self.assertEqual(match["home"], "Manchester City FC")


if __name__ == "__main__":
    unittest.main()
