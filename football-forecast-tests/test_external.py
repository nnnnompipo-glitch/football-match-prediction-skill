"""Exercise the optional external service with deterministic local test doubles."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "football-forecast-lab" / "scripts"))
import external


class PublicForecastTest(unittest.TestCase):
    slug = "test-a-b"
    fixture = {"event_slug":slug, "canonical_match_id":123, "home_team":{"name":"Alpha"},
               "away_team":{"name":"Beta"}, "kickoff_at":"2026-07-01T12:00:00Z","status":"SCHEDULED"}
    base = {"home_win_prob":0.50,"draw_prob":0.25,"away_win_prob":0.25,
            "market_prob_home_win":None,"computed_at":"2026-06-01T06:15:00Z",
            "signals":[{"signal_id":"team-form","team_side":"home"}]}
    change = {"signal_id":"team-form","team_side":"home","manual_delta":{"attack_delta":0.05}}
    def setUp(self):
        self.calls = []
        self.now = datetime(2026,6,1,8,tzinfo=timezone.utc)
        timepatch = patch.object(external, "_now", return_value=self.now)
        timepatch.start()
        self.addCleanup(timepatch.stop)

    def api(self, url, *, allowed_host, payload=None):
        self.assertEqual(allowed_host,"web3.binance.com")
        endpoint = url.removeprefix(external.BASE)
        self.calls.append((endpoint,payload))
        if endpoint == "recent-unfinished":
            body = [self.slug,"unmatched"]
        elif endpoint == "resolve-by-slug":
            body = [self.fixture] if self.slug in payload["slugs"] else []
        elif endpoint == "prediction/123":
            body = self.base
        elif endpoint == "recompute-final/123":
            body = dict(self.base,home_win_prob=0.53,draw_prob=0.22)
        elif endpoint in ("news-insights/123","master-analysis/123"):
            body = {"text":"external context"}
        else:
            self.fail(f"Unexpected endpoint {endpoint}")
        return {"data":body,"code":"000000"}

    def test_discovery_uses_resolved_teams_and_reports_missing(self):
        with patch.object(external,"fetch_json",side_effect=self.api):
            snapshot = external.recent()
        self.assertEqual(snapshot["records"][0]["home"],"Alpha")
        self.assertEqual(snapshot["unresolved_slugs"],["unmatched"])
        self.assertEqual(snapshot["kind"],"fixtures")

    def test_recompute_and_context_must_keep_reference_unchanged(self):
        with patch.object(external,"fetch_json",side_effect=self.api):
            snapshot = external.prediction(self.slug,context=True,edits=[self.change])
        row = snapshot["records"][0]
        self.assertEqual((snapshot["kind"],row["market"]),("external","1x2_90"))
        self.assertEqual(row["probs"],[0.5,0.25,0.25])
        self.assertIsNone(row["market_probs"])
        self.assertAlmostEqual(row["scenario"]["delta_pp"][0],3.0)
        self.assertEqual(len(row["context"]),2)
        write_calls = [(name,payload) for name,payload in self.calls if payload is not None]
        self.assertEqual([name for name,_ in write_calls],["resolve-by-slug","recompute-final/123"])
        self.assertEqual(write_calls[-1][1],{"signals":[self.change]})

    def test_rejects_unverified_edits_before_request(self):
        for bad in (dict(self.change,team_side="away"),dict(self.change,enabled="true"),
                    dict(self.change,signal_id="made-up"),dict(self.change,junk=1)):
            self.calls.clear()
            with self.subTest(bad=bad), patch.object(external,"fetch_json",side_effect=self.api):
                with self.assertRaises(ValueError):
                    external.prediction(self.slug,edits=[bad])
                self.assertNotIn("recompute-final/123",[x[0] for x in self.calls])

    def test_late_and_live_fixtures_rejected(self):
        for update in ({"kickoff_at":"2026-06-01T07:40:00Z"},{"status":"LIVE"},
                       {"status":"POSTPONED"},{"kickoff_at":None}):
            fixture = dict(self.fixture,**update)
            with self.subTest(update=update), patch.object(self,"fixture",fixture), patch.object(
                    external,"fetch_json",side_effect=self.api):
                with self.assertRaises(ValueError):
                    external.prediction(self.slug)

    def test_provider_errors_and_slug_path_are_not_dereferenced(self):
        with patch.object(external,"fetch_json",return_value={"code":"DENIED","data":[]}):
            with self.assertRaisesRegex(ValueError,"declined"):
                external.recent()
        with patch.object(external,"fetch_json") as fetch:
            with self.assertRaises(ValueError):
                external.resolve(["../bad"])
            fetch.assert_not_called()

    def test_bad_probabilities_and_future_update(self):
        for update in ({"computed_at":"2026-06-03T00:00:00Z"},
                       {"home_win_prob":50},{"away_win_prob":None}):
            with self.subTest(update=update),patch.object(self,"base",dict(self.base,**update)),patch.object(
                    external,"fetch_json",side_effect=self.api):
                with self.assertRaises(ValueError):
                    external.prediction(self.slug)


if __name__ == "__main__":
    unittest.main()
