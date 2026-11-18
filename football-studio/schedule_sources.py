"""Read provider schedules and retain only verified fixture and regulation-score fields."""
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from sources import fetch_json
from web_links import safe_web_url

UTC = timezone.utc
HK = timezone(timedelta(hours=8))
LABELS = {"espn": "ESPN 全球足球赛程", "football-data": "Football-Data.org 帐号覆盖赛事"}
ESPN = "site.api.espn.com"
FOOTBALL_DATA = "api.football-data.org"
FD_LOCK = threading.Lock()
FD_NEXT_REQUEST = 0.


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("比赛时间需要时区")
    return parsed.astimezone(UTC)


def stamp():
    return datetime.now(UTC).isoformat(timespec="microseconds")


def schedule_windows(source, start, end):
    # ESPN's US display day may include early hours of the following UTC day.
    first = (start - timedelta(hours=5) if source == "espn" else start).date()
    last = (end - timedelta(microseconds=1)).date()
    step = 1 if source == "espn" else 8
    while first <= last:
        stop = min(first + timedelta(days=step), last + timedelta(days=1))
        yield first.isoformat() + "/" + stop.isoformat()
        first = stop


def fetch(host, path, params, headers=None):
    global FD_NEXT_REQUEST
    if host == FOOTBALL_DATA:
        # The free account allows ten calls per minute.
        with FD_LOCK:
            delay = FD_NEXT_REQUEST - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            FD_NEXT_REQUEST = time.monotonic() + 6.1
    return fetch_json(f"https://{host}{path}?{urlencode(params)}", allowed_host=host, headers=headers)


def provider_link(links, relation):
    if not isinstance(links, list):
        return None
    candidates = [entry for entry in links if isinstance(entry, dict)
                  and relation in (entry.get("rel") or []) and safe_web_url(entry.get("href"))]
    candidates.sort(key=lambda entry: "desktop" not in (entry.get("rel") or []))
    return candidates[0]["href"] if candidates else None


def trace_fixture(row, event, endpoint=None):
    source = row.get("source") or "espn"
    links = []
    if source == "espn":
        comp = event["competitions"][0]
        home, away = sides_from(comp)
        reference = [
            ("match", "比赛原文", provider_link(event.get("links"), "summary")),
            ("home_team", "主队赛程", provider_link((home.get("team") or {}).get("links"), "schedule")),
            ("away_team", "客队赛程", provider_link((away.get("team") or {}).get("links"), "schedule")),
            ("competition", "赛事页面", provider_link((event.get("league") or {}).get("links"), "index")),
        ]
        for kind, label, url in reference:
            if url:
                links.append({"kind": kind, "label": label, "url": url})
        web_url = next((link["url"] for link in links if link["kind"] == "match"), None)
    else:
        web_url = None
    endpoint = safe_web_url(endpoint)
    if endpoint:
        links.append({"kind": "api", "label": "原始赛程 API" + (" · 需源平台凭据" if source == "football-data" else ""),
                      "url": endpoint})
    original_names = {key: row.get(key) for key in ("home", "away", "competition", "stage") if row.get(key)}
    provenance = {
        "provider": source, "source_name": LABELS[source], "provider_id": row["provider_id"],
        "home_id": row["home_id"], "away_id": row["away_id"], "competition_id": row["competition_id"],
        "original_names": original_names, "web_url": web_url, "api_url": endpoint, "links": links,
    }
    row.update(source_url=web_url, source_endpoint=endpoint, provenance=provenance)
    return row


def fd_headers():
    token = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        raise ValueError("Football-Data.org 需要 FOOTBALL_DATA_TOKEN。可切换到免密钥的 ESPN 采集。")
    return {"X-Auth-Token": token}


def sides_from(comp):
    teams = {s.get("homeAway"): s for s in comp.get("competitors", []) if isinstance(s, dict)}
    return teams.get("home", {}), teams.get("away", {})


def espn_name(side):
    team = side.get("team") or {}
    return team.get("displayName") or team.get("name") or ""


