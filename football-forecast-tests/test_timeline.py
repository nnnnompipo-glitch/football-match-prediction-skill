import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "football-forecast-lab" / "scripts"))
from timeline import timing_summary


class TimelineTests(unittest.TestCase):
    def test_goalless_result(self):
        result = timing_summary([[1]])
        self.assertEqual(result["half_probs"], [0, 1, 0])
        self.assertEqual(result["half_top_scores"], [{"home": 0, "away": 0, "p": 1}])
        self.assertEqual(result["half_expected_goals"], [0, 0])
        self.assertTrue(all(p["p_at_least_one_goal"] == 0 for p in result["periods"]))

    def test_one_goal_each(self):
        result = timing_summary([[0, 0], [0, 1]])
        self.assertEqual(result["half_probs"], [.25, .5, .25])
        self.assertEqual(result["half_expected_goals"], [.5, .5])
        self.assertEqual({(r["home"], r["away"], r["p"]) for r in result["half_top_scores"]},
                         {(0, 0, .25), (0, 1, .25), (1, 0, .25), (1, 1, .25)})
        self.assertEqual([(p["start_minute"], p["end_minute"]) for p in result["periods"]],
                         [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 90)])
        for period in result["periods"]:
            self.assertAlmostEqual(period["expected_goals"], 1 / 3)
            self.assertAlmostEqual(period["p_at_least_one_goal"], 11 / 36)
            self.assertAlmostEqual(period["p_home_goal"], 1 / 6)
            self.assertAlmostEqual(period["p_away_goal"], 1 / 6)

    def test_mixture_preserves_dependence_and_goal_mass(self):
        # Either scoreless or a 2-1 result with equal probability.
        matrix = [[.5, 0], [0, 0], [0, .5]]
        summary = timing_summary(matrix)
        self.assertEqual(summary["half_probs"], [.25, .6875, .0625])
        self.assertEqual(summary["half_expected_goals"], [.5, .25])
        periods = summary["periods"]
        self.assertAlmostEqual(sum(p["home_expected_goals"] for p in periods), 1)
        self.assertAlmostEqual(sum(p["away_expected_goals"] for p in periods), .5)
        self.assertAlmostEqual(periods[0]["p_at_least_one_goal"], .5 * (1 - (5 / 6) ** 3))
        self.assertEqual(len(summary["half_top_scores"]), 5)

    def test_rectangular_matrix_and_invalid_inputs(self):
        self.assertEqual(timing_summary([[0, 0, 1]])["half_probs"], [0, .25, .75])
        for invalid in (None, [], [[]], [[1], []], [[.4]], [[-.1, 1.1]], [[True]], [[math.nan]]):
            with self.subTest(matrix=invalid), self.assertRaises(ValueError):
                timing_summary(invalid)


if __name__ == "__main__":
    unittest.main()
