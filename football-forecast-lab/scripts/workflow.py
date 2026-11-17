"""Link normalized snapshots by fixture and cutoff, then derive match markets."""
import copy
import math
from datetime import datetime, timezone


def instant(value):
    if not isinstance(value, str):
        raise ValueError("时间须为带时区的 ISO 8601 字符串")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"无效时间 {value!r}") from exc
    if result.utcoffset() is None:
        raise ValueError(f"时间缺少时区 {value!r}")
    return result.astimezone(timezone.utc)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def records(data):
    if isinstance(data, dict):
        data = data.get("records", data.get("matches", [data]))
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError("需要 JSON 对象数组或含 records 的快照")
    return data


def identity(row):
    sides = (row.get("home"), row.get("away"))
    if any(not isinstance(s, str) or not s.strip() for s in sides):
        raise ValueError("对阵需要有效的主客队名")
    home, away = (s.strip().casefold() for s in sides)
    if home == away:
        raise ValueError("主客球队名称相同，请核对球队或别名")
    return (home, away, instant(row["kickoff"]).isoformat())


def prepare(row, snapshots, *, bookmaker=None):
    match = copy.deepcopy(row)
    target = identity(match)
    cutoff = instant(match["as_of"])
    audit, quotes, external = [], [], []
    latest_ratings = {}
    for snap in snapshots:
        captured = instant(snap["observed_at"])
        kind = snap["kind"]
        if captured > cutoff:
            audit.append({"kind": kind, "status": "after_cutoff", "observed_at": snap["observed_at"]})
            continue
        matched = 0
        for r in records(snap):
            if kind == "ratings":
                name = str(r.get("team", "")).strip().casefold()
                for side, team in (("home", target[0]), ("away", target[1])):
                    if name == team and r.get("elo") is not None:
                        if side not in latest_ratings or captured > latest_ratings[side][0]:
                            latest_ratings[side] = (captured, r["elo"])
                        matched += 1
            elif kind == "odds" and identity(r) == target and r.get("market") == "1x2_90":
                if bookmaker and r.get("bookmaker") != bookmaker:
                    continue
                updated = instant(r.get("quote_observed_at") or snap["observed_at"])
                if updated <= cutoff and updated <= captured:
                    quotes.append((captured, updated, r, snap["observed_at"]))
                    matched += 1
            elif kind in ("external", "club-forecast"):
                exact = r.get("kickoff") and r.get("home") and r.get("away") and identity(r) == target
                date_match = (kind == "club-forecast" and match.get("accept_clubelo_date") is True
                              and str(r.get("home","")).casefold() == target[0]
                              and str(r.get("away","")).casefold() == target[1]
                              and r.get("date") == instant(match["kickoff"]).date().isoformat())
                if exact or date_match:
                    external.append({"source": snap.get("source", kind), "record": r,
                                     "observed_at": snap["observed_at"], "match_basis": "kickoff" if exact else "teams+UTC date"})
                    matched += 1
        audit.append({"kind": kind, "source": snap.get("source"), "observed_at": snap["observed_at"],
                      "matched": matched})
    supplied = {side: match.get(side + "_elo") for side in ("home","away")}
    if latest_ratings and all(supplied[s] is not None or s in latest_ratings for s in supplied):
        stamps = []
        for side, (stamp, rating) in latest_ratings.items():
            if supplied[side] is None:
                match[side + "_elo"] = rating
                stamps.append(stamp)
        if len(stamps) == 2:
            match["elo_at"] = max(stamps).isoformat()
    elif latest_ratings:
        audit.append({"kind":"ratings","status":"incomplete rating pair","observed_at":match["as_of"]})
    quote_history = []
    if quotes:
        names = sorted({str(q[2].get("bookmaker")) for q in quotes})
        if len(names) > 1 and not bookmaker:
            raise ValueError("多家公司赔率同时匹配，请用 --bookmaker 选择一个：" + ", ".join(names))
        # A later capture can contain a cached price older than one already collected.
        quotes.sort(key=lambda q: (q[1], q[0]))
        for _, _, record, stamp in quotes:
            quote_history.append({"observed_at": stamp, "captured_at": stamp,
                                  "quote_observed_at": record.get("quote_observed_at"),
                                  "bookmaker": record["bookmaker"], "odds": record["odds"]})
        if match.get("odds") is None:
            selected = quote_history[-1]
            match["odds"] = selected["odds"]
            match["odds_at"] = selected["quote_observed_at"] or selected["captured_at"]
            match["odds_captured_at"] = selected["captured_at"]
            match["odds_source"] = selected["bookmaker"]
    return match, {"snapshots": audit, "quote_history": quote_history, "upstream": external}


def scenario_match(match, scenario):
    allowed = {"name", "home_xg", "away_xg", "home_elo", "away_elo", "evidence", "roles",
               "odds", "market_weight", "role_weight", "rho", "neutral"}
    if not isinstance(scenario, dict) or not isinstance(scenario.get("name"), str) or not scenario["name"].strip():
        raise ValueError("每个情景需要 name")
    unknown = set(scenario) - allowed
    if unknown:
        raise ValueError("不支持的情景字段：" + ", ".join(sorted(unknown)))
    variant = copy.deepcopy(match)
    for key, value in scenario.items():
        if key == "evidence":
            variant[key] = [*variant.get(key, []), *value]
        elif key != "name":
            variant[key] = value
    return variant


def derived_markets(matrix, handicap=0, total=2.5):
    if not isinstance(handicap, int) or abs(handicap) > 10:
        raise ValueError("三项让球采用主队整数让球，绝对值不超过 10")
    if not math.isfinite(total) or not 0 <= total <= 20 or total * 2 != int(total * 2):
        raise ValueError("大小球界线须为 0 至 20 的整数或半球")
    totals = [0., 0., 0.]
    spread = [0., 0., 0.]
    btts = home_clean = away_clean = 0.
    for h, row in enumerate(matrix):
        for a, p in enumerate(row):
            totals[0 if h+a > total else 1 if h+a == total else 2] += p
            spread[0 if h+handicap > a else 1 if h+handicap == a else 2] += p
            if h and a:
                btts += p
            if a == 0:
                home_clean += p
            if h == 0:
                away_clean += p
    return {"total_line": total, "over_push_under": totals, "home_handicap": handicap,
            "handicap_home_draw_away": spread, "both_teams_score": btts,
            "home_clean_sheet": home_clean, "away_clean_sheet": away_clean}
