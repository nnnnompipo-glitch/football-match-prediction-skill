import copy
from datetime import date, timedelta
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "football-forecast-lab" / "scripts"))
from calibrate import apply_temperature, calibration_history, fit_calibration, validate_for_match
from competitions import backtest_rows, calibration_cutoff, history_policy
from model import predict_match


def report(outcomes="HDAHDA", days=16):
    records = []
    for i in range(days):
        day = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
        for j in range(3):
            records.append({"date": day, "home": f"H{j}", "away": f"A{j}", "probs": [0.9, .07, .03],
                            "as_of": day + "T00:00:00Z", "training_rows": 4,
                            "actual": outcomes[(i * 3 + j) % len(outcomes)], "competition": "L"})
    return {"forecasts": records, "history_policy": history_policy(3, 4)}


class CalibrationTests(unittest.TestCase):
    def test_temperature_preserves_mass_and_exact_zeros(self):
        for temp in (.25, 1, 2, 4):
            out = apply_temperature([.75, .25, 0], temp)
            self.assertAlmostEqual(sum(out), 1)
            self.assertEqual(out[2], 0)
        for temp in (0, 4.01, float("nan"), True):
            with self.assertRaises(ValueError):
                apply_temperature([.9, .08, .02], temp)
        with self.assertRaises(ValueError):
            apply_temperature([.45, .45, .2], 2)

    def test_softens_overconfidence_and_uses_disjoint_dates(self):
        artifact = fit_calibration(report())
        self.assertTrue(artifact["enabled"])
        self.assertGreater(artifact["temperature"], 1)
        self.assertLess(artifact["trained_until"], artifact["validation_start"])
        self.assertEqual(artifact["fit"]["candidate"]["n"] % 3, 0)
        self.assertEqual(artifact["holdout"]["candidate"]["n"] % 3, 0)
        self.assertLess(artifact["holdout"]["candidate"]["brier"], artifact["holdout"]["identity"]["brier"])
        self.assertLess(artifact["holdout"]["candidate"]["log_loss"], artifact["holdout"]["identity"]["log_loss"])

    def test_validation_regime_change_retains_identity(self):
        data = report(days=20)
        for row in data["forecasts"][42:]:
            row["actual"] = "H"
        artifact = fit_calibration(data)
        self.assertGreater(artifact["candidate_temperature"], 1)
        self.assertFalse(artifact["enabled"])
        self.assertEqual(artifact["temperature"], 1)

    def test_later_validation_gate_and_applicable_inputs(self):
        artifact = fit_calibration(report())
        match = {"as_of": "2026-02-04T00:00:00+02:00", "competition": "L"}
        self.assertEqual(validate_for_match(artifact, match), artifact["temperature"])
        for change in ({"competition": "other"}, {"as_of": "2026-01-01T00:00:00Z"},
                       {"roles": [{"role": "market"}]}, {"home_xg": 1.2}, {"odds": [2, 3, 4]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_for_match(artifact, dict(match, **change))
        for change in ({"temperature": math.inf}, {"schema": "unknown"}, {"enabled": False, "temperature": 2}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_for_match(dict(artifact, **change), match)

    def test_late_labels_are_not_fit(self):
        data = report()
        data["forecasts"][0]["result_available_at"] = "2026-03-01T00:00:00Z"
        data["forecasts"][-1]["result_available_at"] = "2026-02-10T00:00:00Z"
        artifact = fit_calibration(data)
        self.assertEqual(artifact["excluded_late_fit_labels"], 1)
        self.assertEqual(artifact["validated_until"], "2026-02-10")
        with self.assertRaises(ValueError):
            validate_for_match(artifact, {"competition": "L", "as_of": "2026-02-09T00:00:00Z"})

    def test_missing_mixed_duplicate_and_insufficient(self):
        data = report()
        with self.assertRaisesRegex(ValueError, "distinct-date"):
            fit_calibration(report(days=1))
        data["forecasts"][0]["competition"] = "Other"
        with self.assertRaisesRegex(ValueError, "Mixed"):
            fit_calibration(data)
        self.assertEqual(fit_calibration(data, competition="L")["applicability"]["competition"], "L")
        data = report()
        data["forecasts"].append(copy.deepcopy(data["forecasts"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            fit_calibration(data)

    def test_report_and_artifact_require_matching_sample_protocol(self):
        data = report()
        for change in ({"history_policy": None}, {"window": 6},
                       {"history_policy": dict(data["history_policy"], model_version="foreign")}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                fit_calibration(dict(data, **change))
        for change in ({"training_rows": 2}, {"training_rows": 5}, {"as_of": "2026-01-01T06:00:00Z"}):
            invalid = copy.deepcopy(data)
            invalid["forecasts"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                fit_calibration(invalid)
        artifact = fit_calibration(data)
        self.assertEqual(artifact["history_policy"], data["history_policy"])
        for change in ({"schema": "football-forecast-lab/temperature-v1"}, {"history_policy": {}},
                       {"history_policy": dict(data["history_policy"], cutoff="live")}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_for_match(dict(artifact, **change), {"competition": "L", "as_of": "2026-03-01T15:00:00Z"})

    def test_deploy_reproduces_eligible_training_rows_and_probabilities(self):
        artifact = fit_calibration(report())
        rows = []
        for day in range(1, 9):
            stamp = f"2026-02-{day:02d}"
            rows.append({"date": stamp, "home": "A", "away": "B", "home_goals": day % 3,
                         "away_goals": day % 2, "competition": "L", "kickoff": stamp + "T11:00:00Z"})
        rows[5]["result_available_at"] = "2026-02-08T05:00:00Z"
        rows.extend([dict(rows[6], competition="Other"), dict(rows[6], competition=None)])
        match = {"home": "A", "away": "B", "competition": "L", "as_of": "2026-02-08T10:00:00Z",
                 "kickoff": "2026-02-08T11:00:00Z"}
        selected = calibration_history(artifact, match, list(reversed(rows)))
        self.assertEqual([r["date"] for r in selected], [f"2026-02-{d:02d}" for d in (3, 4, 5, 7)])
        self.assertTrue(all(r["competition"] == "L" for r in selected))
        result = backtest_rows(rows, min_train=3, window=4)
        historical = next(r for r in result["forecasts"] if r["date"] == rows[7]["date"])
        snapshot = calibration_cutoff(match)
        self.assertEqual(historical["as_of"], snapshot)
        self.assertEqual(predict_match(dict(match, as_of=snapshot), history=selected)["probs"], historical["probs"])
        self.assertEqual(result["history_policy"], artifact["history_policy"])
        with self.assertRaisesRegex(ValueError, "at least 3"):
            calibration_history(artifact, match, rows[:2])
        live = dict(rows[7], status="IN_PLAY")
        self.assertEqual(calibration_history(artifact, match, rows + [live]), selected)


if __name__ == "__main__":
    unittest.main()
