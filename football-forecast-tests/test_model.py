"""Independent regression cases for the original regulation-time forecast engine."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "football-forecast-lab" / "scripts"))
from model import predict_match


class MatchModelTest(unittest.TestCase):
    def setUp(self):
        self.fixture = dict(home="A", away="B", kickoff="2026-06-01T16:00:00Z",
                            as_of="2026-06-01T12:00:00Z", neutral=True)

    def forecast(self, **changes):
        return predict_match(dict(self.fixture, **changes))

    def test_neutral_equal_teams_symmetric(self):
        output = self.forecast()
        h, d, a = output["probs"]
        self.assertAlmostEqual(h, a)
        self.assertAlmostEqual(h + d + a, 1)
        self.assertTrue(output["warnings"])

    def test_evidence_caps_and_update_dedup(self):
        item = dict(team="A", kind="injury", source="team-A", event_id="player-1-injury",
                    delta_xg=-0.2, confidence=0.8, observed_at="2026-05-30T12:00:00Z")
        newer = dict(item, delta_xg=-2, observed_at="2026-05-31T12:00:00Z")
        output = self.forecast(home_xg=1.5, away_xg=1.05, evidence=[newer, item, newer])
        self.assertAlmostEqual(output["model_goal_means"][0], 1.5 - 0.35 * 0.8)
        self.assertEqual(len(output["evidence"]), 1)
        self.assertLess(output["base_probs"][0], output["statistical_probs_before_evidence"][0])

    def test_conflicting_updates_and_future_evidence_rejected(self):
        item = dict(team="A", kind="injury", source="reporter", delta_xg=-0.2, confidence=0.8,
                    observed_at="2026-06-01T11:00:00Z")
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.forecast(evidence=[item, dict(item, delta_xg=-0.1)])
        with self.assertRaisesRegex(ValueError, "later than as_of"):
            self.forecast(evidence=[dict(item, observed_at="2026-06-01T13:00:00Z")])

    def test_history_cutoff_is_conservative(self):
        past = dict(date="2026-05-28", home="A", away="B", home_goals=3, away_goals=0)
        uncertain = dict(past, date="2026-06-01")
        future = dict(past, date="2026-06-02")
        output = predict_match(self.fixture, [past, uncertain, future, past])
        self.assertEqual((output["eligible_history"], output["ignored_history"]), (1, 3))
        self.assertGreater(output["probs"][0], self.forecast()["probs"][0])
        known = dict(uncertain, kickoff="2026-06-01T07:00:00Z",
                     completed_at="2026-06-01T08:56:00Z")
        self.assertEqual(predict_match(self.fixture, [known])["eligible_history"], 1)
        late = dict(known, observed_at="2026-06-01T12:01:00Z")
        self.assertEqual(predict_match(self.fixture, [late])["eligible_history"], 0)
        with self.assertRaisesRegex(ValueError, "conflicting historical"):
            predict_match(self.fixture, [past, dict(past, home_goals=4)])

    def test_market_fusion_score_marginals_and_targets(self):
        odds = [2.0, 4.0, 4.0]
        output = self.forecast(odds=odds, target_odds=odds, market_weight=1.0)
        self.assertEqual(output["market_probs"], [0.5, 0.25, 0.25])
        self.assertEqual(output["probs"], [0.5, 0.25, 0.25])
        self.assertIsNone(output["target_comparison"]["probability_gap"])
        matrix = output["score_matrix"]
        result = [sum(p for i, row in enumerate(matrix) for j, p in enumerate(row)
                      if (i > j, i == j, i < j)[side]) for side in range(3)]
        for p, q in zip(result, output["probs"]):
            self.assertAlmostEqual(p, q)
        for cell in output["top_scores"]:
            self.assertEqual(cell["p"], matrix[cell["home"]][cell["away"]])
        self.assertLess(sum(cell["p"] for cell in output["top_scores"]), 1)
        other = self.forecast(odds=odds, market_weight=1.0, target_odds=[2.2, 3.6, 4.5])
        self.assertEqual(output["probs"], other["probs"])
        self.assertGreater(other["target_comparison"]["edge_vs_break_even"][0], 0)

    def test_same_reference_source_is_not_independent(self):
        out = self.forecast(odds=[2, 3, 4], target_odds=[2.1, 3.1, 4.1],
                            odds_source="book-A", target_odds_source="book-A")
        self.assertTrue(out["target_comparison"]["shared_reference"])

    def test_as_of_market_and_features(self):
        for changes in [
            {"odds": [2, 3, 4], "odds_at": "2026-06-01T14:00:00Z"},
            {"home_elo": 1700, "away_elo": 1650, "features_at": "2026-06-02T12:00:00Z"},
            {"as_of": self.fixture["kickoff"]}, {"as_of": "2026-06-01T12:00:00"},
            {"market": "advance"}, {"home_elo": 1800}, {"home_xg": float("nan")},
            {"odds": [1, 3, 5]}, {"neutral": "false"}, {"market_weight": -0.01}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.forecast(**changes)

    def test_roles_scope_and_weight(self):
        role = dict(role="tactics", probs=[0.8, 0.2, 0.0], market="1x2_90", source="analyst-1",
                    observed_at="2026-06-01T11:00:00Z")
        out = self.forecast(roles=[role, dict(role, role="market", weight=0.18, probs=[0.4,0.3,0.3])],
                            role_weight=1.0)
        for p,q in zip(out["probs"], (0.6, 0.25, 0.15)):
            self.assertAlmostEqual(p, q)
        for bad in [dict(role, market="advance"), dict(role, probs=[77, 20, 3])]:
            with self.assertRaises(ValueError):
                self.forecast(roles=[bad])

    def test_high_scoring_and_negative_rho(self):
        out = self.forecast(home_xg=8, away_xg=8, rho=-0.2)
        self.assertTrue(all(p >= 0 for row in out["score_matrix"] for p in row))
        self.assertAlmostEqual(sum(map(sum, out["score_matrix"])), 1)
        self.assertAlmostEqual(out["probs"][0], out["probs"][2])

    def test_original_input_is_unchanged(self):
        fixture = dict(self.fixture, odds=[1.9, 3.2, 3.8])
        original = deepcopy(fixture)
        predict_match(fixture)
        self.assertEqual(fixture, original)


if __name__ == "__main__":
    unittest.main()
