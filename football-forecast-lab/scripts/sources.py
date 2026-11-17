"""Read football data into timestamped JSON snapshots. Python 3.10+, stdlib only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


MAX_BYTES = 8 * 1024 * 1024
WEATHER_FIELDS = ("temperature_2m", "precipitation_probability", "wind_speed_10m")


def _check_origin(url: str, host: str, allow_http: bool) -> None:
    parts = urllib.parse.urlsplit(url)
    if (parts.hostname != host or parts.scheme not in (("https", "http") if allow_http else ("https",))
            or parts.username is not None or parts.password is not None
            or parts.port not in (None, 443 if parts.scheme == "https" else 80)):
        raise ValueError("Unexpected provider origin")


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        original = urllib.parse.urlsplit(req.full_url)
        _check_origin(newurl, original.hostname, original.scheme == "http")
        if urllib.parse.urlsplit(newurl).scheme != original.scheme or req.get_method() != "GET":
            raise ValueError("Provider changed protocol or redirected a POST")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(url: str, *, allowed_host: str, headers: dict | None = None,
                allow_http: bool = False, data: bytes | None = None) -> bytes:
    _check_origin(url, allowed_host, allow_http)
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": "football-forecast-lab/1.0", "Accept-Encoding": "identity", **(headers or {})})
    try:
        with urllib.request.build_opener(SameOriginRedirect()).open(request, timeout=20) as response:
            size = response.headers.get("Content-Length")
            if size and int(size) > MAX_BYTES:
                raise ValueError(f"{allowed_host}: response exceeds 8 MiB")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError(f"{allowed_host}: response exceeds 8 MiB")
            return body
    except urllib.error.HTTPError as exc:
        raise ValueError(f"{allowed_host}: HTTP {exc.code}; verify availability, credentials or quota") from None
    except (OSError, EOFError) as exc:
        raise ValueError(f"{allowed_host}: request failed ({type(exc).__name__})") from None


def fetch_json(url: str, *, allowed_host: str, headers: dict | None = None, payload=None):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    request_headers = dict(headers or {})
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    return json.loads(fetch_bytes(url, allowed_host=allowed_host, headers=request_headers, data=data))


def _secret(name: str) -> str:
    token = os.environ.get(name, "").strip()
    if not token:
        raise ValueError(f"Set the {name} environment variable for this source")
    return token


def _utc(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("Use a timestamp including UTC offset")
    return stamp.astimezone(timezone.utc)


def _number(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _identifier(value: str, pattern: str, label: str) -> str:
    if not re.fullmatch(pattern, value):
        raise ValueError(f"Invalid {label}")
    return value


def _records(payload, key=None):
    result = payload.get(key) if key is not None and isinstance(payload, dict) else payload
    if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
        raise ValueError("Provider returned an unexpected record layout")
    return result


def _csv_rows(body: bytes, required: tuple[str, ...]):
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp1252")
    rows = csv.DictReader(io.StringIO(text))
    if not set(required).issubset(rows.fieldnames or []):
        raise ValueError("Provider CSV lacks required columns: " + ", ".join(required))
    return rows


def _goal(value):
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,2}", str(value)):
        raise ValueError("Expected a nonnegative integer goal count")
    return int(value)


def _csv_date(value):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Unknown CSV match date")


def history_records(body: bytes, local_csv: bool, competition: str | None = None) -> tuple[list, list]:
    output, warnings = [], []
    ignored = 0
    if local_csv:
        rows = _csv_rows(body, ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"))
        if competition is not None and (not competition.strip() or "," in competition):
            raise ValueError("--competition needs one nonempty competition name or code")
        competition = competition.strip() if competition else None
        divisions = set()
        for row in rows:
            division = (row.get("Div") or "").strip()
            if division:
                divisions.add(division)
                if competition and len(divisions) > 1:
                    raise ValueError("CSV contains multiple Div values; split by Div or omit --competition")
            if not (row["Date"] and row["HomeTeam"] and row["AwayTeam"] and row["FTHG"] and row["FTAG"]):
                ignored += 1
                continue
            record = {"date": _csv_date(row["Date"]), "home": row["HomeTeam"].strip(),
                      "away": row["AwayTeam"].strip(), "home_goals": _goal(row["FTHG"]),
                      "away_goals": _goal(row["FTAG"])}
            if division:
                record["source_division"] = division
            if competition or division:
                record["competition"] = competition or division
            for prefix in ("AvgC", "PSC", "B365C"):
                prices = [_number(row.get(prefix + side)) for side in "HDA"]
                if all(p is not None and p > 1 for p in prices):
                    record.update(benchmark_odds=prices, odds_column=prefix, odds_horizon="closing")
                    break
            output.append(record)
        if len(divisions) > 1 and any("competition" not in r for r in output):
            raise ValueError("Mixed-league CSV has completed rows without Div; identify their division or split the file")
    else:
        for row in _records(json.loads(body), "matches"):
            score = row.get("score")
            if isinstance(score, dict):
                score = score.get("ft")
            if not isinstance(score, list) or len(score) != 2:
                ignored += 1
                continue
            record = {"date": date.fromisoformat(row["date"]).isoformat(),
                      "home": row["team1"], "away": row["team2"],
                      "home_goals": _goal(score[0]), "away_goals": _goal(score[1])}
            if competition:
                record["competition"] = competition
            output.append(record)
    if ignored:
        warnings.append(f"Skipped {ignored} rows without a completed result or required fields.")
    if any("benchmark_odds" in row for row in output):
        warnings.append("Closing prices lack precise quote timestamps. Use them only as closing benchmarks.")
    return sorted(output, key=lambda row: row["date"]), warnings


def fixtures_records(body: bytes) -> tuple[list, list]:
    output = []
    for row in _records(json.loads(body), "matches"):
        home, away = row["homeTeam"], row["awayTeam"]
        output.append({"fixture_id": str(row["id"]), "home": home.get("name"), "away": away.get("name"),
                       "home_id": home.get("id"), "away_id": away.get("id"), "kickoff": row["utcDate"],
                       "competition": row["competition"].get("code"), "status": row.get("status"),
                       "stage": row.get("stage"), "venue": row.get("venue"), "market": "1x2_90"})
    return output, []


def h2h_records(body: bytes) -> tuple[list, list]:
    output, skipped = [], 0
    for row in _records(json.loads(body), "matches"):
        score = row.get("score") or {}
        regular = score.get("regularTime") or {}
        if None in (regular.get("home"), regular.get("away")) and score.get("duration") == "REGULAR":
            regular = score.get("fullTime") or {}
        if row.get("status") != "FINISHED" or None in (regular.get("home"), regular.get("away")):
            skipped += 1
            continue
        output.append({"fixture_id": str(row["id"]), "date": _utc(row["utcDate"]).date().isoformat(),
                       "kickoff": row["utcDate"], "home": row["homeTeam"]["name"], "away": row["awayTeam"]["name"],
                       "home_goals": _goal(regular["home"]), "away_goals": _goal(regular["away"]),
                       "competition": (row.get("competition") or {}).get("code")})
    warnings = [f"Skipped {skipped} unfinished matches or results without a verified regulation score."] if skipped else []
    return sorted(output, key=lambda row: row["kickoff"]), warnings


def odds_records(body: bytes, bookmaker=None) -> tuple[list, list]:
    output, incomplete = [], 0
    for event in _records(json.loads(body)):
        for book in event.get("bookmakers", []):
            if bookmaker and book.get("key") != bookmaker:
                continue
            for market in book.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = {o["name"]: _number(o.get("price")) for o in market["outcomes"]}
                prices = [outcomes.get(k) for k in (event["home_team"], "Draw", event["away_team"])]
                if not all(v is not None and v > 1 for v in prices):
                    incomplete += 1
                    continue
                output.append({"fixture_id": str(event["id"]), "home": event["home_team"],
                               "away": event["away_team"], "kickoff": event["commence_time"],
                               "bookmaker": book["key"], "odds": prices, "market": "1x2_90",
                               "quote_observed_at": market.get("last_update") or book.get("last_update")})
    return output, [f"Skipped {incomplete} incomplete or two-way markets."] if incomplete else []


def squad_records(body: bytes) -> tuple[list, list]:
    data = json.loads(body)
    players = _records(data, "squad")
    return [{"team": data.get("name"), "team_id": data.get("id"), "player": p.get("name"),
             "player_id": p.get("id"), "position": p.get("position"), "date_of_birth": p.get("dateOfBirth"),
             "nationality": p.get("nationality"), "shirt_number": p.get("shirtNumber"),
             "team_last_updated": data.get("lastUpdated")} for p in players], [
        "Current club/team registration is not proof of inclusion in the matchday lineup."]


def injury_records(body: bytes) -> tuple[list, list]:
    data = json.loads(body)
    if data.get("errors"):
        raise ValueError("API-Football rejected the injury request; check plan, quota and fixture ID")
    output = []
    for report in _records(data, "response"):
        player, team, fixture = report["player"], report["team"], report["fixture"]
        output.append({"fixture_id": str(fixture["id"]), "kickoff": fixture.get("date"),
                       "team": team.get("name"), "team_id": team.get("id"), "player": player.get("name"),
                       "player_id": player.get("id"), "status": player.get("type"), "reason": player.get("reason")})
    return output, ["An empty feed does not confirm a healthy squad. Independently verify material absences."]


def ratings_records(body: bytes, team=None, requested_date=None) -> tuple[list, list]:
    output = []
    for row in _csv_rows(body, ("Club", "Elo")):
        if team and row["Club"].casefold() != team.casefold():
            continue
        if requested_date and not (row.get("From") and row.get("To") and row["From"] <= requested_date <= row["To"]):
            continue
        elo = _number(row["Elo"])
        if elo is None:
            continue
        output.append({"team": row["Club"], "elo": elo, "country": row.get("Country"),
                       "valid_from": row.get("From"), "valid_to": row.get("To")})
    return output, []


def club_records(body: bytes, team=None) -> tuple[list, list]:
    output, incomplete = [], 0
    bins = ["GD<-5"] + [f"GD={n}" for n in range(-5, 6)] + ["GD>5"]
    for row in _csv_rows(body, ("Home", "Away", "Date", *bins)):
        if team and team.casefold() not in {row["Home"].casefold(), row["Away"].casefold()}:
            continue
        values = [_number(row[k]) for k in bins]
        if any(v is None or not 0 <= v <= 1 for v in values) or abs(sum(values) - 1) > .02:
            incomplete += 1
            continue
        scores = []
        for key, val in row.items():
            score = re.fullmatch(r"R:(\d+)[:-](\d+)", key or "")
            p = _number(val)
            if score and p is not None and 0 < p <= 1:
                scores.append({"home": int(score[1]), "away": int(score[2]), "p": p})
        output.append({"date": row["Date"], "home": row["Home"], "away": row["Away"],
                       "market": "1x2_90", "upstream_probs": [sum(values[7:]), values[6], sum(values[:6])],
                       "top_scores": sorted(scores, key=lambda r: -r["p"])[:5]})
    return output, [f"Skipped {incomplete} incomplete upstream distributions."] if incomplete else []


class FixtureTable(HTMLParser):
    """Read ClubElo's public two-row fixture table; never evaluate page scripts."""
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.in_anchor = False
        self.capture = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row = {"name_parts": [], "numbers": []}
            self.in_anchor = False
            self.capture = None
        if self.row is None:
            return
        if tag == "a":
            self.in_anchor = True
        if attrs.get("data-live-status-game-id"):
            self.row["id"] = attrs["data-live-status-game-id"]
        if attrs.get("data-utc-time"):
            self.row["kickoff"] = attrs["data-utc-time"]
        if tag == "span":
            classes = attrs.get("class", "").split()
            if self.in_anchor and ("min641" in classes or "min1081" in classes):
                self.capture = "name_parts"
            elif not self.in_anchor and "min1081" in classes:
                self.capture = "numbers"

    def handle_data(self, data):
        if self.row is not None and self.capture:
            self.row[self.capture].append(data)

    def handle_endtag(self, tag):
        if tag == "span":
            self.capture = None
        elif tag == "a":
            self.in_anchor = False
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def club_html_records(body: bytes, team=None):
    parser = FixtureTable()
    parser.feed(body.decode("utf-8"))
    parser.close()
    output, found, skipped = [], 0, 0
    now = datetime.now(timezone.utc)
    for idx, row in enumerate(parser.rows):
        if "id" not in row or idx + 1 >= len(parser.rows):
            continue
        found += 1
        opp = parser.rows[idx + 1]
        home, away = "".join(row["name_parts"]).strip(), "".join(opp["name_parts"]).strip()
        if ("id" in opp or not home or not away or not row.get("kickoff")
                or len(row["numbers"]) < 2 or not opp["numbers"]):
            skipped += 1
            continue
        if team and team.casefold() not in {home.casefold(), away.casefold()}:
            continue
        percents = [_number(v.strip().rstrip("%")) for v in (*row["numbers"][:2], opp["numbers"][0])]
        if any(n is None or not 0 <= n <= 100 for n in percents) or abs(sum(percents) - 100) > .2:
            skipped += 1
            continue
        kickoff = _utc(row["kickoff"])
        if kickoff <= now:
            continue
        output.append({"fixture_id": row["id"], "date": kickoff.date().isoformat(), "kickoff": kickoff.isoformat(),
                       "home": home, "away": away, "market": "1x2_90",
                       "upstream_probs": [p / 100 for p in percents], "top_scores": []})
    if not found:
        raise ValueError("No recognizable ClubElo fixture table; use an archived fixture CSV with --csv")
    warnings = ["ClubElo displays rounded 1X2 probabilities; its HTML feed does not publish scorelines."]
    if skipped:
        warnings.append(f"Skipped {skipped} incomplete/unrecognized fixture rows.")
    return output, warnings


