"""Provider placeholder names must remain ineligible after display translation."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector import unavailable


class FixtureIdentityTests(unittest.TestCase):
    def test_pending_teams_do_not_become_predictable_through_a_chinese_label(self):
        now = datetime.now(timezone.utc)
        row = {"status": "SCHEDULED", "time_confirmed": True, "kickoff": (now + timedelta(days=2)).isoformat(),
               "home": "Known United", "away": "Known City", "home_id": "123", "away_id": "456"}
        self.assertEqual(unavailable(row, now), "")
        for side in ("home", "away"):
            for name in ("TBD Home", "TBD Away", "TBD", "to be determined", "主队待定", "客队待定"):
                with self.subTest(side=side, name=name):
                    changed = {**row, side: name, side + "_zh": "中文显示"}
                    self.assertEqual(unavailable(changed, now), "参赛球队待确认")
            self.assertEqual(unavailable({**row, side + "_id": "0"}, now), "参赛球队待确认")


if __name__ == "__main__":
    unittest.main()
