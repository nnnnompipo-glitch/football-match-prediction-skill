import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_engine
from model import predict_match
from simulation import _distribution, simulate


class MatchSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        examples = studio_engine.examples()
        cls.forecast = predict_match(examples["match"], examples["history"]["records"]
                                     if isinstance(examples["history"], dict) else examples["history"])
        cls.request = {"prediction": cls.forecast, "home": "主队", "away": "客队"}

    def test_even_without_report_matrix_uses_exact_final_distribution(self):
        p = self.forecast.copy()
        reference = p.pop("score_matrix")
        restored = _distribution(p)
        self.assertEqual(len(restored), len(reference))
        for values, original in zip(restored, reference):
            self.assertEqual(values, original)
        likely = simulate({**self.request, "prediction": p, "selection": "most_likely", "seed": 17})
        top = p["top_scores"][0]
        self.assertEqual(likely["score"], [top["home"], top["away"]])
        self.assertAlmostEqual(likely["score_probability"], top["p"])

    def test_goal_events_equal_selected_score(self):
        for score in ([0, 0], [1, 0], [0, 3], [2, 2], [5, 2]):
            with self.subTest(score=score):
                sim = simulate({**self.request, "selection": score, "seed": 7})
                events = sim["events"]
                goals = [event["side"] for event in events if event["type"] == "goal"]
                self.assertEqual([goals.count("home"), goals.count("away")], score)
                self.assertEqual(events[0]["type"], "kickoff")
                self.assertEqual(events[-1]["type"], "fulltime")
                self.assertEqual([e["minute"] for e in events], sorted({e["minute"] for e in events}))

    def test_random_replay_respects_final_outcome_and_seed(self):
        p = {**self.forecast, "probs": [0, 0, 1]}
        payload = {**self.request, "prediction": p, "selection": "sample", "seed": 92}
        sim = simulate(payload)
        self.assertEqual(sim, simulate(payload))
        self.assertGreater(sim["score"][1], sim["score"][0])
        with self.assertRaises(ValueError):
            simulate({**payload, "selection": [2, 0]})


if __name__ == "__main__":
    unittest.main()
