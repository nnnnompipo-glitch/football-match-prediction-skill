import io
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr
from unittest.mock import patch


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "football-forecast-lab" / "scripts"))
import sources


class SourceTests(unittest.TestCase):
    def test_history_fetch_and_import_do_not_leak_closing_odds_to_model(self):
        data = {"matches": [{"date": "2025-04-03", "team1": "A", "team2": "B", "score": {"ft": [0, 2]}},
                            {"date": "2025-05-08", "team1": "B", "team2": "A"}]}
        with patch.object(sources, "fetch_bytes", return_value=json.dumps(data).encode()) as get:
            snapshot = sources.collect(sources.parser().parse_args(["history", "--league", "en.1", "--season", "2024-25"]))
        self.assertIn("2024-25/en.1.json", get.call_args.args[0])
        self.assertEqual(snapshot["records"], [{"date": "2025-04-03", "home": "A", "away": "B",
                                                "home_goals": 0, "away_goals": 2, "competition": "PL"}])
        self.assertIn("Skipped 1", snapshot["warnings"][0])
        with tempfile.TemporaryDirectory() as d:
            file = pathlib.Path(d) / "league.csv"
            out = pathlib.Path(d) / "history.json"
            file.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG,AvgCH,AvgCD,AvgCA\n08/04/25,A,B,0,0,2,3,4\n")
            self.assertEqual(sources.main(["history", "--csv", str(file), "--out", str(out)]), 0)
            row = json.loads(out.read_bytes())["records"][0]
            self.assertEqual((row["date"], row["benchmark_odds"]), ("2025-04-08", [2., 3., 4.]))
            self.assertNotIn("odds", row)
            self.assertNotIn("competition", row)
            original = file.read_bytes()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(sources.main(["history", "--csv", str(file), "--out", str(file)]), 2)
            self.assertEqual(file.read_bytes(), original)

    def test_online_history_keeps_unmapped_leagues_and_reads_plain_score_pairs(self):
        payload = {"matches": [{"date":"2025-05-01", "team1":"A", "team2":"B", "score":[0, 1]}]}
        with patch.object(sources, "fetch_bytes", return_value=json.dumps(payload).encode()) as get:
            result = sources.collect(sources.parser().parse_args(["history", "--league", "de.1"]))
            self.assertEqual(result["records"][0]["competition"], "de.1")
            self.assertEqual(result["records"][0]["away_goals"], 1)
            with self.assertRaises(ValueError):
                sources.collect(sources.parser().parse_args(["history", "--league", "de.1", "--competition", "PL"]))
            self.assertEqual(get.call_count, 1)

    def test_history_csv_preserves_divisions_and_overrides_only_single_league_files(self):
        header = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
        first = "E0,08/04/25,A,B,2,1\n"
        second = "E1,09/04/25,C,D,0,0\n"
        with tempfile.TemporaryDirectory() as tmp:
            csv_file = pathlib.Path(tmp) / "scores.csv"
            def imported(text, *options):
                csv_file.write_text(text, encoding="utf-8")
                args = sources.parser().parse_args(["history", "--csv", str(csv_file), *options])
                return sources.collect(args)["records"]

            one = imported(header + first, "--competition", "PL")[0]
            self.assertEqual((one["competition"], one["source_division"]), ("PL", "E0"))
            unlabelled = "Date,HomeTeam,AwayTeam,FTHG,FTAG\n08/04/25,A,B,2,1\n"
            self.assertEqual(imported(unlabelled, "--competition", "PL")[0]["competition"], "PL")
            many = imported(header + first + second)
            self.assertEqual([r["competition"] for r in many], ["E0", "E1"])
            with self.assertRaisesRegex(ValueError, "multiple Div"):
                imported(header + first + second, "--competition", "PL")
            with self.assertRaisesRegex(ValueError, "without Div"):
                imported(header + first + second + ",10/04/25,B,D,1,1\n")

    def test_credential_scope_and_fixtures(self):
        data = {"matches": [{"id": 12, "utcDate": "2026-09-20T20:00:00Z", "status": "TIMED",
                "competition": {"code": "PL"}, "homeTeam": {"name": "A", "id": 1}, "awayTeam": {"name": "B", "id": 2}}]}
        with patch.dict("os.environ", {"FOOTBALL_DATA_TOKEN": "test-secret"}), patch.object(sources, "fetch_bytes", return_value=json.dumps(data).encode()) as get:
            result = sources.collect(sources.parser().parse_args(["fixtures", "--competition", "PL", "--from", "2026-09-20", "--to", "2026-09-21"]))
        self.assertNotIn("test-secret", json.dumps(result))
        self.assertEqual(get.call_args.kwargs["headers"]["X-Auth-Token"], "test-secret")
        self.assertEqual(result["records"][0]["market"], "1x2_90")
        with self.assertRaises(ValueError):
            sources._check_origin("https://api.football-data.org.invalid/path", "api.football-data.org", False)
        r = urllib.request.Request("https://api.football-data.org/matches", headers={"X-Auth-Token": "test-secret"})
        with self.assertRaises(ValueError):
            sources.SameOriginRedirect().redirect_request(r, None, 302, "", {}, "https://example.com/tokens")

    def test_three_way_quotes_and_redaction(self):
        def book(key, prices):
            return {"key": key, "last_update": "2026-05-03T16:30:00Z", "markets": [{"key": "h2h", "outcomes":
                [{"name": name, "price": price} for name, price in prices.items()]}]}
        event = {"id": "e", "home_team": "A", "away_team": "B", "commence_time": "2026-05-03T19:00:00Z",
                 "bookmakers": [book("two", {"A": 2, "B": 3}), book("complete", {"B": 4, "Draw": 3, "A": 2})]}
        with patch.dict("os.environ", {"THE_ODDS_API_KEY": "test-secret"}), patch.object(sources,"fetch_bytes",return_value=json.dumps([event]).encode()) as get:
            result = sources.collect(sources.parser().parse_args(["odds"]))
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["records"][0]["odds"], [2., 3., 4.])
        self.assertIn("Skipped 1", result["warnings"][0])
        self.assertIn("test-secret", get.call_args.args[0])
        self.assertNotIn("test-secret", json.dumps(result))

    def test_h2h_uses_regulation_score_only(self):
        record = {"id": 1, "status": "FINISHED", "utcDate": "2026-05-01T18:00:00Z",
                  "homeTeam": {"name":"A"}, "awayTeam":{"name":"B"},
                  "score": {"duration":"PENALTY_SHOOTOUT","fullTime":{"home":5,"away":4}}}
        with_regulation = {**record,"score":{**record["score"],"regularTime":{"home":0,"away":0}}}
        data=json.dumps({"matches":[record,with_regulation]}).encode()
        rows,warnings=sources.h2h_records(data)
        self.assertEqual([(r["home_goals"],r["away_goals"]) for r in rows],[(0,0)])
        self.assertIn("Skipped 1",warnings[0])

    def test_squad_and_injury_ids_from_their_own_providers(self):
        team = {"id": 123, "name": "Team A", "squad": [{"name": "J. Lee", "id": 9, "dateOfBirth": "2000-04-03"}]}
        with patch.dict("os.environ", {"FOOTBALL_DATA_TOKEN": "private"}), patch.object(sources,"fetch_bytes", return_value=json.dumps(team).encode()) as get:
            squad = sources.collect(sources.parser().parse_args(["squad", "--team-id", "123"]))
        self.assertEqual(squad["records"][0]["date_of_birth"], "2000-04-03")
        self.assertIn("/v4/teams/123",get.call_args.args[0])
        data = {"response": [{"team": {"id": 6,"name":"A"}, "player": {"id": 7, "name":"J. Lee","type":"Questionable"},
                              "fixture": {"id":444,"date":"2026-05-03T20:00:00Z"}}], "errors": []}
        with patch.dict("os.environ", {"API_FOOTBALL_KEY": "private"}), patch.object(sources,"fetch_bytes",return_value=json.dumps(data).encode()) as get:
            report = sources.collect(sources.parser().parse_args(["injuries","--fixture-id","444"]))
        self.assertEqual(get.call_args.kwargs["allowed_host"], "v3.football.api-sports.io")
        self.assertNotIn("private",json.dumps(report))
        self.assertEqual(report["records"][0]["status"],"Questionable")
        with self.assertRaisesRegex(ValueError,"rejected"):
            sources.injury_records(b'{"response":[],"errors":{"quota":"exceeded"}}')

    def test_club_missing_bins_and_home_perspective(self):
        bins = ["GD<-5"] + [f"GD={i}" for i in range(-5, 6)] + ["GD>5"]
        header = ",".join(["Home", "Away", "Date", *bins, "R:2-1"])
        values = [str({-1: .2, 0: .3, 1: .5}.get(i, 0)) for i in range(-6, 7)]
        good = ",".join(["A", "B", "2026-08-01", *values, ".12"])
        bad = good.replace(",0.3,", ",,")
        rows,warnings = sources.club_records(("\n".join([header,good,bad])).encode(), "B")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["upstream_probs"], [.5, .3, .2])
        self.assertEqual(rows[0]["top_scores"], [{"home": 2, "away": 1, "p": .12}])
        self.assertIn("Skipped 1", warnings[0])
        self.assertEqual(sources.ratings_records(b"Club,Elo,Country\nA,1600,NED\nB,,GER\n")[0][0]["elo"],1600)

    def test_weather_matches_utc_hour_and_news_is_metadata(self):
        data = {"latitude": 1, "longitude": 2, "hourly": {"time": ["2026-08-01T18:00"],
                 "temperature_2m": [20], "precipitation_probability": [None], "wind_speed_10m": [10]},
                "hourly_units": {"temperature_2m":"C","precipitation_probability":"%","wind_speed_10m":"km/h"}}
        rows,_=sources.weather_records(json.dumps(data).encode(),sources._utc("2026-08-01T20:30:00+02:00"))
        self.assertEqual(rows[0]["temperature_2m"],20)
        self.assertIsNone(rows[0]["precipitation_probability"])
        self.assertFalse(sources.weather_records(json.dumps(data).encode(),sources._utc("2026-08-02T18:00:00Z"))[0])
        rss = b"<rss><channel><item><title>Team selection</title><link>https://example.org/item1</link></item></channel></rss>"
        items,warnings=sources.news_records(rss, 5)
        self.assertEqual(items[0]["headline"], "Team selection")
        self.assertNotIn("delta_xg", items[0])
        self.assertTrue(warnings)

    def test_current_clubelo_pages_confirm_dates_and_read_both_fixture_rows(self):
        rankings = b'''<h1><a href="/2026-11-16/Ranking">Ranking</a></h1>
        <script>const eloData = [['<td><a href="/ENG"><img alt="ENG"></a><a href="/x">Town<span> FC</span></a></td>', '1563', '0', '1']];</script>'''
        self.assertEqual(sources.rating_html_records(rankings, "Town FC")[0][0]["elo"], 1563)
        with self.assertRaisesRegex(ValueError,"expected"):
            sources.rating_html_records(rankings,requested_date="2025-08-01")
        fixtures = b'''<table><tr><td data-live-status-game-id="1"><span data-utc-time="2099-12-01T14:00Z"></span></td>
        <td><a><span class="max640">A</span><span class="min641">Alpha</span></a></td>
        <td><span class="min1081">50.5</span><span class="max1080">51</span></td><td><span class="min1081">29.5</span></td></tr>
        <tr><td><a><span class="min641">Beta</span></a></td><td><span class="min1081">20</span></td></tr></table>'''
        row = sources.club_html_records(fixtures, "Beta")[0][0]
        self.assertEqual([row["home"],row["away"],row["upstream_probs"]], ["Alpha","Beta",[.505,.295,.2]])
        self.assertFalse(row["top_scores"])


if __name__ == "__main__":
    unittest.main()