def rating_html_records(body: bytes, team=None, requested_date=None):
    page = body.decode("utf-8")
    anchor = re.search(r'<h1>\s*<a href="/(\d{4}-\d{2}-\d{2})/Ranking"', page)
    data = re.search(r"\bconst\s+eloData\s*=\s*(\[\[.*?\]\]);", page, re.S)
    if not anchor or not data:
        raise ValueError("No recognizable ClubElo ranking table for this date; use an archived CSV with --csv")
    rating_date = anchor[1]
    if requested_date and requested_date != rating_date:
        raise ValueError(f"ClubElo returned rating date {rating_date}, expected {requested_date}")
    pattern = r"""\[\s*'(<td\b[^\n]*?</td>)',\s*'(\d+(?:\.\d+)?)'"""
    output = []
    total = 0
    for cell, elo in re.findall(pattern, data[1]):
        links = re.findall(r"<a\b[^>]*>(.*?)</a>", cell, re.S)
        if not links:
            continue
        name = html.unescape(re.sub(r"<[^>]+>", "", links[-1])).replace("\\'", "'").strip()
        if name:
            total += 1
            if not team or name.casefold() == team.casefold():
                country = re.search(r'\balt="([A-Z]{2,4})"', cell)
                output.append({"team": name, "elo": float(elo), "country": country[1] if country else None,
                               "valid_from": rating_date, "valid_to": None})
    if not total:
        raise ValueError("ClubElo ranking rows have changed; no ratings decoded")
    return output, []


