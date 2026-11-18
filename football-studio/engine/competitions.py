"""Cup simulations and day-batched historical evaluation. All timestamps are UTC internally."""

import bisect
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from itertools import accumulate, combinations, groupby
import math
import random

from model import predict_match
from result_rules import require_final_regulation, top_tie_credit


UTC = timezone.utc
HISTORY_MODEL_VERSION = "history-poisson-dc-v1"
HISTORY_CUTOFF = "utc-midnight-prior-days-and-available-results-v1"


def _time(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO timestamp with timezone")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be an ISO timestamp with timezone") from exc


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _name(value, label):
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise ValueError(f"Invalid {label}: expected a nonempty trimmed name")
    return value


def _score(record):
    return (_integer(record.get("home_goals"), "home_goals"),
            _integer(record.get("away_goals"), "away_goals"))


def _pair(record):
    home = _name(record.get("home"), "home")
    away = _name(record.get("away"), "away")
    if home == away:
        raise ValueError(f"A team cannot play itself: {home}")
    return home, away


def _result_candidates(value, label):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a list of objects")
    return [row for row in value if any(row.get(k) is not None for k in ("home_goals", "away_goals", "winner"))]


def _scored_records(value, label):
    scored = _result_candidates(value, label)
    for row in scored:
        require_final_regulation(row)
        _score(row)
    return scored


def _result_times(row):
    return [_time(row[k], k) for k in ("completed_at", "observed_at", "available_at", "result_available_at")
            if row.get(k) is not None]


def _check_cup_result(row, cutoff):
    stamps = _result_times(row)
    if row.get("kickoff") is not None:
        kickoff = _time(row["kickoff"], "kickoff")
        if cutoff is not None and kickoff >= cutoff:
            raise ValueError("Completed cup match has not kicked off by as_of")
        if any(stamp < kickoff for stamp in stamps):
            raise ValueError("Completed result predates kickoff")
    if cutoff is not None and any(stamp > cutoff for stamp in stamps):
        raise ValueError("Completed cup result was not available by as_of")


def _cup_format(spec):
    groups = spec.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("groups must map group names to lists of teams")
    membership = {}
    for group, members in groups.items():
        _name(group, "group name")
        if ":" in group or group == "third":
            raise ValueError("Group names cannot contain ':' or equal 'third'")
        if not isinstance(members, list) or len(members) < 2:
            raise ValueError("Each group must contain at least two teams")
        for team in members:
            _name(team, "team")
            if team in membership:
                raise ValueError(f"Team occurs more than once: {team}")
            membership[team] = group
    advance = _integer(spec.get("advance_per_group", 2), "advance_per_group", 1)
    if advance > min(map(len, groups.values())):
        raise ValueError("advance_per_group exceeds group size")
    wc48 = len(groups) == 12 and all(len(v) == 4 for v in groups.values()) and advance == 2
    thirds = _integer(spec.get("best_thirds", 8 if wc48 else 0), "best_thirds")
    if thirds and (advance != 2 or thirds > sum(len(v) >= 3 for v in groups.values())):
        raise ValueError("best_thirds requires two direct qualifiers and enough third-placed teams")
    if thirds and len(set(map(len, groups.values()))) != 1:
        raise ValueError("Cross-group third-place ranking requires equal-sized groups")
    slots = [f"{group}:{rank}" for group in groups for rank in range(1, advance + 1)]
    slots.extend(f"third:{n}" for n in range(1, thirds + 1))
    size = len(slots)
    if size < 2 or size & (size - 1):
        raise ValueError("Number of knockout qualifiers must be a power of two >= 2")
    return groups, membership, advance, thirds, slots


def _field(value, size, allowed, label, exact=False):
    if not isinstance(value, list) or len(value) != size // 2:
        raise ValueError(f"{label} must contain {size // 2} match pairs")
    flat = []
    for pair in value:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"Invalid {label} pair")
        flat.extend(_name(item, label) for item in pair)
    names = set(flat)
    if len(names) != size or not names.issubset(allowed) or (exact and names != allowed):
        raise ValueError(f"{label} contains missing, duplicate or unknown team/slot")
    return flat


