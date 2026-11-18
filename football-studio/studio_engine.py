"""Map browser inputs to the bundled football-forecast-lab operations."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine"))

import calibrate
import competitions
import external
import fitting
import football
import ledger
import localization
import ratings
import reporting
import simulation
import sources
from workflow import records


def data_dir():
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return Path(os.environ.get("FOOTBALL_STUDIO_DATA") or base / "FootballForecastStudio")


def examples():
    return {path.stem.replace("-", "_"): football.load(path)
            for path in sorted((ROOT / "examples").glob("*.json"))}


def ledger_records():
    path = data_dir() / "forecasts.sqlite"
    if not path.exists():
        return {"records": []}
    with closing(sqlite3.connect(path, timeout=15)) as db:
        rows = db.execute("""
            SELECT f.input, f.frozen, f.prospective, r.home_goals, r.away_goals
            FROM forecasts f LEFT JOIN results r ON f.fixture = r.fixture
            ORDER BY f.frozen DESC, f.cutoff DESC, f.fixture
        """)
        data = []
        for body, frozen, prospective, home_goals, away_goals in rows:
            match = json.loads(body)
            data.append({**{k: match.get(k) for k in ("home", "away", "competition", "stage", "kickoff", "as_of", "demo",
                                                    "source", "competition_id", "home_id", "away_id", "country",
                                                    "home_zh", "away_zh", "competition_zh", "stage_zh", "translation",
                                                    "home_aliases", "away_aliases", "competition_aliases", "stage_aliases",
                                                    "source_url", "source_endpoint", "provenance")},
                         "frozen_at": frozen, "prospective": bool(prospective),
                         "home_goals": home_goals, "away_goals": away_goals})
    from localization import localize_rows
    return {"records": localize_rows(data)}


def json_file(folder, name, data):
    path = Path(folder) / (name + ".json")
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def flag(payload, key):
    value = payload.get(key, False)
    if type(value) is not bool:
        raise ValueError(f"{key} 必须为布尔值")
    return value


def forecast(payload, folder):
    fixtures = payload["input"]
    if "knockout" in payload and not flag(payload, "knockout"):
        # An explicit UI switch overrides the per-fixture default in an import.
        fixtures = copy.deepcopy(fixtures)
        for match in records(fixtures):
            match.pop("knockout", None)
    args = football.parser().parse_args(["forecast", str(json_file(folder, "input", fixtures))])
    args.localize = localization.localize_rows
    for key in ("history", "aliases", "fit", "calibration", "scenarios"):
        if payload.get(key) is not None:
            setattr(args, key, json_file(folder, key, payload[key]))
    for key in ("snapshot", "context"):
        documents = payload.get(key + "s", [])
        if not isinstance(documents, list) or any(not isinstance(doc, dict) for doc in documents):
            raise ValueError(f"{key}s 需要 JSON 快照对象数组")
        setattr(args, key, [json_file(folder, f"{key}-{i}", doc) for i, doc in enumerate(documents)])
    for key in ("home", "away", "as_of", "bookmaker", "handicap", "total"):
        if payload.get(key) is not None:
            setattr(args, key, payload[key])
    for key in ("matrix", "timeline", "knockout"):
        setattr(args, key, flag(payload, key))
    if flag(payload, "ledger"):
        args.ledger = data_dir() / "forecasts.sqlite"
    return football.forecast(args)


# The API accepts uploaded CSV content. Local paths and output paths are never
# accepted as source parameters.
SOURCE_FIELDS = {
    "fixtures": {"competition": None, "date_from": None, "date_to": None},
    "h2h": {"fixture_id": None},
    "odds": {"sport": "soccer_epl", "regions": "eu", "bookmaker": None},
    "squad": {"team_id": None},
    "injuries": {"fixture_id": None},
    "ratings": {"team": None, "date": None, "csv": None},
    "club-forecast": {"team": None, "csv": None},
    "weather": {"lat": None, "lon": None, "kickoff": None},
    "news": {"query": None, "limit": 15},
    "history": {"season": "2024-25", "league": "en.1", "csv": None, "competition": None},
}

REQUIRED_FIELDS = {"h2h": ("fixture_id",), "squad": ("team_id",), "injuries": ("fixture_id",),
                   "weather": ("lat", "lon", "kickoff"), "news": ("query",)}


def source_snapshot(payload, folder):
    kind = payload["kind"]
    if kind not in SOURCE_FIELDS:
        raise ValueError("未知的数据来源")
    args = argparse.Namespace(kind=kind)
    for key, default in SOURCE_FIELDS[kind].items():
        value = payload.get(key, default)
        if value is None or value == "":
            value = default
        if value is not None and key == "csv":
            if not isinstance(value, str):
                raise ValueError("CSV 需要完整文本")
            path = Path(folder) / f"{kind}.csv"
            path.write_text(value, encoding="utf-8")
            value = path
        elif value is not None and key in ("lat", "lon"):
            value = float(value)
        elif value is not None and key == "limit":
            value = int(value)
        elif value is not None:
            value = str(value)
        setattr(args, key, value)
    for key in REQUIRED_FIELDS.get(kind, ()):
        if getattr(args, key) is None:
            raise ValueError(f"{kind} 需要填写 {key}")
    token = {"fixtures": "FOOTBALL_DATA_TOKEN", "h2h": "FOOTBALL_DATA_TOKEN", "squad": "FOOTBALL_DATA_TOKEN",
             "odds": "THE_ODDS_API_KEY", "injuries": "API_FOOTBALL_KEY"}.get(kind)
    if token and not os.environ.get(token, "").strip():
        raise ValueError(f"此体育数据源需要单独的访问密钥。请设置环境变量 {token} 后重启研究室。")
    return sources.collect(args)


def external_snapshot(payload):
    action = payload["action"]
    if action == "recent":
        return external.recent(payload.get("limit", 25))
    if action == "resolve":
        if not isinstance(payload["slugs"], list) or not payload["slugs"]:
            raise ValueError("需要提供至少一个赛事 slug")
        return external.resolve(payload["slugs"])
    if action == "predict":
        return external.prediction(payload["slug"], context=flag(payload, "context"), edits=payload.get("signals"))
    raise ValueError("未知的外部模型操作")


COMMANDS = {"forecast", "cup", "backtest", "fit", "elo", "calibrate", "combo", "sources", "simulation",
            "external", "review", "archive", "settle", "report", "collector/search", "collector/predict", "collector/localize"}


def run(command, payload):
    if command.startswith("collector/"):
        import collector
        if command == "collector/search":
            return collector.collect(payload)
        if command == "collector/localize":
            return collector.localize_collection(payload)
        return collector.predict(payload)
    if command == "simulation":
        return simulation.simulate(payload)
    if command in ("forecast", "sources", "combo"):
        with tempfile.TemporaryDirectory(prefix="football-studio-") as folder:
            if command == "forecast":
                return forecast(payload, folder)
            if command == "sources":
                return source_snapshot(payload, folder)
            args = argparse.Namespace(**{key: json_file(folder, key, payload[key]) for key in ("forecasts", "picks")})
            return football.combo(args)
    if command == "cup":
        return {**competitions.simulate_tournament(payload["input"], sims=payload.get("sims", 1000),
                                                   seed=payload.get("seed", 7)), "kind": "cup"}
    if command == "backtest":
        original = payload["history"]
        history = records(original)
        result = competitions.backtest_rows(history, min_train=payload.get("min_train", 20), window=payload.get("window"))
        dataset = {key: original[key] for key in ("source", "endpoint", "observed_at", "raw_sha256")
                   if isinstance(original, dict) and key in original}
        return {**result, "kind": "backtest", "dataset": {**dataset, "rows": len(history)}}
    if command in ("elo", "fit"):
        args = (records(payload["history"]), payload["as_of"], payload.get("competition"))
        if command == "elo":
            return ratings.historical_elo(*args)
        return {**fitting.fit_strength(*args), "kind": "fit"}
    if command == "calibrate":
        kwargs = {k: payload[k] for k in ("min_fit", "min_validation", "fit_fraction", "competition") if k in payload}
        return calibrate.fit_calibration(payload["backtest"], **kwargs)
    if command == "external":
        return external_snapshot(payload)
    if command == "report":
        return {"html": reporting.render_html(payload["result"])}
    path = data_dir() / "forecasts.sqlite"
    if command == "settle":
        return {**ledger.settle(path, records(payload["results"])), "kind": "settle"}
    if command == "review":
        return {**ledger.review(path), "kind": "review"}
    if command == "archive":
        return ledger.archived(path, payload, payload["as_of"])
    raise ValueError("未知的分析功能")