def weather_records(body: bytes, kickoff: datetime) -> tuple[list, list]:
    data = json.loads(body)
    hourly = data["hourly"]
    wanted = kickoff.strftime("%Y-%m-%dT%H:00")
    if wanted not in hourly["time"]:
        return [], ["Kickoff hour is outside the returned weather forecast horizon."]
    index = hourly["time"].index(wanted)
    fields = {name: hourly[name][index] for name in WEATHER_FIELDS}
    return [{"hour_utc": wanted + ":00Z", "latitude": data["latitude"], "longitude": data["longitude"],
             **fields, "units": {key: data["hourly_units"][key] for key in WEATHER_FIELDS}}], []


def news_records(body: bytes, limit: int) -> tuple[list, list]:
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Unexpected RSS declarations")
    channel = ET.fromstring(body).find("channel")
    if channel is None:
        raise ValueError("Provider returned an unexpected RSS feed")
    output = []
    for item in channel.findall("item")[:limit]:
        url = item.findtext("link", "")
        if urllib.parse.urlsplit(url).scheme not in ("https", "http"):
            continue
        output.append({"headline": item.findtext("title"), "publisher": item.findtext("source"),
                       "published_at": item.findtext("pubDate"), "url": url})
    return output, ["Headlines are unverified research leads; confirm any injury or lineup with the original publisher."]


