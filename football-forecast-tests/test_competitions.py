import copy
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "football-forecast-lab" / "scripts"))
from competitions import backtest_rows, simulate_tournament


class TournamentTests(unittest.TestCase):
    def setUp(self):
        self.cup = {
            "groups": {"A": ["Lion", "Owl"], "B": ["Fox", "Bear"]},
            "ratings": {"Lion": 1700, "Owl": 1400, "Fox": 1650, "Bear": 1520},
            "bracket": [["A:1", "B:2"], ["B:1", "A:2"]],
            "as_of": "2026-06-01T00:00:00Z",
        }

    def test_seed_and_probability_mass_using_real_model(self):
        r = simulate_tournament(self.cup, sims=100, seed=11)
        self.assertEqual(r, simulate_tournament(self.cup, sims=100, seed=11))
        teams = list(r["teams"].values())
        self.assertAlmostEqual(sum(t["reach_4"] for t in teams), 4)
        self.assertAlmostEqual(sum(t["reach_2"] for t in teams), 2)
        self.assertAlmostEqual(sum(t["champion"] for t in teams), 1)
        self.assertTrue(all(t["champion"] <= t["reach_2"] <= t["reach_4"] for t in teams))

    def test_known_group_and_drawn_final(self):
        self.cup["group_results"] = [
            {"home": "Owl", "away": "Lion", "home_goals": 1, "away_goals": 3},
            {"home": "Fox", "away": "Bear", "home_goals": 2, "away_goals": 0},
        ]
        # The known final itself implies both semifinal winners, without supplying those scores.
        self.cup["knockout_results"] = [
            {"round": 2, "home": "Fox", "away": "Lion", "home_goals": 1, "away_goals": 1, "winner": "Fox"}
        ]
        r = simulate_tournament(self.cup, sims=7, seed=0)
        self.assertEqual(r["teams"]["Fox"]["champion"], 1)
        self.assertEqual(r["teams"]["Lion"]["reach_2"], 1)
        self.assertEqual(r["teams"]["Bear"]["reach_2"], 0)

    def test_known_field_supersedes_standings(self):
        cup = {"groups": {"A": ["a", "b", "c"], "B": ["d", "e", "f"]},
               "knockout_field": [["c", "f"], ["a", "e"]]}
        r = simulate_tournament(cup, sims=2, seed=0)
        self.assertEqual(r["teams"]["b"]["reach_4"], 0)
        self.assertEqual(r["teams"]["d"]["reach_4"], 0)
        self.assertEqual(r["teams"]["f"]["reach_4"], 1)

    def test_knockout_draw_requires_actual_winner(self):
        cup = {"groups": {"A": ["a", "b"]}, "knockout_field": [["a", "b"]],
               "knockout_results": [{"round": 2, "home": "a", "away": "b", "home_goals": 0, "away_goals": 0}]}
        with self.assertRaisesRegex(ValueError, "actual winner"):
            simulate_tournament(cup)

    def test_late_result_is_not_known_at_cutoff(self):
        self.cup["group_results"] = [{"home": "Lion", "away": "Owl", "home_goals": 1, "away_goals": 0,
                                       "observed_at": "2026-06-02T00:00:00Z"}]
        with self.assertRaisesRegex(ValueError, "available by as_of"):
            simulate_tournament(self.cup, sims=1)

    def test_duplicated_team_slot_and_score_rejected(self):
        for update in ({"groups": {"A": ["a", "b"], "B": ["a", "c"]}},
                       {"bracket": [["A:1", "A:2"], ["B:1", "A:2"]]},
                       {"group_results": [
                           {"home": "Lion", "away": "Owl", "home_goals": 1, "away_goals": 0},
                           {"home": "Owl", "away": "Lion", "home_goals": 0, "away_goals": 1}]}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                simulate_tournament({**self.cup, **update})

    def test_contradictory_path_rejected(self):
        self.cup.pop("bracket")
        self.cup["knockout_field"] = [["Lion", "Fox"], ["Bear", "Owl"]]
        self.cup["knockout_results"] = [
            {"round": 4, "home": "Lion", "away": "Fox", "home_goals": 3, "away_goals": 1},
            {"round": 2, "home": "Fox", "away": "Bear", "home_goals": 2, "away_goals": 1}]
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            simulate_tournament(self.cup, sims=1, seed=1)

    def test_48_team_defaults(self):
        groups = {letter: [letter + str(i) for i in range(4)] for letter in "ABCDEFGHIJKL"}
        r = simulate_tournament({"groups": groups}, sims=1, seed=1)
        self.assertEqual(r["qualified_teams"], 32)
        self.assertEqual(sum(t["reach_32"] for t in r["teams"].values()), 32)

    def test_scored_inputs_must_be_completed_regulation_results(self):
        cup = dict(self.cup)
        cup.pop("bracket")
        cup["knockout_field"] = [["Lion", "Owl"], ["Fox", "Bear"]]
        game = {"date": "2026-05-01", "home": "Lion", "away": "Owl",
                "home_goals": 1, "away_goals": 0}
        for field in ("group_results", "knockout_results", "history"):
            base = dict(game, round=4) if field == "knockout_results" else game
            simulate_tournament({**cup, field: [base]}, sims=1)
            for invalid in ({"status": "IN_PLAY"}, {"market": "advancement"}):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    simulate_tournament({**cup, field: [{**base, **invalid}]}, sims=1)

    def test_scoreless_future_fixtures_do_not_lock_a_team(self):
        future = {"date": "2026-06-28", "home": "Lion", "away": "Owl",
                  "status": "SCHEDULED", "home_goals": None, "away_goals": None}
        cup = dict(self.cup, group_results=[future], history=[future],
                   knockout_results=[dict(future, round=2)])
        self.assertEqual(simulate_tournament(cup, sims=5), simulate_tournament(self.cup, sims=5))
        for partial in ({"home_goals": 1}, {"winner": "Lion"}):
            cup["knockout_results"] = [{**future, **partial, "round": 2}]
            with self.subTest(partial=partial), self.assertRaises(ValueError):
                simulate_tournament(cup, sims=5)


class BacktestTests(unittest.TestCase):
    @staticmethod
    def history():
        rows = []
        for i in range(10):
            for home, away, hg, ag in (("a", "b", i % 3, 1), ("c", "d", 0, i % 2)):
                rows.append({"date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                             "home": home, "away": away, "home_goals": hg, "away_goals": ag})
        return rows

    def test_batch_cutoff_no_same_day_or_prices_used_against_model(self):
        rows = self.history()
        for row in rows:
            row["odds"] = [2.0, 3.0, 4.0]
        seen = []

        def model(match, history):
            self.assertTrue(all(r["date"] < match["as_of"][:10] and "odds" not in r for r in history))
            self.assertNotIn("odds", match)
            seen.append(len(history))
            return {"probs": [0.4, 0.35, 0.25]}

        with patch("competitions.predict_match", model):
            report = backtest_rows(list(reversed(rows)), min_train=16)
        self.assertEqual(seen, [16, 16, 18, 18])
        self.assertEqual(report["n"], 4)
        self.assertEqual(report["paired_benchmarks"]["unknown_time"]["market"]["n"], 4)
        self.assertAlmostEqual(report["metrics"]["top1_accuracy"], 0.25)

    def test_odds_timing_and_real_model(self):
        rows = self.history()
        for i, row in enumerate(rows[-4:]):
            row.update(odds=[2, 3.2, 4], kickoff=row["date"] + "T15:00:00Z")
            if i == 0:
                row["odds_kind"] = "closing"
            elif i == 1:
                row["odds_observed_at"] = "2026-01-08T23:59:00Z"
            elif i == 2:
                row["odds_observed_at"] = row["date"] + "T14:00:00Z"
            else:
                row["odds_observed_at"] = row["date"] + "T15:00:00Z"
        r = backtest_rows(rows, min_train=16)
        self.assertEqual(r["odds_timing_counts"], {"closing_unverified": 1, "available_by_cutoff": 1,
                                                    "before_kickoff_after_cutoff": 1, "in_play_or_later": 1})
        self.assertNotIn("in_play_or_later", r["paired_benchmarks"])
        self.assertEqual(sum(b["n"] for b in r["metrics"]["top1_calibration"]), 4)
        self.assertLessEqual(r["metrics"]["brier"], 2)

    def test_duplicate_and_insufficient_history_reported(self):
        rows = self.history()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            backtest_rows(rows + [copy.deepcopy(rows[-1])], min_train=2)
        with self.assertRaisesRegex(ValueError, "No evaluable"):
            backtest_rows(rows, min_train=20)

    def test_backtest_rejects_live_or_wrong_market_in_train_and_test(self):
        for index in (0, -1):
            for invalid in ({"status": "IN_PLAY"}, {"market": "extra_time"}):
                rows = self.history()
                rows[index].update(invalid)
                with self.subTest(index=index, invalid=invalid), self.assertRaises(ValueError):
                    backtest_rows(rows, min_train=16)

    def test_backtest_excludes_fixture_without_label(self):
        rows = self.history()
        expected = backtest_rows(rows, min_train=16)
        rows.append({"date": "2026-01-06", "home": "a", "away": "d", "status": "SCHEDULED"})
        self.assertEqual(backtest_rows(rows, min_train=16), expected)

    def test_utc_midnight_kickoff_uses_previous_day_snapshot_only_for_that_fixture(self):
        rows = self.history()
        rows[-2]["kickoff"] = "2026-01-10T00:00:00Z"
        rows[-1]["kickoff"] = "2026-01-10T19:00:00Z"
        result = backtest_rows(rows, min_train=14, window=17)
        pair = [row for row in result["forecasts"] if row["date"] == "2026-01-10"]
        self.assertEqual([(r["as_of"], r["training_rows"]) for r in pair],
                         [("2026-01-09T00:00:00+00:00", 16), ("2026-01-10T00:00:00+00:00", 17)])
        settings = result["history_policy"]
        self.assertEqual((settings["min_train"], settings["window"]), (14, 17))
        self.assertTrue(settings["cutoff"])
        self.assertTrue(settings["model_version"])

    def test_competition_venue_delayed_labels_and_imported_closing_price(self):
        rows = self.history()
        for i, row in enumerate(rows):
            row["league"] = "Alpha" if i % 2 == 0 else "Beta"
            row.update(neutral=(i % 4 == 0), benchmark_odds=[2.0, 3.0, 4.0],
                       odds_horizon="closing")
        rows[0]["observed_at"] = "2026-02-01T00:00:00Z"

        def verify(match, history):
            self.assertTrue(all(r["competition"] == match["competition"] for r in history))
            self.assertTrue(all("neutral" in r for r in history))
            self.assertTrue(all(r.get("observed_at") != "2026-02-01T00:00:00Z" for r in history))
            self.assertNotIn("benchmark_odds", match)
            return {"probs": [0.45, 0.30, 0.25]}

        with patch("competitions.predict_match", verify):
            report = backtest_rows(rows, min_train=7)
        self.assertEqual(report["paired_benchmarks"]["closing_unverified"]["market"]["n"], 5)
        pair = [r for r in report["forecasts"] if r["date"] == "2026-01-09"]
        self.assertEqual({r["competition"]: r["training_rows"] for r in pair}, {"Alpha": 7, "Beta": 8})


if __name__ == "__main__":
    unittest.main()
