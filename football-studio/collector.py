"""Collect a time window, recheck selected fixtures and run the original forecast engine."""
import json
import re
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime, time, timedelta

import studio_engine
import schedule_sources as feeds
from localization import localize_rows, translation_summary

POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fixture-source")
LOCKS = [threading.Lock() for _ in range(64)]
FIXTURE_TTL = timedelta(minutes=10)
HISTORY_TTL = timedelta(hours=6)


def time_range(payload):
    def boundary(value, is_end):
        if not isinstance(value, str):
            raise ValueError("请填写开始和结束时间")
        if len(value) == 10:
            day = date.fromisoformat(value) + timedelta(days=int(is_end))
            return datetime.combine(day, time.min, feeds.HK).astimezone(feeds.UTC)
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=feeds.HK)
        return value.astimezone(feeds.UTC)

    start = boundary(payload.get("start"), False)
    end = boundary(payload.get("end"), True)
    if end <= start:
        raise ValueError("结束时间须晚于开始时间")
    return start, end


def connection():
    folder = studio_engine.data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / "fixtures.sqlite", timeout=25)
    db.execute("CREATE TABLE IF NOT EXISTS snapshots (key TEXT PRIMARY KEY, seen TEXT NOT NULL, value TEXT NOT NULL)")
    return db


def cached(key):
    with closing(connection()) as db:
        record = db.execute("SELECT seen, value FROM snapshots WHERE key = ?", (key,)).fetchone()
    return (record[0], json.loads(record[1])) if record else (None, None)


def save(key, value, seen=None):
    seen = seen or feeds.stamp()
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    with closing(connection()) as db, db:
        db.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?)", (key, seen, encoded))
    return seen


def retrieve(key, fetch, ttl, allow_stale=True):
    with LOCKS[hash(key) % len(LOCKS)]:
        seen, value = cached(key)
        if seen and datetime.now(feeds.UTC) - feeds.timestamp(seen) < ttl:
            return value, seen, None
        try:
            value = fetch()
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            if allow_stale and seen:
                return value, seen, f"联网失败，显示 {seen} 的缓存（{exc}）"
            return None, None, str(exc)
        return value, save(key, value), None


def refresh_window(args):
    source, window, mode = args
    key = f"schedule:v3:{source}:{window}"
    value, seen, issue = retrieve(key, lambda: feeds.schedule(source, window),
                                  timedelta(0) if mode else FIXTURE_TTL, allow_stale=mode != "verify")
    if value is not None:
        for row in value["rows"]:
            if row.get("provenance"):
                row["provenance"] = {**row["provenance"], "observed_at": seen}
    return window, value, seen, issue


def unavailable(row, now):
    if row["status"] not in ("SCHEDULED", "TIMED"):
        return {"FINISHED": "已完场", "LIVE": "比赛进行中", "IN_PLAY": "比赛进行中",
                "POSTPONED": "已延期", "CANCELED": "已取消", "CANCELLED": "已取消"}.get(row["status"], "当前状态不可赛前预测")
    if not row["time_confirmed"]:
        return "开球时间待确认"
    if feeds.timestamp(row["kickoff"]) <= now:
        return "已到开球时间"
    for side in ("home", "away"):
        label = str(row.get(side) or "").strip().casefold()
        waiting = re.fullmatch(r"tbd(?:\s+(?:home|away))?|(?:home|away)\s+tbd|to be determined|unknown|待定|(?:主|客)队待定", label)
        if not row.get(side + "_id") or str(row[side + "_id"]) == "0" or not label or waiting:
            return "参赛球队待确认"
    if row["home_id"] == row["away_id"] or row["home"].casefold() == row["away"].casefold():
        return "对阵信息待核实"
    return ""


def collect(payload):
    source = payload.get("source", "espn")
    if source not in feeds.LABELS:
        raise ValueError("未知的赛程数据源")
    if source == "football-data":
        feeds.fd_headers()
    start, end = time_range(payload)
    refresh = studio_engine.flag(payload, "refresh")
    windows = list(feeds.schedule_windows(source, start, end))
    fixtures, issues = {}, []
    succeeded = 0
    for window, packet, seen, issue in POOL.map(refresh_window, ((source, w, refresh) for w in windows)):
        if issue:
            issues.append(f"{window} · {issue}")
        else:
            succeeded += 1
        if packet is None:
            continue
        issues.extend(packet["issues"])
        for row in packet["rows"]:
            if not start <= feeds.timestamp(row["kickoff"]) < end:
                continue
            old = fixtures.get(row["id"])
            if old is None or old["observed_at"] < seen:
                fixtures[row["id"]] = {**row, "observed_at": seen, "source_window": window, "cached_offline": bool(issue)}
    observed = datetime.now(feeds.UTC)
    unique = {}
    for row in fixtures.values():
        key = (row["competition_id"], row["home_id"], row["away_id"], row["kickoff"])
        old = unique.get(key)
        if old is None or old["observed_at"] < row["observed_at"]:
            unique[key] = row
    ordered = sorted(unique.values(), key=lambda r: (r["kickoff"], r["competition"] or "", r["id"]))
    for row in ordered:
        row["reason"] = unavailable(row, observed)
        row["eligible"] = not row["reason"]
    ordered = localize_rows(ordered, retry=refresh)
    result = {
        "collection_id": uuid.uuid4().hex, "observed_at": observed.isoformat(), "timezone": "Asia/Hong_Kong",
        "start": start.isoformat(), "end": end.isoformat(), "source": source, "fixtures": ordered,
        "translation_summary": translation_summary(ordered),
        "coverage": {"label": feeds.LABELS[source], "complete": not issues, "requested": len(windows),
                     "succeeded": succeeded, "issues": list(dict.fromkeys(issues))},
    }
    save("collection:" + result["collection_id"], result)
    return result