def collect(args):
    kind = args.kind
    headers, private_query = {}, {}
    query = {}
    csv_file = getattr(args, "csv", None)
    if csv_file is not None:
        if csv_file.stat().st_size > MAX_BYTES:
            raise ValueError("Local CSV exceeds 8 MiB")
        body = csv_file.read_bytes()
        endpoint = csv_file.name
        source = f"user-supplied {kind} CSV"
    else:
        if kind == "history":
            if args.competition is not None:
                raise ValueError("--competition is for a local single-league CSV; select online history with --league")
            league = _identifier(args.league, r"[a-z]{2,4}\.\d+", "openfootball league slug (e.g. en.1)")
            season = _identifier(args.season, r"\d{4}-\d{2}", "season (e.g. 2024-25)")
            host, path, source = "raw.githubusercontent.com", f"/openfootball/football.json/master/{season}/{league}.json", "openfootball/football.json"
        elif kind == "fixtures":
            host, path, source = "api.football-data.org", "/v4/matches", "Football-Data.org"
            if (args.date_from is None) != (args.date_to is None):
                raise ValueError("Pass both --from and --to, or omit both")
            if args.date_from:
                start, end = date.fromisoformat(args.date_from), date.fromisoformat(args.date_to)
                if end < start:
                    raise ValueError("--to precedes --from")
                query.update(dateFrom=start.isoformat(), dateTo=end.isoformat())
            if args.competition:
                query["competitions"] = _identifier(args.competition, r"[A-Za-z0-9,]+", "competition")
            headers["X-Auth-Token"] = _secret("FOOTBALL_DATA_TOKEN")
        elif kind == "odds":
            sport = _identifier(args.sport, r"soccer_[a-z0-9_]+", "soccer sport key")
            host, path, source = "api.the-odds-api.com", f"/v4/sports/{sport}/odds/", "The Odds API"
            query.update(regions=_identifier(args.regions, r"[a-z0-9,]+", "regions"), markets="h2h", oddsFormat="decimal", dateFormat="iso")
            private_query["apiKey"] = _secret("THE_ODDS_API_KEY")
        elif kind == "h2h":
            fixture_id = _identifier(args.fixture_id, r"[0-9]+", "Football-Data.org fixture ID")
            host, path, source = "api.football-data.org", f"/v4/matches/{fixture_id}/head2head", "Football-Data.org"
            headers["X-Auth-Token"] = _secret("FOOTBALL_DATA_TOKEN")
        elif kind == "squad":
            team_id = _identifier(args.team_id, r"[0-9]+", "Football-Data.org team ID")
            host, path, source = "api.football-data.org", f"/v4/teams/{team_id}", "Football-Data.org"
            headers["X-Auth-Token"] = _secret("FOOTBALL_DATA_TOKEN")
        elif kind == "injuries":
            query["fixture"] = _identifier(args.fixture_id, r"[0-9]+", "API-Football fixture ID")
            host, path, source = "v3.football.api-sports.io", "/injuries", "API-Football"
            headers["x-apisports-key"] = _secret("API_FOOTBALL_KEY")
        elif kind in ("ratings", "club-forecast"):
            host, source = "clubelo.com", "ClubElo"
            if kind == "club-forecast":
                path = "/Fixtures"
            else:
                prefix = ("/" + date.fromisoformat(args.date).isoformat()) if args.date else ""
                path = prefix + "/Ranking"
        elif kind == "weather":
            kickoff = _utc(args.kickoff)
            if not (-90 <= args.lat <= 90 and -180 <= args.lon <= 180):
                raise ValueError("Invalid latitude or longitude")
            host, path, source = "api.open-meteo.com", "/v1/forecast", "Open-Meteo"
            query.update(latitude=args.lat, longitude=args.lon, hourly=",".join(WEATHER_FIELDS),
                         timezone="GMT", start_date=kickoff.date().isoformat(), end_date=kickoff.date().isoformat())
        elif kind == "news":
            host, path, source = "news.google.com", "/rss/search", "Google News RSS"
            if not args.query.strip() or not 1 <= args.limit <= 100:
                raise ValueError("Supply a nonempty search and --limit between 1 and 100")
            query.update(q=args.query, hl="en-US", gl="US", ceid="US:en")
        else:
            raise ValueError("Unsupported source")
        base = f"https://{host}{path}"
        endpoint = base + ("?" + urllib.parse.urlencode(query) if query else "")
        url = base + ("?" + urllib.parse.urlencode({**query, **private_query}) if query or private_query else "")
        body = fetch_bytes(url, allowed_host=host, headers=headers)

    if kind == "history":
        competition = args.competition if csv_file is not None else {"en.1": "PL"}.get(league, league)
        records, warnings = history_records(body, csv_file is not None, competition)
    elif kind == "fixtures":
        records, warnings = fixtures_records(body)
    elif kind == "h2h":
        records, warnings = h2h_records(body)
    elif kind == "odds":
        records, warnings = odds_records(body, args.bookmaker)
    elif kind == "squad":
        records, warnings = squad_records(body)
    elif kind == "injuries":
        records, warnings = injury_records(body)
    elif kind == "ratings":
        required_date = date.fromisoformat(args.date).isoformat() if args.date else None
        records, warnings = ratings_records(body, args.team, required_date) if csv_file else rating_html_records(body, args.team, required_date)
    elif kind == "club-forecast":
        records, warnings = club_records(body, args.team) if csv_file else club_html_records(body, args.team)
    elif kind == "weather":
        records, warnings = weather_records(body, kickoff)
    else:
        records, warnings = news_records(body, args.limit)
    if not records:
        warnings.append("No matching data returned; do not substitute zeros or invented observations.")
    return {"schema_version": 1, "kind": kind, "source": source, "endpoint": endpoint,
            "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "raw_sha256": hashlib.sha256(body).hexdigest(), "records": records, "warnings": warnings}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="kind", required=True)
    def command(name, help_text):
        sub = commands.add_parser(name, help=help_text, description=help_text)
        sub.add_argument("--out", type=Path, help="Save JSON snapshot (default: stdout)")
        return sub
    fixtures = command("fixtures", "Football-Data.org v4 fixtures; requires FOOTBALL_DATA_TOKEN")
    fixtures.add_argument("--competition", help="Competition codes, e.g. PL or PL,PD")
    fixtures.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    fixtures.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    h2h = command("h2h", "Completed regulation head-to-head results; requires FOOTBALL_DATA_TOKEN")
    h2h.add_argument("--fixture-id", required=True, help="Football-Data.org match ID from fixtures")
    odds = command("odds", "Three-way soccer prices by bookmaker; requires THE_ODDS_API_KEY")
    odds.add_argument("--sport", default="soccer_epl")
    odds.add_argument("--regions", default="eu")
    odds.add_argument("--bookmaker", help="Optional exact provider bookmaker key")
    squad = command("squad", "Team roster and player identities; requires FOOTBALL_DATA_TOKEN")
    squad.add_argument("--team-id", required=True, help="Football-Data.org team ID (e.g. from fixtures)")
    injuries = command("injuries", "Reported absences; requires API_FOOTBALL_KEY and provider coverage")
    injuries.add_argument("--fixture-id", required=True, help="API-Football fixture ID, distinct from other provider IDs")
    for name in ("ratings", "club-forecast"):
        sub = command(name, "ClubElo club ratings" if name == "ratings" else "ClubElo fixtures and upstream 90-minute forecasts")
        sub.add_argument("--team", help="Optional exact ClubElo team name (case-insensitive)")
        sub.add_argument("--csv", type=Path, help="Read an archived ClubElo CSV instead of the current public HTTPS table")
        if name == "ratings":
            sub.add_argument("--date", help="Require the provider to confirm this ranking date (default: latest published ranking)")
    weather = command("weather", "Open-Meteo weather for the stadium coordinates and UTC kickoff hour")
    weather.add_argument("--lat", type=float, required=True)
    weather.add_argument("--lon", type=float, required=True)
    weather.add_argument("--kickoff", required=True, help="ISO-8601 timestamp with offset")
    news = command("news", "Google News RSS search for headlines to verify independently")
    news.add_argument("--query", required=True)
    news.add_argument("--limit", type=int, default=15)
    history = command("history", "League results from the public-domain openfootball data, or a local CSV")
    history.add_argument("--season", default="2024-25", help="openfootball season, e.g. 2024-25")
    history.add_argument("--league", default="en.1", help="openfootball league, e.g. en.1, de.1, es.1")
    history.add_argument("--csv", type=Path, help="Use a local Date,HomeTeam,AwayTeam,FTHG,FTAG CSV instead of fetching")
    history.add_argument("--competition", help="Competition name/code for a single-league CSV; otherwise preserve each Div")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = collect(args)
        encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.out is None:
            print(encoded, end="")
        else:
            if getattr(args, "csv", None) and args.csv.resolve() == args.out.resolve():
                raise ValueError("Snapshot destination must differ from input CSV")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=args.out.parent, delete=False) as f:
                tmp = Path(f.name)
            try:
                tmp.write_bytes(encoded.encode("utf-8"))
                os.replace(tmp, args.out)
            finally:
                tmp.unlink(missing_ok=True)
    except (ValueError, OSError, TypeError, AttributeError, KeyError, IndexError, csv.Error, ET.ParseError) as exc:
        print(f"Source error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