def _knockout_locks(records, field):
    """A known participant in a later round also certifies its path through earlier rounds."""
    size = len(field)
    positions = {team: i for i, team in enumerate(field)}
    forced = {}
    seen = set()

    def force(stage, game, winner):
        key = (stage, game)
        if key in forced and forced[key] != winner:
            raise ValueError("Conflicting winners in knockout_results")
        forced[key] = winner

    for row in records:
        home, away = _pair(row)
        stage = _integer(row.get("round"), "knockout round", 2)
        if stage > size or stage & (stage - 1) or {home, away} - positions.keys():
            raise ValueError("Knockout result conflicts with bracket size or field")
        hi, ai = positions[home], positions[away]
        span = size // stage
        if hi // (span * 2) != ai // (span * 2) or hi // span == ai // span:
            raise ValueError(f"Round {stage}: {home} and {away} cannot meet in this bracket")
        game = hi // (span * 2)
        if (stage, game) in seen:
            raise ValueError(f"Duplicate knockout result in round {stage}")
        seen.add((stage, game))
        hg, ag = _score(row)
        winner = row.get("winner")
        if hg == ag:
            if winner not in (home, away):
                raise ValueError("A tied completed knockout result requires its actual winner")
        else:
            actual = home if hg > ag else away
            if winner is not None and winner != actual:
                raise ValueError("Recorded knockout winner conflicts with the score")
            winner = actual
        force(stage, game, winner)
        for team, position in ((home, hi), (away, ai)):
            earlier = stage * 2
            while earlier <= size:
                force(earlier, position // (2 * size // earlier), team)
                earlier *= 2
    return forced


def simulate_tournament(spec, *, sims=1000, seed=7):
    """Group round robin and single-elimination cup. First-round pairs define the fixed tree."""
    if not isinstance(spec, dict):
        raise ValueError("Tournament spec must be an object")
    _integer(sims, "sims", 1)
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    groups, membership, advance, thirds, slots = _cup_format(spec)
    size = len(slots)
    ratings = spec.get("ratings", {})
    if not isinstance(ratings, dict) or ratings.keys() - membership.keys():
        raise ValueError("ratings must map participating teams to Elo values")
    for rating in ratings.values():
        if isinstance(rating, bool) or not isinstance(rating, (int, float)) or not math.isfinite(rating):
            raise ValueError("Invalid Elo rating")
    neutral = spec.get("neutral", True)
    if type(neutral) is not bool:
        raise ValueError("neutral must be boolean")
    history = _scored_records(spec.get("history", []), "history")
    if history and not spec.get("as_of"):
        raise ValueError("as_of is required when supplying historical training data")
    # With no dated history a fixed technical anchor keeps identical inputs reproducible.
    cutoff = _time(spec.get("as_of", "2000-01-01T00:00:00Z"), "as_of")
    rng = random.Random(seed)
    baseline_date = cutoff.isoformat()
    simulation_date = (cutoff + timedelta(days=1)).isoformat()

    @lru_cache(maxsize=None)
    def distribution(home, away):
        match = dict(home=home, away=away, neutral=neutral, as_of=baseline_date,
                     kickoff=simulation_date)
        if home in ratings and away in ratings:
            match.update(home_elo=ratings[home], away_elo=ratings[away])
        prediction = predict_match(match, history=history)
        scores = []
        mass = []
        for i, row in enumerate(prediction["score_matrix"]):
            for j, probability in enumerate(row):
                if probability > 0:
                    scores.append((i, j))
                    mass.append(probability)
        return scores, list(accumulate(mass))

    def sample(home, away):
        scores, cumulative = distribution(home, away)
        return scores[bisect.bisect_left(cumulative, rng.random() * cumulative[-1])]

    results = {}
    for row in _scored_records(spec.get("group_results", []), "group_results"):
        _check_cup_result(row, cutoff if spec.get("as_of") else None)
        home, away = _pair(row)
        if home not in membership or away not in membership or membership[home] != membership[away]:
            raise ValueError("group_results contains teams outside the same group")
        key = frozenset((home, away))
        if key in results:
            raise ValueError(f"Duplicate group result for {home}, {away}")
        hg, ag = _score(row)
        results[key] = {home: hg, away: ag}

    known_field = spec.get("knockout_field")
    raw_bracket = spec.get("bracket")
    if known_field is not None and raw_bracket is not None:
        raise ValueError("Use one of bracket or knockout_field")
    fixed = None if known_field is None else _field(known_field, size, set(membership), "knockout_field")
    template = None if raw_bracket is None else _field(raw_bracket, size, set(slots), "bracket", exact=True)
    knockout = _scored_records(spec.get("knockout_results", []), "knockout_results")
    for row in knockout:
        _check_cup_result(row, cutoff if spec.get("as_of") else None)
    scheduled = [(group, tuple(combinations(members, 2))) for group, members in groups.items()]
    groups_complete = len(results) == sum(len(matches) for _, matches in scheduled)
    if knockout and fixed is None and not groups_complete:
        raise ValueError("Supply the actual knockout_field or all group results to locate completed knockout games")

    def ranked_field():
        standings = {t: [0, 0, 0] for t in membership}  # points, goal difference, goals scored
        seeds = {}
        third_teams = []

        def key(team):
            pts, gd, gf = standings[team]
            return -pts, -gd, -gf, team

        for group, games in scheduled:
            for home, away in games:
                lock = results.get(frozenset((home, away)))
                hg, ag = (lock[home], lock[away]) if lock else sample(home, away)
                home_pts, away_pts = (3, 0) if hg > ag else (0, 3) if ag > hg else (1, 1)
                for team, points, goals, against in ((home, home_pts, hg, ag), (away, away_pts, ag, hg)):
                    standings[team][0] += points
                    standings[team][1] += goals - against
                    standings[team][2] += goals
            ranking = sorted(groups[group], key=key)
            for n, team in enumerate(ranking[:advance], 1):
                seeds[f"{group}:{n}"] = team
            if thirds:
                third_teams.append(ranking[2])
        for n, team in enumerate(sorted(third_teams, key=key)[:thirds], 1):
            seeds[f"third:{n}"] = team
        if template is not None:
            return [seeds[slot] for slot in template]
        ranked = sorted(seeds.values(), key=key)
        # Standard seed ordering places the two highest-ranked teams in opposite halves.
        order = [0, 1]
        while len(order) < size:
            end = 2 * len(order) - 1
            order = [s for old in order for s in (old, end - old)]
        return [ranked[i] for i in order]

    if fixed is None and groups_complete:
        fixed = ranked_field()
    locks = _knockout_locks(knockout, fixed or []) if knockout else {}
    counts = {t: {f"reach_{2**r}": 0 for r in range(size.bit_length() - 1, 0, -1)} for t in membership}
    for row in counts.values():
        row["champion"] = 0
    sample_bracket = []
    for trial in range(sims):
        field = fixed or ranked_field()
        while len(field) > 1:
            stage = len(field)
            next_round = []
            for game, (home, away) in enumerate(zip(field[::2], field[1::2])):
                counts[home][f"reach_{stage}"] += 1
                counts[away][f"reach_{stage}"] += 1
                winner = locks.get((stage, game))
                if winner is None:
                    hg, ag = sample(home, away)
                    if hg == ag:
                        # Approximate extra time + penalties, deliberately separate from 90-minute W/D/L.
                        gap = ratings[home] - ratings[away] if home in ratings and away in ratings else 0
                        decider = 1 / (1 + 10 ** (-max(-2400, min(2400, gap)) / 600))
                        winner = home if rng.random() < decider else away
                    else:
                        winner = home if hg > ag else away
                if trial == 0:
                    sample_bracket.append({"round": stage, "home": home, "away": away, "advances": winner})
                next_round.append(winner)
            field = next_round
        counts[field[0]]["champion"] += 1
    draw_method = ("supplied actual knockout field" if known_field is not None else
                   "supplied rank-slot bracket" if template else "simplified performance seeding")
    return {"sims": sims, "seed": seed, "as_of": spec.get("as_of"),
            "qualified_teams": size, "draw_method": draw_method, "one_sample_bracket": sample_bracket,
            "group_results_locked": len(results), "knockout_results_locked": len(knockout),
            "teams": {t: {k: n / sims for k, n in c.items()} for t, c in counts.items()},
            "assumptions": ["Round-robin order: points, goal difference, goals scored, then team name.",
                            "A supplied knockout field supersedes group qualification; otherwise the configured bracket is used.",
                            "Samples use the single-match score matrix; tied new knockout games use an Elo-weighted decider (50/50 without both ratings).",
                            "All simulated pairings use one pre-tournament information cutoff; the internal modeling date is not an official fixture time."]}


def _metrics(samples):
    if not samples:
        return None
    brier = loss = correct = 0.0
    bins = [[0, 0.0, 0.0] for _ in range(10)]
    ties = 0
    for probs, actual in samples:
        brier += sum((p - int(i == actual)) ** 2 for i, p in enumerate(probs))
        loss -= math.log(max(probs[actual], 1e-15))
        top = max(probs)
        hit, tied = top_tie_credit(probs, actual)
        ties += int(tied)
        correct += hit
        bucket = bins[min(9, int(top * 10))]
        bucket[0] += 1
        bucket[1] += top
        bucket[2] += hit
    n = len(samples)
    return {"n": n, "brier": brier / n, "log_loss": loss / n,
            "top1_accuracy": correct / n, "top1_ties": ties,
            "top1_calibration": [{"lower": i / 10, "upper": (i + 1) / 10, "n": count,
                                  "mean_confidence": confidence / count, "accuracy": hits / count}
                                 for i, (count, confidence, hits) in enumerate(bins) if count]}


def _benchmark(row, cutoff, kickoff):
    odds = row.get("benchmark_odds")
    if odds is None:
        odds = row.get("odds")
    if odds is None:
        return None, "missing"
    if not isinstance(odds, (list, tuple)) or len(odds) != 3 or any(
        isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 1 for p in odds
    ):
        raise ValueError("historical odds must be three finite decimal prices greater than 1")
    values = [1.0 / p for p in odds]
    total = sum(values)
    probs = [v / total for v in values]
    observed = row.get("odds_observed_at")
    if not observed:
        closing = row.get("odds_horizon", row.get("odds_kind")) == "closing"
        return probs, "closing_unverified" if closing else "unknown_time"
    stamp = _time(observed, "odds_observed_at")
    if (kickoff and stamp >= kickoff) or stamp.date() > cutoff.date():
        return None, "in_play_or_later"
    if stamp <= cutoff:
        return probs, "available_by_cutoff"
    return probs, "before_kickoff_after_cutoff" if kickoff else "same_day_unverified"


def history_policy(min_train, window):
    _integer(min_train, "min_train", 1)
    if window is not None:
        _integer(window, "window", min_train)
    return {"model_version": HISTORY_MODEL_VERSION, "cutoff": HISTORY_CUTOFF,
            "min_train": min_train, "window": window}


def calibration_cutoff(match):
    """UTC day snapshot shared with historical evaluation, always at or before the caller's as_of."""
    stamp = _time(match.get("as_of"), "as_of")
    if stamp >= _time(match.get("kickoff"), "kickoff"):
        raise ValueError("as_of must precede kickoff")
    return datetime.combine(stamp.date(), time.min, UTC).isoformat()


def backtest_cutoff(day, kickoff):
    """The latest eligible UTC midnight strictly before kickoff, even for a midnight fixture."""
    midnight = datetime.combine(day, time.min, UTC)
    return midnight - timedelta(days=1) if kickoff == midnight else midnight


def _rolling_records(rows, cutoff=None):
    records = []
    keys = set()
    for row in _result_candidates(rows, "rows"):
        kickoff = _time(row["kickoff"], "kickoff") if row.get("kickoff") else None
        try:
            day = kickoff.date() if row.get("date") is None and kickoff else date.fromisoformat(row["date"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Every history row needs date YYYY-MM-DD") from exc
        if kickoff and kickoff.date() != day:
            raise ValueError("kickoff UTC date differs from date")
        if cutoff is not None and day >= cutoff.date():
            continue
        times = _result_times(row)
        earliest = kickoff or datetime.combine(day, time.min, UTC)
        if any(stamp < earliest for stamp in times):
            raise ValueError("Historical result availability predates its fixture")
        available = max(times) if times else datetime.combine(day + timedelta(days=1), time.min, UTC)
        if cutoff is not None and available > cutoff:
            continue
        require_final_regulation(row)
        _score(row)
        home, away = _pair(row)
        competition = row.get("competition") or row.get("league")
        if competition is not None:
            _name(competition, "competition")
        if "neutral" in row and type(row["neutral"]) is not bool:
            raise ValueError("neutral must be boolean")
        key = day, home, away, competition
        if key in keys:
            raise ValueError(f"Duplicate historical fixture: {day} {home} vs {away}")
        keys.add(key)
        records.append((day, home, away, kickoff, row, available))
    records.sort(key=lambda item: item[:3])
    return records


def _as_history(record):
    day, home, away, kickoff, row, available = record
    hg, ag = _score(row)
    past = dict(date=day.isoformat(), home=home, away=away, home_goals=hg, away_goals=ag,
                available_at=available.isoformat(), competition=row.get("competition") or row.get("league"),
                neutral=row.get("neutral", False))
    if kickoff is not None:
        past["kickoff"] = kickoff.isoformat()
    for field in ("completed_at", "observed_at"):
        if row.get(field) is not None:
            past[field] = row[field]
    return day, available, past


def _eligible_history(history, cutoff, window):
    by_competition = defaultdict(list)
    for day, available, past in history:
        if day < cutoff.date() and available <= cutoff:
            by_competition[past["competition"]].append(past)
    if window is not None:
        for league, past in by_competition.items():
            by_competition[league] = past[-window:]
    return by_competition


def history_at_cutoff(rows, competition, cutoff, settings):
    """Normalize the same result fields, tie ordering, availability and sample window as backtest_rows."""
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("history must be a list of records")
    scoped = [row for row in rows if (row.get("competition") or row.get("league")) == competition]
    prepared = map(_as_history, _rolling_records(scoped, cutoff))
    selected = _eligible_history(prepared, cutoff, settings["window"])[competition]
    if len(selected) < settings["min_train"]:
        raise ValueError(f"Calibration requires at least {settings['min_train']} eligible prior-day matches; got {len(selected)}")
    return selected


def backtest_rows(rows, *, min_train=20, window=None):
    """Walk forward by UTC date. Only prior-day results feed the single-match model."""
    settings = history_policy(min_train, window)
    records = _rolling_records(rows)
    history = []
    forecast_scores = []
    benchmark_groups = defaultdict(list)
    status_counts = defaultdict(int)
    forecasts = []
    for day, group in groupby(records, key=lambda item: item[0]):
        batch = list(group)
        midnight = datetime.combine(day, time.min, UTC)
        snapshots = {cutoff: _eligible_history(history, cutoff, window)
                     for cutoff in {backtest_cutoff(day, row[3]) for row in batch}}
        for _, home, away, kickoff, row, available in batch:
            cutoff = backtest_cutoff(day, kickoff)
            competition = row.get("competition") or row.get("league")
            previous = snapshots[cutoff][competition]
            if len(previous) < min_train:
                continue
            # For date-only data, this administrative order is never presented as an observed kickoff.
            match = {"home": home, "away": away, "as_of": cutoff.isoformat(),
                     "kickoff": (kickoff or (midnight + timedelta(hours=12))).isoformat(),
                     "neutral": row.get("neutral", False), "competition": competition}
            prediction = predict_match(match, history=previous)
            probs = prediction["probs"]
            hg, ag = _score(row)
            actual = 0 if hg > ag else 1 if hg == ag else 2
            forecast_scores.append((probs, actual))
            benchmark, status = _benchmark(row, cutoff, kickoff)
            status_counts[status] += 1
            if benchmark is not None:
                benchmark_groups[status].append(((probs, actual), (benchmark, actual)))
            forecasts.append({"date": day.isoformat(), "home": home, "away": away,
                              "competition": competition, "market": "1x2_90", "neutral": match["neutral"],
                              "kickoff": row.get("kickoff"), "as_of": cutoff.isoformat(),
                              "result_available_at": available.isoformat(),
                              "training_rows": len(previous), "probs": probs, "actual": ("H", "D", "A")[actual],
                              "benchmark_probs": benchmark, "benchmark_timing": status})
        history.extend(map(_as_history, batch))
    if not forecasts:
        raise ValueError("No evaluable fixtures after the prior-day training minimum")
    return {"n": len(forecasts), "min_train": min_train, "window": window, "history_policy": settings,
            "metrics": _metrics(forecast_scores), "odds_timing_counts": dict(status_counts),
            "paired_benchmarks": {status: {"model": _metrics([a for a, _ in pairs]),
                                           "market": _metrics([b for _, b in pairs])}
                                  for status, pairs in benchmark_groups.items()},
            "forecasts": forecasts,
            "protocol": "Entire UTC day held out. Historical market prices are benchmarks only; compare matched fixtures by quote timing. Brier sums squared errors over H/D/A (range 0–2). Calibration bins use top-1 confidence; tied top outcomes share accuracy credit."}
