"""Exercise public CLI and ledger entry points with synthetic, offline data."""
import json
import math
import operator
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "football-forecast-lab"
sys.path.insert(0, str(SKILL / "scripts"))
from ledger import freeze, review, settle


def fixture(home="Arsenal", away="Pine XI"):
    return {"home": home, "away": away, "competition": "Example League",
            "kickoff": "2026-02-15T15:00:00Z", "as_of": "2026-02-15T12:00:00Z"}


class FootballIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def save(self, name, obj):
        path = self.work / name
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return path

    def run_cli(self, *args, succeeds=True):
        proc = subprocess.run([sys.executable, "-X", "utf8", "-B", str(SKILL / "scripts" / "football.py"),
                               *map(str, args)], cwd=self.work, capture_output=True,
                              text=True, encoding="utf-8", timeout=25)
        if succeeds:
            self.assertEqual(proc.returncode, 0, proc.stderr)
        else:
            self.assertNotEqual(proc.returncode, 0)
            self.assertNotIn("Traceback", proc.stderr)
        return proc

    def cli_json(self, *args):
        return json.loads(self.run_cli(*args).stdout)

    def test_fit_artifact_drives_forecast_and_rejects_incompatible_cutoffs_and_leagues(self):
        pairs = [("Arsenal", "Pine XI", 3, 0), ("Lake", "Hill", 1, 1),
                 ("Hill", "Arsenal", 1, 3), ("Pine XI", "Lake", 0, 2)]
        history = []
        for i in range(32):
            h, a, hg, ag = pairs[i % len(pairs)]
            history.append({"date": (date(2025, 12, 1) + timedelta(days=i)).isoformat(),
                            "home": h, "away": a, "home_goals": hg, "away_goals": ag,
                            "competition": "Example League"})
        history.append({"date": "2026-02-14", "home": "Arsenal", "away": "Pine XI",
                        "competition": "Example League", "home_goals": 0, "away_goals": 4})
        fit_path = self.work / "fit.json"
        self.run_cli("fit", self.save("history.json", history), "--competition", "Example League",
                     "--as-of", "2026-02-01T12:00:00Z", "--out", fit_path)
        fit = json.loads(fit_path.read_text(encoding="utf-8"))
        self.assertEqual(fit["matches"], 32)
        self.assertEqual(fit["ignored"], 1)
        for neutral in (True, False):
            with self.subTest(neutral=neutral):
                match_path = self.save("fixture.json", {**fixture(), "neutral": neutral})
                result = self.cli_json("forecast", match_path, "--fit", fit_path)["matches"][0]
                h, a = fit["teams"]["Arsenal"], fit["teams"]["Pine XI"]
                rh = fit["neutral_mean"] if neutral else fit["home_mean"]
                ra = fit["neutral_mean"] if neutral else fit["away_mean"]
                want = [rh * h["attack"] * a["concession"], ra * a["attack"] * h["concession"]]
                self.assertEqual(result["input"]["fit_provenance"]["matches"], 32)
                self.assertEqual(result["input"]["xg_at"], fit["as_of"])
                self.assertEqual(result["input"]["rho"], fit["rho"])
                for actual, expected in zip(result["prediction"]["expected_goals"], want):
                    self.assertAlmostEqual(actual, expected)
        for change in [{"competition": "Another League"}, {"as_of": "2026-01-31T12:00:00Z"}]:
            with self.subTest(change=change):
                self.run_cli("forecast", self.save("invalid.json", {**fixture(), **change}),
                             "--fit", fit_path, succeeds=False)

    def test_aliases_join_sources_and_matrix_reproduces_published_markets(self):
        m = fixture("Arsenal FC")
        observation = "2026-02-15T10:00:00Z"
        ratings = {"kind": "ratings", "observed_at": observation,
                   "records": [{"team": "Arsenal", "elo": 1670}, {"team": "Pine XI", "elo": 1500}]}
        quote = {**fixture(), "market": "1x2_90", "bookmaker": "Demo", "odds": [4, 3.7, 1.9]}
        odds = {"kind": "odds", "observed_at": observation,
                "records": [quote, {**quote, "away": "Other", "odds": [1.2, 5, 9]}]}
        path = self.save("fixture.json", m)
        common = ["forecast", path, "--snapshot", self.save("ratings.json", ratings),
                  "--snapshot", self.save("odds.json", odds)]
        raw = self.cli_json(*common)["matches"][0]
        self.assertIsNone(raw["prediction"]["market_probs"])
        result = self.cli_json(*common, "--aliases", SKILL / "examples" / "aliases.json",
                               "--home", "Arsenal FC", "--matrix", "--handicap", "-1",
                               "--total", "2")["matches"][0]
        actual_input, p, markets = result["input"], result["prediction"], result["markets"]
        self.assertEqual((actual_input["home"], actual_input["home_elo"], actual_input["away_elo"]),
                         ("Arsenal", 1670, 1500))
        self.assertEqual(actual_input["odds"], quote["odds"])
        self.assertEqual([s["matched"] for s in result["sources"]["snapshots"]], [2, 1])
        self.assertNotAlmostEqual(p["base_probs"][0], p["probs"][0])
        matrix = p["score_matrix"]

        def mass(predicate):
            return math.fsum(v for h, row in enumerate(matrix) for a, v in enumerate(row)
                             if predicate(h, a))

        self.assertTrue(all(math.isfinite(v) and v >= 0 for row in matrix for v in row))
        self.assertAlmostEqual(mass(lambda h, a: True), 1)
        for actual, expected in zip(p["probs"], [mass(lambda h,a: h > a), mass(lambda h,a: h == a),
                                                  mass(lambda h,a: h < a)]):
            self.assertAlmostEqual(actual, expected)
        for i, op in enumerate((operator.gt, operator.eq, operator.lt)):
            self.assertAlmostEqual(markets["over_push_under"][i], mass(lambda h,a: op(h+a, 2)))
            self.assertAlmostEqual(markets["handicap_home_draw_away"][i], mass(lambda h,a: op(h-1, a)))
        self.assertAlmostEqual(markets["both_teams_score"], mass(lambda h,a: h > 0 and a > 0))
        self.assertAlmostEqual(markets["home_clean_sheet"], mass(lambda h,a: a == 0))
        self.assertAlmostEqual(markets["away_clean_sheet"], mass(lambda h,a: h == 0))
        for cell in p["top_scores"]:
            self.assertAlmostEqual(cell["p"], matrix[cell["home"]][cell["away"]])

    def test_html_preserves_literal_text_from_fixture_scenario_and_research(self):
        home = "<team-name>Harbor & Coast</team-name>"
        scenario = {"name": "<variant-note>Wind</variant-note>", "home_xg": 1.1}
        context = {"kind": "news", "source": "Demo", "observed_at": "2026-02-14T12:00:00Z",
                   "records": [{"headline": "<press-note>Travel delay</press-note>"}]}
        html = self.work / "report.html"
        result = self.cli_json("forecast", self.save("fixture.json", fixture(home=home)),
                               "--scenarios", self.save("scenario.json", [scenario]),
                               "--context", self.save("news.json", context), "--html", html)
        self.assertEqual(result["matches"][0]["input"]["home"], home)
        document = html.read_text(encoding="utf-8")
        for tag in ("team-name", "variant-note", "press-note"):
            self.assertIn(f"&lt;{tag}&gt;", document)
            self.assertNotIn(f"<{tag}>", document)
        self.assertIn("Harbor &amp; Coast", document)

    def test_combination_multiplies_distinct_matches_and_refuses_same_fixture_twice(self):
        first, second = fixture(), fixture("Lake", "Hill")
        forecast_path = self.work / "batch.json"
        self.run_cli("forecast", self.save("fixtures.json", [first, second]), "--out", forecast_path)
        predictions = json.loads(forecast_path.read_text(encoding="utf-8"))["matches"]
        choices = [{**first, "outcome": "home"}, {**second, "outcome": "draw"}]
        picked = self.cli_json("combo", forecast_path, self.save("choices.json", choices))
        expected = predictions[0]["prediction"]["probs"][0] * predictions[1]["prediction"]["probs"][1]
        self.assertAlmostEqual(picked["joint_probability"], expected)
        self.assertAlmostEqual(picked["fair_decimal_under_independence"], 1 / expected)
        duplicate = {**first, "home": "ARSENAL", "outcome": "away",
                     "kickoff": "2026-02-15T16:00:00+01:00"}
        for bad in (duplicate, {**second, "away": "Other", "outcome": "draw"}):
            with self.subTest(bad=bad):
                self.run_cli("combo", forecast_path, self.save("invalid.json", [choices[0], bad]),
                             succeeds=False)

    def test_ledger_rolls_back_batches_and_reviews_latest_forecast_per_capture_group(self):
        db = self.work / "forecasts.sqlite"

        def batch_item(row, probabilities):
            return {"input": row, "prediction": {"probs": probabilities,
                    "top_scores": [{"home": 0, "away": 1}]}}

        first, other = fixture(), fixture("Lake", "Hill")
        early = batch_item({**first, "as_of": "2026-02-14T18:00:00Z"}, [.1, .2, .7])
        final = batch_item(first, [.65, .2, .15])
        retrospective = batch_item({**first, "as_of": "2026-02-15T13:00:00Z"}, [.2, .1, .7])
        for item, captured in [(early, early["input"]["as_of"]), (final, first["as_of"]),
                               (retrospective, "2026-02-16T08:00:00Z")]:
            freeze(db, [item], [], captured_at=captured)
        with self.assertRaises(ValueError):
            freeze(db, [batch_item(other, [.5,.3,.2]), batch_item(first, [.8,.1,.1])], [],
                   captured_at=first["as_of"])
        end = "2026-02-16T09:00:00Z"
        result = {**first, "home_goals": 0, "away_goals": 1}
        with self.assertRaises(ValueError):
            settle(db, [result, {**other, "home_goals": 0, "away_goals": 0}], now=end)
        self.assertEqual(review(db)["prospective"]["n"], 0)
        self.assertEqual(settle(db, [result], now=end)["new_results"], 1)
        self.assertEqual(settle(db, [result], now=end)["new_results"], 0)
        report = self.cli_json("review", db)
        self.assertEqual(report["prospective"]["n"], 1)
        self.assertEqual(report["prospective"]["accuracy"], 0)
        self.assertAlmostEqual(report["prospective"]["log_loss"], -math.log(.15))
        self.assertEqual(report["retrospective"]["n"], 1)
        self.assertEqual(report["retrospective"]["accuracy"], 1)
        self.assertAlmostEqual(report["retrospective"]["log_loss"], -math.log(.7))


if __name__ == "__main__":
    unittest.main()
