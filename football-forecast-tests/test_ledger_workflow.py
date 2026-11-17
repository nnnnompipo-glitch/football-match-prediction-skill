"""Cross-check odds snapshot selection and prospective ledger scoring."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "football-forecast-lab" / "scripts"))

from ledger import freeze, review, settle
from workflow import prepare


def stamp(hhmm):
    return f"2026-05-01T{hhmm}:00Z"


def fixture():
    return {"home": "Harbor", "away": "Pine", "kickoff": stamp("12:00"), "as_of": stamp("10:30")}


def quote(capture, update, price):
    record = {**fixture(), "bookmaker": "Example", "market": "1x2_90", "odds": [price, 3, 4]}
    if update is not None:
        record["quote_observed_at"] = stamp(update)
    return {"kind": "odds", "observed_at": stamp(capture), "records": [record]}


class QuoteSelectionTests(unittest.TestCase):
    def test_newer_capture_of_old_quote_does_not_supersede_fresher_price(self):
        snapshots = [quote("10:25", "09:55", 2), quote("10:20", "10:15", 2.6)]
        for inputs in (snapshots, list(reversed(snapshots))):
            with self.subTest(reversed=(inputs is not snapshots)):
                match, audit = prepare(fixture(), inputs)
                self.assertEqual(match["odds"], [2.6, 3, 4])
                self.assertEqual(match["odds_at"], stamp("10:15"))
                self.assertEqual(match["odds_captured_at"], stamp("10:20"))
                older, selected = audit["quote_history"]
                self.assertEqual(older["quote_observed_at"], stamp("09:55"))
                self.assertEqual(older["captured_at"], stamp("10:25"))
                self.assertEqual(selected["observed_at"], stamp("10:20"))

    def test_missing_provider_timestamp_falls_back_to_observation(self):
        match, audit = prepare(fixture(), [quote("10:00", None, 2.3),
                                          quote("10:40", "10:20", 1.5),
                                          quote("10:05", "10:12", 2.8)])
        self.assertEqual(match["odds"], [2.3, 3, 4])
        self.assertEqual(match["odds_at"], stamp("10:00"))
        self.assertIsNone(audit["quote_history"][0]["quote_observed_at"])
        self.assertEqual(len(audit["quote_history"]), 1)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "prospective.sqlite"
        report = {"probs": [.4, .2, .4], "top_scores": [{"home": 1, "away": 1}]}
        freeze(self.db, [{"input": fixture(), "prediction": report}], [], captured_at=stamp("10:30"))

    def add(self, home_goals, away_goals, **fields):
        row = {**fixture(), "home_goals": home_goals, "away_goals": away_goals, **fields}
        return settle(self.db, [row], now=stamp("15:00"))

    def test_in_play_and_nonregulation_leaves_fixture_settleable(self):
        for invalid in [{"status": "IN_PLAY"}, {"status": None}, {"status": "POSTPONED"},
                        {"status": "FINISHED", "market": "to_qualify"},
                        {"status": "PEN"}, {"score_period": "SHOOTOUT"},
                        {"duration": "EXTRA_TIME"}, {"observed_at": stamp("15:05")},
                        {"completed_at": stamp("11:00")}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.add(0, 0, **invalid)
        self.assertEqual(self.add(0, 1, status="FINISHED"), {"new_results": 1})
        self.assertEqual(self.add(0, 1), {"new_results": 0})
        summary = review(self.db)["prospective"]
        self.assertEqual(summary["accuracy"], .5)
        self.assertEqual(summary["top1_ties"], 1)

    def test_explicit_regulation_score_of_completed_shootout_can_settle(self):
        result = self.add(1, 1, market="1x2_90", status="PEN", duration="PENALTY_SHOOTOUT")
        self.assertEqual(result, {"new_results": 1})
        self.assertEqual(review(self.db)["prospective"]["accuracy"], 0)


if __name__ == "__main__":
    unittest.main()