def decimal_price(raw):
    try:
        if str(raw).upper() in ("EVEN", "EV"):
            return 2.
        number = float(raw)
        if not math.isfinite(number) or abs(number) < 100:
            return None
        return 1 + (number / 100 if number > 0 else 100 / abs(number))
    except (ValueError, TypeError):
        return None


def espn_price(comp):
    for quote in comp.get("odds") or []:
        if not isinstance(quote, dict):
            continue
        moneyline = quote.get("moneyline") or {}
        if not isinstance(moneyline, dict):
            continue
        raw = []
        for key in ("home", "draw", "away"):
            side = moneyline.get(key) or {}
            close = side.get("close") if isinstance(side, dict) else None
            legacy = "drawOdds" if key == "draw" else key + "TeamOdds"
            previous = quote.get(legacy)
            raw.append((close.get("odds") if isinstance(close, dict) else None)
                       or (previous.get("moneyLine") if isinstance(previous, dict) else None))
        prices = [decimal_price(value) for value in raw]
        if all(prices):
            provider = quote.get("provider")
            label = provider.get("name") if isinstance(provider, dict) else None
            return {"prices": prices, "source": "ESPN / " + str(label or "未标注公司")}
    return None


def espn_fixture(event, endpoint=None):
    comp = event["competitions"][0]
    status = (comp.get("status") or event.get("status") or {}).get("type") or {}
    code = str(status.get("name") or "UNKNOWN").removeprefix("STATUS_")
    if status.get("state") == "in":
        code = "LIVE"
    elif status.get("completed"):
        code = "FINISHED"
    home, away = sides_from(comp)
    uid = re.search(r"~l:(\d+)", str(event.get("uid")))
    league_id = uid.group(1) if uid else ""
    note = str(comp.get("altGameNote") or "")
    competition, _, stage = note.partition(",")
    kickoff = timestamp(comp.get("date") or event["date"])
    row = {"id": "espn:" + str(event["id"]), "provider_id": str(event["id"]),
            "home": espn_name(home), "away": espn_name(away),
            "home_id": str(home.get("id") or ""), "away_id": str(away.get("id") or ""),
            "kickoff": kickoff.isoformat(), "status": code, "time_confirmed": comp.get("timeValid") is True,
            "competition": competition.strip() or ("ESPN 赛事 " + league_id),
            "competition_id": league_id, "season": int((event.get("season") or {}).get("year") or kickoff.year),
            "stage": stage.strip(), "neutral": bool(comp.get("neutralSite")),
            "venue": (comp.get("venue") or event.get("venue") or {}).get("fullName"),
            "price": espn_price(comp), "source": "espn"}
    return trace_fixture(row, event, endpoint)


def fd_fixture(event, endpoint=None):
    league = event.get("competition") or {}
    home, away = event.get("homeTeam") or {}, event.get("awayTeam") or {}
    row = {"id": "football-data:" + str(event["id"]), "provider_id": str(event["id"]),
            "home": home.get("name") or "", "away": away.get("name") or "",
            "home_id": str(home.get("id") or ""), "away_id": str(away.get("id") or ""),
            "kickoff": timestamp(event["utcDate"]).isoformat(), "status": str(event.get("status") or "UNKNOWN"),
            "time_confirmed": event.get("status") != "SCHEDULED", "competition": league.get("name") or league.get("code"),
            "competition_id": str(league.get("id") or ""), "stage": event.get("stage"),
            "venue": event.get("venue"), "source": "football-data"}
    if endpoint is None and row["provider_id"].isdigit():
        endpoint = f"https://{FOOTBALL_DATA}/v4/matches/{row['provider_id']}"
    return trace_fixture(row, event, endpoint)