def history_fetch(key):
    source, team, season = key
    value, seen, issue = retrieve(f"team:v2:{source}:{team}:{season}",
                                  lambda: feeds.team_history(source, team, season), HISTORY_TTL)
    return key, value or [], seen, issue


def localize_collection(payload):
    cid = payload.get("collection_id")
    if not isinstance(cid, str) or len(cid) != 32:
        raise ValueError("请先采集时间范围内的赛程")
    key = "collection:" + cid
    with LOCKS[hash(key) % len(LOCKS)]:
        seen, collection = cached(key)
        if not collection:
            raise ValueError("此赛单在本机缓存中不存在，请重新采集")
        collection["fixtures"] = localize_rows(collection["fixtures"], timeout=0,
                                                retry=studio_engine.flag(payload, "retry"))
        collection["translation_summary"] = translation_summary(collection["fixtures"])
        save(key, collection, seen=seen)
    return collection


def prior_history(fixtures, source):
    data = {}
    current = datetime.now(feeds.UTC)
    def needed(row, side):
        return source, row[side + "_id"], row.get("season") or 0
    primary = {needed(row, side) for row in fixtures for side in ("home", "away")}
    def load(keys):
        for key, result, seen, issue in POOL.map(history_fetch, keys):
            data[key] = (result, seen, issue)
    load(sorted(primary))
    if source == "espn":
        previous = set()
        for row in fixtures:
            for side in ("home", "away"):
                key = needed(row, side)
                rows, _, issue = data[key]
                count = sum(1 for r in rows if r["competition_id"] == row["competition_id"] and
                            feeds.timestamp(r["kickoff"]) < current)
                if count < 3 and not issue:
                    previous.add((source, key[1], key[2] - 1))
        load(sorted(previous - primary))
    return data


def usable_history(row, cache, cutoff):
    by_id, notes = {}, []
    names = {row["home_id"]: row["home"], row["away_id"]: row["away"]}
    source, season = row["source"], row.get("season") or 0
    for side in ("home", "away"):
        team = row[side + "_id"]
        for year in (season, season - 1):
            rows, seen, issue = cache.get((source, team, year), ([], None, None))
            if issue:
                notes.append(f"{row[side]} 历史数据：{issue}")
            if not seen or feeds.timestamp(seen) > cutoff:
                continue
            for earlier in rows:
                if (not row["competition_id"] or earlier["competition_id"] != row["competition_id"]
                        or earlier["provider_id"] == row["provider_id"] or feeds.timestamp(earlier["kickoff"]) >= cutoff
                        or feeds.timestamp(earlier["kickoff"]) > feeds.timestamp(seen)):
                    continue
                if earlier["provider_id"] in by_id and by_id[earlier["provider_id"]]["observed_at"] >= seen:
                    continue
                record = {**earlier, "competition": row["competition"], "status": "FINISHED",
                          "score_period": "REGULATION", "observed_at": seen}
                if earlier.get("provenance"):
                    record["provenance"] = {**earlier["provenance"], "observed_at": seen}
                for position in ("home", "away"):
                    record[position] = names.get(record[position + "_id"], record[position])
                by_id[earlier["provider_id"]] = record
    history = sorted(by_id.values(), key=lambda r: (r["kickoff"], r["provider_id"]))
    return history, list(dict.fromkeys(notes))


