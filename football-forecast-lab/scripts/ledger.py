"""Local forecast ledger. Repeating the same freeze or result import is idempotent."""
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path
from result_rules import require_final_regulation, top_tie_credit
from workflow import identity, instant, utc_now


def packed(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fixture_key(record):
    return packed(identity(record))


def freeze(path, batch, history, *, captured_at=None):
    stamp = captured_at or utc_now()
    capture = instant(stamp)
    history_json = packed(history)
    history_id = hashlib.sha256(history_json.encode()).hexdigest()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=15)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS histories (digest TEXT PRIMARY KEY, input TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS forecasts (fixture TEXT NOT NULL, cutoff TEXT NOT NULL, frozen TEXT NOT NULL, prospective INTEGER NOT NULL, history_id TEXT NOT NULL, input TEXT NOT NULL, output TEXT NOT NULL, PRIMARY KEY(fixture, cutoff))")
        db.execute("CREATE TABLE IF NOT EXISTS results (fixture TEXT PRIMARY KEY, home_goals INTEGER NOT NULL, away_goals INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS reports (fixture TEXT NOT NULL, cutoff TEXT NOT NULL, digest TEXT NOT NULL, captured TEXT NOT NULL, report TEXT NOT NULL, PRIMARY KEY(fixture, cutoff, digest))")
        db.execute("INSERT OR IGNORE INTO histories VALUES (?, ?)", (history_id, history_json))
        for item in batch:
            m, report = item["input"], item["prediction"]
            key, cutoff = fixture_key(m), instant(m["as_of"]).isoformat()
            if instant(cutoff) > capture:
                raise ValueError("不能把未来截点登记为已经完成的预测")
            body = packed(m)
            output = packed({k:v for k,v in report.items() if k != "score_matrix"})
            full_report = packed(item)
            digest = hashlib.sha256(full_report.encode()).hexdigest()
            existing = db.execute("SELECT history_id,input,output FROM forecasts WHERE fixture=? AND cutoff=?", (key, cutoff)).fetchone()
            if existing:
                if existing != (history_id, body, output):
                    raise ValueError(f"{m['home']} 同一截点已有不同记录，请保留原版并选择新截点")
            else:
                is_live = int(capture < instant(m["kickoff"]))
                db.execute("INSERT INTO forecasts VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (key, cutoff, stamp, is_live, history_id, body, output))
            db.execute("INSERT OR IGNORE INTO reports VALUES (?, ?, ?, ?, ?)",
                       (key, cutoff, digest, stamp, full_report))


def archived(path, row, cutoff):
    if not Path(path).is_file():
        raise ValueError("尚无预测账本")
    key, stamp = fixture_key(row), instant(cutoff).isoformat()
    with closing(sqlite3.connect(path)) as db:
        frozen = db.execute("SELECT frozen,prospective,input,output,history_id FROM forecasts WHERE fixture=? AND cutoff=?",
                            (key, stamp)).fetchone()
        if not frozen:
            raise ValueError("账本中没有这个对阵和截点的预测")
        reports = []
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reports'").fetchone():
            rows = db.execute("SELECT captured,digest,report FROM reports WHERE fixture=? AND cutoff=? ORDER BY captured,digest",
                              (key, stamp))
            reports = [{"captured_at":ts,"sha256":digest,"report":json.loads(value)} for ts,digest,value in rows]
        history = db.execute("SELECT input FROM histories WHERE digest=?", (frozen[4],)).fetchone()
    return {"kind":"archive","frozen_at":frozen[0],"prospective":bool(frozen[1]),"input":json.loads(frozen[2]),
            "prediction":json.loads(frozen[3]),"history_sha256":frozen[4],"history":json.loads(history[0]),"reports":reports}


def settle(path, outcomes, *, now=None):
    if not Path(path).is_file():
        raise ValueError("尚无预测账本")
    current = instant(now or utc_now())
    changed = 0
    with closing(sqlite3.connect(path, timeout=15)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        for r in outcomes:
            require_final_regulation(r)
            key = fixture_key(r)
            kickoff = instant(r["kickoff"])
            if kickoff >= current:
                raise ValueError("不能结算尚未开赛的比赛")
            for field in ("completed_at", "observed_at", "available_at"):
                if r.get(field) is not None and not kickoff <= instant(r[field]) <= current:
                    raise ValueError(f"{field} 必须在开球与本次结算时间之间")
            goals = (r.get("home_goals"), r.get("away_goals"))
            if not all(type(x) is int and x >= 0 for x in goals):
                raise ValueError("结算需要常规时间主客队非负整数进球数")
            if not db.execute("SELECT 1 FROM forecasts WHERE fixture=?", (key,)).fetchone():
                raise ValueError(f"该场比赛没有冻结记录：{r['home']} / {r['away']}")
            old = db.execute("SELECT home_goals,away_goals FROM results WHERE fixture=?", (key,)).fetchone()
            if old and old != goals:
                raise ValueError("同一场比赛有冲突的结算比分，原始记录已保留")
            if not old:
                db.execute("INSERT INTO results VALUES (?, ?, ?)", (key, *goals))
                changed += 1
    return {"new_results": changed}


def review(path):
    if not Path(path).is_file():
        raise ValueError("尚无预测账本")
    buckets = {"prospective": [], "retrospective": []}
    seen = set()
    with closing(sqlite3.connect(path)) as db:
        rows = db.execute(
            "SELECT f.fixture,f.prospective,f.output,r.home_goals,r.away_goals "
            "FROM forecasts f JOIN results r ON r.fixture=f.fixture ORDER BY f.cutoff DESC")
        for key, live, output, hg, ag in rows:
            if (key, live) in seen:
                continue
            seen.add((key, live))
            report = json.loads(output)
            probs = report["probs"]
            actual = 0 if hg > ag else 1 if hg == ag else 2
            top = report["top_scores"][0]
            hit, tied = top_tie_credit(probs, actual)
            buckets["prospective" if live else "retrospective"].append(
                (hit,
                 -math.log(max(1e-15, probs[actual])),
                 sum((p - (i == actual))**2 for i, p in enumerate(probs)),
                 (top["home"], top["away"]) == (hg, ag), tied))
    summary = {}
    for group, values in buckets.items():
        names = ["accuracy", "log_loss", "brier_sum", "top_score_accuracy"]
        summary[group] = {"n": len(values), **{name: (sum(v[i] for v in values)/len(values) if values else None)
                                              for i, name in enumerate(names)}}
        summary[group]["top1_ties"] = sum(v[4] for v in values)
    return {"selection": "latest cutoff per fixture within each capture cohort", **summary}
