import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'football-forecast-lab' / 'scripts'))
from ratings import historical_elo, recent_form


class RatingsTest(unittest.TestCase):
    def setUp(self):
        self.history = [
            {"date":"2025-01-07","competition":"Demo","home":"A","away":"B","home_goals":1,"away_goals":0,"neutral":True},
            {"date":"2025-01-09","competition":"Demo","home":"A","away":"C","home_goals":0,"away_goals":1},
            {"date":"2025-01-08","competition":"Demo","home":"A","away":"D","home_goals":0,"away_goals":0,
             "result_available_at":"2025-01-20T01:00Z"},
        ]
        self.match = {"home":"A","away":"B","competition":"Demo","kickoff":"2025-01-10T20:00Z","as_of":"2025-01-09T17:00Z"}

    def test_known_neutral_result_and_delayed_labels(self):
        r = historical_elo(self.history, self.match["as_of"], "Demo")
        self.assertEqual({v["team"]:v["elo"] for v in r["records"]},{"A":1510,"B":1490})
        self.assertEqual(r["matches"],1)
        view = recent_form(self.match,self.history)
        self.assertEqual(view["teams"]["A"]["W"],1)
        self.assertEqual(view["teams"]["A"]["days_since_last_listed_game"],3)
        self.assertEqual(view["head_to_head"][0]["score"],[1,0])

    def test_day_order_independent_and_total_preserved(self):
        other = dict(self.history[0], home="C",away="A")
        first = historical_elo([self.history[0],other], self.match["as_of"], "Demo")
        second = historical_elo([other,self.history[0]], self.match["as_of"], "Demo")
        self.assertEqual(first["records"],second["records"])
        self.assertEqual(sum(r["elo"] for r in first["records"]),4500)
