"""Offline display, asynchronous upgrades and source-identity regressions."""
import json
import os
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import localization as names
from offline_names import transliterate


class NameLocalizationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="studio-names-")
        self.env = patch.dict(os.environ, {"FOOTBALL_STUDIO_DATA": self.folder.name})
        self.env.start()
        with names._lock:
            names._memory.clear()
            names._pending.clear()
            names._cooldowns.clear()
        self.model = patch.object(names, "_model_batch", return_value={})
        self.lookup = patch.object(names, "_lookup", side_effect=OSError("offline"))
        self.model_mock = self.model.start()
        self.lookup_mock = self.lookup.start()

    def tearDown(self):
        for future in list(names._pending.values()):
            future.result(timeout=5)
        self.lookup.stop()
        self.model.stop()
        self.env.stop()
        self.folder.cleanup()

    def test_unknown_names_have_immediate_chinese_during_a_slow_model_request(self):
        release = threading.Event()
        started = threading.Event()
        def slow_model(items):
            started.set()
            release.wait(3)
            return {}
        self.model_mock.side_effect = slow_model
        rows = [{"home": "Brockhaven Women U19", "away": "Zelovik II",
                 "competition": "Nordland Regional Division 2", "stage": "Group B",
                 "source": "test", "competition_id": "4", "provenance": {"url": "fixture-source"}}]
        before = json.dumps(rows)
        try:
            start = time.monotonic()
            output = names.localize_rows(rows)
            self.assertLess(time.monotonic() - start, 1.5)
            self.assertTrue(started.wait(1))
            for field in names.FIELDS:
                self.assertRegex(output[0][field + "_zh"], r"[\u3400-\u9fff]")
                self.assertEqual(output[0][field], rows[0][field])
            self.assertTrue(output[0]["home_zh"].endswith("女足U19"))
            self.assertTrue(output[0]["away_zh"].endswith("二队"))
            self.assertTrue(output[0]["translation"]["home"]["pending"])
            summary = names.translation_summary(output)
            self.assertTrue(summary["ready"])
            self.assertFalse(summary["complete"])
            self.assertGreater(summary["pending_count"], 0)
            self.assertIsInstance(summary["pending"], list)
            self.assertEqual(json.dumps(rows), before)
        finally:
            release.set()

    def test_legacy_failed_cache_is_upgraded_to_offline_chinese(self):
        row = {"home": "Riverton Athletic", "away": "Arsenal", "competition": "English Premier League"}
        item = (row["home"], "team", names._context(row, "home"))
        names._save(names._key(item), names._result(row["home"], row["home"], "unavailable", "retry"))
        row["home_zh"] = row["home"]
        row["translation"] = {"home": names._result(row["home"], row["home"], "unavailable", "retry")}
        localized = names.localize_rows([row], timeout=3)[0]
        self.assertNotEqual(localized["home_zh"], row["home"])
        self.assertEqual(localized["translation"]["home"]["status"], "transliteration")
        self.assertTrue(localized["translation"]["home"]["provisional"])
        self.assertFalse(localized["translation"]["home"]["pending"])

    def test_completed_model_replaces_supplied_provisional_and_retains_search_alias(self):
        release = threading.Event()
        def model(items):
            release.wait(3)
            return {key: names._result(item[0], "河畔竞技", "model", "machine") for key, item in items}
        self.model_mock.side_effect = model
        row = {"home": "Riverton Athletic", "away": "France"}
        first = names.localize_rows([row])
        provisional = first[0]["home_zh"]
        release.set()
        for future in list(names._pending.values()):
            future.result(timeout=3)
        second = names.localize_rows(first)
        self.assertEqual(second[0]["home_zh"], "河畔竞技")
        self.assertEqual(second[0]["translation"]["home"]["status"], "machine")
        self.assertIn(provisional, second[0]["home_aliases"])
        self.assertIn(row["home"], second[0]["home_aliases"])
        self.lookup_mock.assert_not_called()

    def test_completion_race_cannot_leave_old_label_without_a_poll_signal(self):
        finish_model = threading.Event()
        saving = threading.Event()
        real_cached, real_save = names._cached, names._save
        intercepted = [False]
        def model(items):
            finish_model.wait(2)
            return {key: names._result(item[0], "河畔竞技", "model", "machine") for key, item in items}
        def save(key, result):
            if result["status"] == "machine":
                saving.set()
            return real_save(key, result)
        def cached(key):
            snapshot = real_cached(key)
            if names._pending and snapshot and snapshot.get("provisional") and not intercepted[0]:
                intercepted[0] = True
                finish_model.set()
                self.assertTrue(saving.wait(1))
                time.sleep(0.03)
            return snapshot
        self.model_mock.side_effect = model
        with patch.object(names, "_cached", side_effect=cached), patch.object(names, "_save", side_effect=save):
            result = names.localize_rows([{"home": "Riverton Athletic", "away": "France"}])[0]
        finish_model.set()
        self.assertTrue(intercepted[0])
        self.assertTrue(result["home_zh"] == "河畔竞技" or result["translation"]["home"]["pending"])

    def test_automatic_retries_are_bounded_and_manual_retry_respects_delay(self):
        clock = [1000]
        row = {"home": "Zelovik", "away": "France"}
        with patch.object(names.time, "time", side_effect=lambda: clock[0]):
            first = names.localize_rows([row], timeout=3)
            self.assertEqual(first[0]["translation"]["home"]["attempts"], 1)
            second = names.localize_rows(first, retry=True, timeout=3)
            self.assertEqual(second[0]["translation"]["home"]["attempts"], 1)
            self.assertEqual(first, second)
            for expected in (2, 3):
                clock[0] = second[0]["translation"]["home"]["retry_after"] + 1
                second = names.localize_rows(second, timeout=3)
                self.assertEqual(second[0]["translation"]["home"]["attempts"], expected)
            self.assertIsNone(second[0]["translation"]["home"]["retry_after"])
            self.assertFalse(second[0]["translation"]["home"]["auto_retry"])
            clock[0] += 86400
            third = names.localize_rows(second, timeout=3)
            self.assertEqual(third, second)
            self.assertEqual(self.lookup_mock.call_count, 3)

    def test_provider_registry_and_provenance_preserve_competition_identity(self):
        registry = {"espn:730": {"zh": "意大利甲级联赛", "aliases": ["意甲"], "names": ["Serie A"]},
                    "espn:630": {"zh": "巴西甲级联赛", "aliases": ["巴甲"], "names": ["Serie A"]},
                    "espn:20956": {"zh": "西班牙女子甲级联赛", "aliases": ["西女甲"], "names": ["Liga F"]}}
        with patch.object(names, "_competitions", registry):
            rows = [{"competition": "Serie A", "source": "espn", "competition_id": "630",
                     "competition_aliases": ["意甲"], "translation": {"competition": names._result("Serie A", "意大利甲级联赛", "dictionary", "dictionary")}},
                    {"competition": "Serie A", "provenance": {"provider": "espn", "competition_id": "730"}},
                    {"home": "Madrid Rovers", "away": "Unknown Town", "competition": "Liga F", "source": "espn", "competition_id": "20956"}]
            output = names.localize_rows(rows, timeout=3)
            self.assertEqual(output[0]["competition_zh"], "巴西甲级联赛")
            self.assertNotIn("意甲", output[0]["competition_aliases"])
            self.assertEqual(output[1]["competition_zh"], "意大利甲级联赛")
            self.assertIn("女足", output[2]["home_zh"])
            other = {**rows[0], "source": "different-provider"}
            self.assertNotEqual(names._context(rows[0], "competition"), names._context(other, "competition"))

    def test_changed_team_name_discards_old_display_aliases(self):
        row = {"home": "France", "home_zh": "德国", "home_aliases": ["德国", "日耳曼"],
               "translation": {"home": names._result("Germany", "德国", "dictionary", "dictionary")}}
        result = names.localize_rows([row])[0]
        self.assertEqual(result["home_zh"], "法国")
        self.assertNotIn("日耳曼", result["home_aliases"])

    def test_named_roman_numeral_is_not_reinterpreted_as_a_reserve_team(self):
        result = names.localize_rows([{"home": "Willem II", "away": "Ajax II"}], timeout=3)[0]
        self.assertEqual(result["home_zh"], "威廉二世")
        self.assertTrue(result["away_zh"].endswith("二队"))

    def test_demo_labels_are_scoped_to_explicit_demo_rows(self):
        row = {"home": "Harbor XI", "away": "Pine XI", "competition": "Demo League", "demo": True}
        demo = names.localize_rows([row])[0]
        self.assertEqual([demo[k] for k in ("home_zh", "away_zh", "competition_zh")],
                         ["海港竞技", "松林联队", "研究室演示联赛"])
        actual = names.localize_rows([{**row, "demo": False}], timeout=3)[0]
        self.assertNotEqual(actual["home_zh"], "海港竞技")
        self.assertEqual(actual["home"], "Harbor XI")

    def test_unidentified_generic_league_does_not_inherit_another_countrys_alias(self):
        result = names.localize_rows([{"competition": "Serie A", "source": "another-provider", "country": "Brazil",
                                      "competition_zh": "意大利甲级联赛", "competition_aliases": ["意甲"],
                                      "translation": {"competition": names._result("Serie A", "意大利甲级联赛", "dictionary", "dictionary")}}], timeout=3)[0]
        self.assertNotIn("意大利", result["competition_zh"])
        self.assertNotIn("意甲", result["competition_aliases"])

    def test_name_request_context_excludes_source_text(self):
        row = {"source": "PRIVATE SOURCE TEXT", "competition_id": "3", "country": "Brazil",
               "competition": "Regional League", "probs": [.3, .3, .4]}
        context = names._context(row, "home")
        self.assertIn("PRIVATE SOURCE TEXT".casefold(), context)
        public = names._public_context(context)
        self.assertIn("Brazil", public)
        self.assertIn("Regional League", public)
        self.assertNotIn("PRIVATE", public.upper())
        self.assertNotIn("probs", public)

    def test_offline_spelling_handles_accents_and_football_structure(self):
        self.assertEqual(transliterate("Łódź"), transliterate("Lodz"))
        self.assertEqual(transliterate("São Cristóvão"), transliterate("Sao Cristovao"))
        label = transliterate("Brazilian Regional Division 2 Women U17", "competition")
        self.assertIn("巴西", label)
        self.assertIn("第二级联赛", label)
        self.assertIn("女子", label)
        self.assertIn("17岁以下", label)
        for original in ("Aparecidense", "Zwevegem", "Динамо", "Ατρόμητος", "アビスパ", "서울", "123"):
            self.assertRegex(transliterate(original), r"[\u3400-\u9fff]")

    def test_shutdown_cancels_large_queue_without_waiting_for_unstarted_names(self):
        script = r'''
import os, tempfile, threading, time
import localization as names
release = threading.Event()
started = threading.Event()
calls = []
def lookup(item):
    calls.append(item)
    started.set()
    release.wait(3)
    raise OSError("offline")
names._lookup = lookup
names._model_batch = lambda items: {}
with tempfile.TemporaryDirectory() as folder:
    os.environ["FOOTBALL_STUDIO_DATA"] = folder
    rows = [{"home": "Unknownqword" + str(i), "away": "France"} for i in range(150)]
    names.localize_rows(rows)
    assert started.wait(1)
    begin = time.monotonic()
    names.shutdown()
    assert time.monotonic() - begin < 0.5
    release.set()
    until = time.monotonic() + 2
    while any(t.name.startswith(("name-batch", "name-lookup")) for t in threading.enumerate()) and time.monotonic() < until:
        time.sleep(0.02)
    assert not any(t.name.startswith(("name-batch", "name-lookup")) for t in threading.enumerate())
    assert len(calls) <= 4, len(calls)
print("queue shutdown completed")
'''
        completed = subprocess.run([sys.executable, "-B", "-c", script], cwd=Path(__file__).resolve().parents[1],
                                   capture_output=True, text=True, timeout=7)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("queue shutdown completed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