def predict(payload):
    cid = payload.get("collection_id")
    if not isinstance(cid, str) or len(cid) != 32:
        raise ValueError("请先采集时间范围内的赛程")
    _, collection = cached("collection:" + cid)
    if not collection:
        raise ValueError("此赛单在本机缓存中不存在，请重新采集")
    available = {row["id"]: row for row in collection["fixtures"]}
    if studio_engine.flag(payload, "all"):
        selected = [row for row in available.values() if row["eligible"]]
    else:
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in available for i in ids):
            raise ValueError("请从本次采集的赛单选择有效比赛")
        selected = [available[i] for i in dict.fromkeys(ids)]
    use_history = studio_engine.flag(payload, "history") if "history" in payload else True
    use_odds = studio_engine.flag(payload, "odds")
    flags = {key: studio_engine.flag(payload, key) for key in ("matrix", "timeline", "knockout", "ledger")}
    source = collection["source"]
    start, end = feeds.timestamp(collection["start"]), feeds.timestamp(collection["end"])
    candidates, skipped, active = [], [], []
    def skip(row, reason):
        skipped.append({**{k: row.get(k) for k in ("id", "home", "away", "kickoff", "competition", "home_zh",
                                                  "away_zh", "competition_zh", "translation", "source", "competition_id",
                                                  "home_aliases", "away_aliases", "competition_aliases",
                                                  "source_url", "source_endpoint", "provenance")},
                        "reason": reason})
    for row in selected:
        reason = unavailable(row, datetime.now(feeds.UTC))
        if reason:
            skip(row, reason)
        else:
            candidates.append(row)
    refreshed, failures = {}, {}
    windows = sorted({r["source_window"] for r in candidates})
    for window, packet, seen, issue in POOL.map(refresh_window, ((source, w, "verify") for w in windows)):
        if packet is None:
            failures[window] = issue
        else:
            refreshed.update({r["id"]: {**r, "observed_at": seen} for r in packet["rows"]})
    for original in candidates:
        row = refreshed.get(original["id"])
        if not row:
            detail = failures.get(original["source_window"]) or "来源中已找不到该场，可能改期"
            skip(original, "无法重新核验赛程：" + detail)
            continue
        if any(original[k] != row[k] for k in ("home_id", "away_id", "competition_id")):
            skip(original, "对阵或赛事编号已更新，请重新采集")
            continue
        if not start <= feeds.timestamp(row["kickoff"]) < end:
            skip(original, "最新开球时间已超出选定范围")
            continue
        reason = unavailable(row, datetime.now(feeds.UTC))
        if reason:
            skip(row, reason)
        else:
            active.append(row)
    active = localize_rows(active)
    history_cache = prior_history(active, source) if use_history else {}
    matches = []
    for row in active:
        cutoff = datetime.now(feeds.UTC)
        reason = unavailable(row, cutoff)
        if reason:
            skip(row, reason)
            continue
        history, notes = usable_history(row, history_cache, cutoff)
        if use_history:
            notes.append("历史样本来自两队赛程中可取得的同赛事比分，覆盖范围以本次样本数为准。")
        match = {k: row[k] for k in ("home", "away", "competition", "kickoff", "status", "stage", "venue", "neutral",
                                    "home_zh", "away_zh", "competition_zh", "stage_zh", "translation",
                                    "source", "competition_id", "home_id", "away_id", "country",
                                    "home_aliases", "away_aliases", "competition_aliases", "stage_aliases",
                                    "source_url", "source_endpoint", "provenance") if row.get(k) is not None}
        match.update(as_of=cutoff.isoformat(), fixture_id=row["provider_id"], fixture_source=feeds.LABELS[source],
                     fixture_observed_at=row["observed_at"], market="1x2_90")
        odds_used = bool(use_odds and row.get("price"))
        if odds_used:
            match.update(odds=row["price"]["prices"], odds_at=row["observed_at"], odds_source=row["price"]["source"])
            notes.append("参考报价的时间取本次读取时间。")
        elif use_odds:
            notes.append("来源未提供完整的主平客三项报价。")
        samples = {side + "_count": sum(row[side + "_id"] in (h["home_id"], h["away_id"]) for h in history)
                   for side in ("home", "away")}
        if use_history and min(samples.values()) < 3:
            notes.append("至少一方可用的同赛事常规时间样本少于三场，模型较依赖基础先验。")
        try:
            out = studio_engine.run("forecast", {"input": match, "history": history, **flags})
        except (ValueError, TypeError, KeyError, sqlite3.Error) as exc:
            skip(row, str(exc))
            continue
        item = out["matches"][0]
        item["collection"] = {"id": row["id"], "history_count": len(history), **samples,
                              "history_source": feeds.LABELS[source] + " · 球队赛果" if use_history else "",
                              "odds_used": odds_used, "observed_at": row["observed_at"], "notes": notes,
                              **{k: match[k] for k in ("source_url", "source_endpoint", "provenance") if k in match}}
        matches.append(item)
    skipped = localize_rows(skipped)
    return {"kind": "forecast", "market": "1x2_90", "matches": matches, "skipped": skipped, "source": source,
            "coverage": collection["coverage"], "collection_id": cid, "observed_at": feeds.stamp()}