def schedule(source, window):
    first, stop = window.split("/")
    if source == "espn":
        params = {"dates": date.fromisoformat(first).strftime("%Y%m%d"), "limit": 1000}
        data = fetch(ESPN, "/apis/site/v2/sports/soccer/all/scoreboard",
                     params)
        endpoint = f"https://{ESPN}/apis/site/v2/sports/soccer/all/scoreboard?{urlencode(params)}"
        events, convert = data["events"], espn_fixture
    else:
        params = {"dateFrom": first, "dateTo": stop}
        data = fetch(FOOTBALL_DATA, "/v4/matches", params, fd_headers())
        endpoint = f"https://{FOOTBALL_DATA}/v4/matches?{urlencode(params)}"
        events, convert = data["matches"], fd_fixture
    if not isinstance(events, list):
        raise ValueError("上游未返回可识别的赛程列表")
    rows, issues = [], []
    if source == "espn" and len(events) >= 1000:
        issues.append(f"{first} 达到 ESPN 单日返回上限，可能另有赛事。")
    for event in events:
        try:
            row = convert(event, endpoint)
            # ESPN's NCAA women's scorecards omit per-match links. This public
            # league calendar was checked against the same event IDs.
            if source == "espn" and not row["source_url"] and row["competition_id"] == "5499":
                calendar = "https://www.espn.com/soccer/scoreboard/_/league/usa.ncaa.w.1/date/" + first.replace("-", "")
                row["provenance"]["links"].insert(0, {"kind": "schedule", "label": "当日来源赛程", "url": calendar})
            rows.append(row)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError):
            issues.append(f"{first} 有一项赛程缺少可验证的时间或标识。")
    return {"rows": rows, "issues": list(dict.fromkeys(issues))}


def final_goals(value):
    if isinstance(value, dict):
        value = value.get("value")
    number = float(value)
    if not number.is_integer() or not 0 <= number <= 50:
        raise ValueError("无有效常规时间比分")
    return int(number)


def espn_result(event, endpoint=None):
    comp = event["competitions"][0]
    state = comp.get("status") or {}
    phase = state.get("type") or {}
    if not phase.get("completed") or phase.get("name") not in ("STATUS_FULL_TIME", "STATUS_FINAL"):
        return None
    if state.get("period") not in (None, 2):
        return None
    home, away = sides_from(comp)
    row = {"provider_id": str(event["id"]), "competition_id": str((event.get("league") or {}).get("id") or ""),
            "kickoff": timestamp(event["date"]).isoformat(), "home": espn_name(home), "away": espn_name(away),
            "home_id": str(home["id"]), "away_id": str(away["id"]),
            "home_goals": final_goals(home.get("score")), "away_goals": final_goals(away.get("score")),
            "neutral": bool(comp.get("neutralSite")), "source": "espn",
            "competition": (event.get("league") or {}).get("name")}
    return trace_fixture(row, event, endpoint)


def fd_result(event, endpoint=None):
    if event.get("status") != "FINISHED":
        return None
    score = event.get("score") or {}
    pair = score.get("regularTime") or {}
    if None in (pair.get("home"), pair.get("away")) and score.get("duration") == "REGULAR":
        pair = score.get("fullTime") or {}
    row = fd_fixture(event, endpoint)
    keep = ("provider_id", "kickoff", "home", "away", "home_id", "away_id", "competition_id",
            "competition", "source", "source_url", "source_endpoint", "provenance")
    return {**{key: row[key] for key in keep}, "home_goals": final_goals(pair.get("home")),
            "away_goals": final_goals(pair.get("away"))}


def team_history(source, team_id, season):
    if not str(team_id).isdigit():
        raise ValueError("缺少已确认的球队编号")
    if source == "espn":
        path, params = f"/apis/site/v2/sports/soccer/all/teams/{team_id}/schedule", {"season": int(season)}
        data = fetch(ESPN, path, params)
        endpoint = f"https://{ESPN}{path}?{urlencode(params)}"
        events, convert = data["events"], espn_result
    else:
        path, params = f"/v4/teams/{team_id}/matches", {"status": "FINISHED", "limit": 50}
        data = fetch(FOOTBALL_DATA, path, params, fd_headers())
        endpoint = f"https://{FOOTBALL_DATA}{path}?{urlencode(params)}"
        events, convert = data["matches"], fd_result
    rows = []
    for event in events:
        try:
            row = convert(event, endpoint)
            if row and row["home"] and row["away"] and team_id in (row["home_id"], row["away_id"]):
                rows.append(row)
        except (KeyError, ValueError, TypeError, IndexError, AttributeError, OverflowError):
            continue
    return rows
