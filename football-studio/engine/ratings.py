"""Historical Elo and recent form computed from dated regulation-time results."""
from collections import Counter, defaultdict
from itertools import groupby

from model import _records
from workflow import instant, utc_now


def _games(history, as_of, competition):
    if competition:
        history = [r for r in history if (r.get("competition") or r.get("league")) == competition]
    data, _ = _records(history, instant(as_of), competition, with_dates=True)
    return sorted(data, key=lambda row: (row[-1], row[0], row[1]))


def historical_elo(history, as_of, competition=None, *, k=20, advantage=60):
    if not competition and len({r.get("competition") or r.get("league") for r in history}) > 1:
        raise ValueError("Elo 历史跨多个赛事，请指定 --competition")
    games = _games(history, as_of, competition)
    if not games:
        raise ValueError("计算 Elo 需要截点前已取得的常规时间赛果")
    ratings, count = defaultdict(lambda: 1500.0), Counter()
    # Each UTC day's fixtures use pre-day ratings so an arbitrary tie order has no influence.
    for _, day in groupby(games, lambda row: row[-1].date()):
        changes = Counter()
        for home, away, hg, ag, neutral, _, _ in day:
            gap = ratings[home] - ratings[away] + (0 if neutral else advantage)
            expected = 1 / (1 + 10 ** (-max(-2400, min(2400, gap)) / 400))
            score = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
            delta = k * (score - expected)
            changes[home] += delta
            changes[away] -= delta
            count.update((home, away))
        for team, delta in changes.items():
            ratings[team] += delta
    return {"schema_version":1, "kind":"ratings", "source":"football-forecast-lab/historical-elo",
            "observed_at":utc_now(), "effective_as_of":instant(as_of).isoformat(),
            "competition":competition, "matches":len(games), "initial_rating":1500, "k":k,
            "home_advantage_points":advantage, "warnings":[],
            "records":[{"team":t,"elo":round(ratings[t],3),"games":count[t]}
                       for t in sorted(ratings, key=lambda t:(-ratings[t],t))]}


def recent_form(match, history, limit=5):
    games = _games(history, match["as_of"], match.get("competition") or match.get("league"))
    home, away = match["home"], match["away"]
    def compact(row):
        h, a, hg, ag, _, _, played = row
        return {"date":played.date().isoformat(), "home":h, "away":a, "score":[hg,ag]}
    views = {}
    for team in (home, away):
        subset = [r for r in reversed(games) if team in r[:2]][:limit]
        stats = Counter()
        for h,a,hg,ag,*_ in subset:
            gf,ga = (hg,ag) if team == h else (ag,hg)
            stats["W" if gf>ga else "D" if gf==ga else "L"] += 1
            stats["GF"] += gf
            stats["GA"] += ga
        views[team] = {"n":len(subset), **{k:stats[k] for k in ("W","D","L","GF","GA")},
                       "days_since_last_listed_game":((instant(match["kickoff"]).date()-subset[0][-1].date()).days if subset else None),
                       "games":[compact(r) for r in subset]}
    h2h = [compact(r) for r in reversed(games) if {r[0], r[1]} == {home, away}][:limit]
    return {"sample_limit":limit, "teams":views, "head_to_head":h2h}
