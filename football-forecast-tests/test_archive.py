import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'football-forecast-lab'/'scripts'))
from ledger import archived, freeze
from football import forecast, parser


class ArchiveTest(unittest.TestCase):
    def test_raw_final_scores_and_unknown_status_cannot_enter_forecast(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'match.json'
            base = {"home":"H","away":"A","kickoff":"2025-05-01T13:00Z","as_of":"2025-05-01T10:00Z"}
            args = parser().parse_args(["forecast",str(path)])
            for bad in ({"home_goals":0,"away_goals":0},{"status":"FT"},{"status":"AET"},{"status":"UNKNOWN"}):
                path.write_text(json.dumps({**base,**bad}),encoding="utf8")
                with self.assertRaises(ValueError):
                    forecast(args)
            path.write_text(json.dumps({**base,"status":"NS"}),encoding="utf8")
            self.assertEqual(len(forecast(args)["matches"]),1)

    def test_snapshot_render_options_do_not_conflict_with_core_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.sqlite'
            m = {"home":"H","away":"A","kickoff":"2025-05-01T13:00Z","as_of":"2025-05-01T10:00Z"}
            baseline = {"input":m, "prediction":{"probs":[.4,.3,.3]}, "scenarios":[]}
            expanded = {**baseline,"prediction":{**baseline["prediction"],"score_matrix":[[1]]},"scenarios":[{"name":"What if"}]}
            freeze(path, [baseline], [], captured_at="2025-05-01T10:01Z")
            freeze(path, [expanded], [], captured_at="2025-05-02T10:00Z")
            freeze(path, [expanded], [], captured_at="2025-05-03T10:00Z")
            entry = archived(path,m,m["as_of"])
            self.assertTrue(entry["prospective"])
            self.assertEqual(len(entry["reports"]),2)
            self.assertEqual(entry["reports"][1]["captured_at"],"2025-05-02T10:00Z")
            self.assertEqual(entry["reports"][1]["report"]["scenarios"],[{"name":"What if"}])
            self.assertEqual(entry["history"],[])
