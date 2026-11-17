"""Original, offline regulation-time football forecasting model (Python standard library)."""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from result_rules import require_final_regulation

OUTCOMES = ("home", "draw", "away")
ROLE_WEIGHTS = {"market": 0.35, "data": 0.25, "tactics": 0.18, "news": 0.12, "synthesis": 0.10}


def _number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be finite and between {low} and {high}")
    return float(value)


def _name(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def _utc(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} requires an ISO timestamp with timezone")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} requires an ISO timestamp with timezone") from exc
    if stamp.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return stamp.astimezone(timezone.utc)


def _before(value, label, cutoff):
    if _utc(value, label) > cutoff:
        raise ValueError(f"{label} is later than as_of")


def _rows(value, label):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _normalize(values):
    total = sum(values)
    return [value / total for value in values]


def _bound(value, low, high):
    return min(high, max(low, value))


def _dates(row):
    start = row.get("kickoff") or row.get("date")
    if isinstance(start, str) and len(start) == 10:
        try:
            played = datetime.combine(date.fromisoformat(start), time.min, tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("invalid history date") from exc
    else:
        played = _utc(start, "history kickoff/date")
    # Without an availability timestamp, completed scores become usable the next UTC day.
    available = played.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    reported_times = [_utc(row[k], f"history {k}") for k in ("completed_at", "observed_at", "available_at", "result_available_at")
                      if row.get(k) is not None]
    if reported_times:
        if min(reported_times) < played:
            raise ValueError("history result availability precedes kickoff/date")
        available = max(reported_times)
    return played, available


def _goals(row, key):
    value = row.get(key)
    if type(value) is not int or not 0 <= value <= 50:
        raise ValueError(f"history {key} must be an integer between 0 and 50 (regulation only)")
    return value


def _records(history, cutoff, competition, *, with_dates=False):
    result = []
    ignored = 0
    seen = {}
    for row in _rows(history, "history"):
        row_competition = row.get("competition") or row.get("league")
        if competition and row_competition and competition != row_competition:
            ignored += 1
            continue
        played, available = _dates(row)
        if played >= cutoff or available > cutoff:
            ignored += 1
            continue
        if row.get("home_goals") is None and row.get("away_goals") is None:
            ignored += 1
            continue
        require_final_regulation(row)
        home = _name(row.get("home"), "history home")
        away = _name(row.get("away"), "history away")
        if home == away:
            raise ValueError("history teams must differ")
        hg, ag = _goals(row, "home_goals"), _goals(row, "away_goals")
        neutral = row.get("neutral", False)
        if type(neutral) is not bool:
            raise ValueError("history neutral must be a boolean")
        key = (played, home, away)
        version = (hg, ag, neutral)
        if key in seen:
            if seen[key] != version:
                raise ValueError("conflicting historical scores or venues for the same fixture")
            ignored += 1
            continue
        seen[key] = version
        age_days = (cutoff - played).total_seconds() / 86400
        item = (home, away, hg, ag, neutral, 2 ** (-age_days / 180))
        result.append(item + (played,) if with_dates else item)
    return result, ignored


def _strength(match, records):
    # Weighted league means with 20 matches of venue-specific prior information.
    sum_home, sum_away, games = 20 * 1.45, 20 * 1.15, 20.0
    for _, _, hg, ag, neutral, w in records:
        if not neutral:
            sum_home += w * hg
            sum_away += w * ag
            games += w
    home_rate, away_rate = sum_home / games, sum_away / games
    neutral_rate = (home_rate + away_rate) / 2
    home, away = match["home"], match["away"]
    # Attack/defence are venue-adjusted ratios against the respective league means.
    stats = {team: [6.0, 6.0, 6.0, 0] for team in (home, away)}
    for h, a, hg, ag, neutral, w in records:
        hr, ar = (neutral_rate, neutral_rate) if neutral else (home_rate, away_rate)
        for team, scored, conceded, avg_for, avg_against in ((h, hg, ag, hr, ar), (a, ag, hg, ar, hr)):
            if team in stats:
                v = stats[team]
                v[0] += w * scored / avg_for
                v[1] += w * conceded / avg_against
                v[2] += w
                v[3] += 1
    neutral = match.get("neutral", False)
    if type(neutral) is not bool:
        raise ValueError("neutral must be a boolean")
    hr, ar = (neutral_rate, neutral_rate) if neutral else (home_rate, away_rate)
    h, a = stats[home], stats[away]
    rates = [hr * (h[0]/h[2]) * (a[1]/a[2]), ar * (a[0]/a[2]) * (h[1]/h[2])]
    known = [match.get(k) is not None for k in ("home_elo", "away_elo")]
    if any(known):
        if not all(known):
            raise ValueError("supply both home_elo and away_elo")
        home_elo = _number(match["home_elo"], "home_elo", 0, 5000)
        away_elo = _number(match["away_elo"], "away_elo", 0, 5000)
        # Dampen the Elo prior as histories for both teams accumulate.
        confidence_weight = 6 / min(h[2], a[2])
        tilt = math.exp(confidence_weight * _bound(home_elo - away_elo, -600, 600) / 850)
        rates = [rates[0] * tilt, rates[1] / tilt]
    sources = ["history/league prior" + (" + Elo" if all(known) else "")] * 2
    for side, key in enumerate(("home_xg", "away_xg")):
        if match.get(key) is not None:
            rates[side] = _number(match[key], key, 0.05, 8)
            sources[side] = "provided match xG"
    return [_bound(x, 0.05, 8) for x in rates], {
        "home_matches": h[3], "away_matches": a[3], "rate_sources": sources,
        "league_means": [home_rate, away_rate], "half_life_days": 180, "team_prior_games": 6,
    }


def _latest(rows, label, cutoff, key):
    # If the same source updates its statement, keep only the most recent version.
    unique = {}
    for item in _rows(rows, label):
        source = _name(item.get("source"), f"{label} source")
        stamp = _utc(item.get("observed_at"), f"{label} observed_at")
        if stamp > cutoff:
            raise ValueError(f"{label} observed_at is later than as_of")
        identity = key(item, source)
        old = unique.get(identity)
        if old is not None and old[0] == stamp and old[1] != item:
            raise ValueError(f"conflicting {label} at the same timestamp")
        if old is None or old[0] < stamp:
            unique[identity] = (stamp, item)
    return [value[1] for value in unique.values()]


def _evidence(match, cutoff):
    sides = (match["home"], match["away"])
    adjustments = [0.0, 0.0]
    applied = []
    def key(item, source):
        return (_name(item.get("team"), "evidence team"), _name(item.get("kind"), "evidence kind"),
                item.get("event_id") and _name(item["event_id"], "evidence event_id") or source)
    for item in _latest(match.get("evidence", []), "evidence", cutoff, key):
        if item["team"].strip() not in sides:
            raise ValueError("evidence team must be a participant")
        delta = _number(item.get("delta_xg"), "evidence delta_xg", -8, 8)
        confidence = _number(item.get("confidence"), "evidence confidence", 0, 1)
        adjustment = _bound(delta, -0.35, 0.35) * confidence
        side = sides.index(item["team"].strip())
        adjustments[side] += adjustment
        applied.append({k: item[k] for k in ("team", "kind", "source", "observed_at")} | {
            "confidence": confidence, "requested_delta_xg": delta, "bounded_delta_xg": adjustment})
    return [_bound(x, -0.65, 0.65) for x in adjustments], applied


def _poisson(mean):
    values = [math.exp(-mean)]
    for k in range(1, 40):
        values.append(values[-1] * mean / k)
        if k >= 8 and 1 - sum(values) < 1e-10:
            break
    return values


def _matrix(means, rho):
    lh, la = means
    # Keep all four low-score correction factors strictly positive.
    rho = _bound(rho, max(-0.99/lh, -0.99/la), min(0.99, 0.99/(lh * la)))
    factors = {(0, 0): 1 - lh * la * rho, (1, 0): 1 + la * rho,
               (0, 1): 1 + lh * rho, (1, 1): 1 - rho}
    home, away = _poisson(lh), _poisson(la)
    rows = [[ph * pa * factors.get((i, j), 1.0) for j, pa in enumerate(away)]
            for i, ph in enumerate(home)]
    total = sum(map(sum, rows))
    return [[x / total for x in row] for row in rows], rho


def _outcome(i, j):
    return 0 if i > j else (1 if i == j else 2)


def _probabilities(matrix):
    values = [0.0] * 3
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            values[_outcome(i, j)] += p
    return _normalize(values)


def _triplet(values, label, low, high):
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"{label} must have three values in home, draw, away order")
    return [_number(v, label, low, high) for v in values]


def _prices(match, key, cutoff, warnings):
    if match.get(key) is None:
        return None
    vals = _triplet(match[key], key, 1.000001, 1000000)
    when = match.get(key + "_at")
    if when:
        _before(when, key + "_at", cutoff)
    else:
        warnings.append(f"{key}: quote time missing; point-in-time availability is unverified.")
    return vals


def _role_view(rows, cutoff):
    views = []
    def key(item, source):
        if item.get("market") != "1x2_90":
            raise ValueError("role market must be 1x2_90; advancement and regulation must remain separate")
        return _name(item.get("role"), "role name")
    for item in _latest(rows, "roles", cutoff, key):
        values = _triplet(item.get("probs"), "role probs", 0, 1)
        if not math.isclose(sum(values), 1, abs_tol=0.015):
            raise ValueError("role probabilities must sum to 1 (rounding tolerance 0.015)")
        role = item["role"].strip()
        weight = _number(item.get("weight", ROLE_WEIGHTS.get(role, 0.10)), "role weight", 0, 1)
        views.append({"role": role, "source": item["source"], "observed_at": item["observed_at"],
                      "weight": weight, "probs": _normalize(values)})
    if not views:
        return None, []
    if not any(item["weight"] for item in views):
        raise ValueError("at least one supplied role must have a positive weight")
    return _normalize([sum(r["weight"] * r["probs"][i] for r in views) for i in range(3)]), views


def _mix(left, right, weight):
    return [(1 - weight) * a + weight * b for a, b in zip(left, right)]


def predict_match(match: dict, history: list[dict] | None = None, *, history_as_of=None) -> dict:
    """Forecast 90 minutes. Inputs and outputs use home/draw/away order, UTC cutoffs."""
    if not isinstance(match, dict):
        raise ValueError("match must be an object")
    home, away = _name(match.get("home"), "home"), _name(match.get("away"), "away")
    if home == away:
        raise ValueError("home and away must differ")
    match = dict(match, home=home, away=away)
    if match.get("market", "1x2_90") != "1x2_90":
        raise ValueError("predict_match accepts only regulation time (1x2_90)")
    cutoff = _utc(match.get("as_of"), "as_of")
    if cutoff >= _utc(match.get("kickoff"), "kickoff"):
        raise ValueError("as_of must be strictly before kickoff")
    for field in ("features_at", "elo_at", "xg_at"):
        if match.get(field) is not None:
            _before(match[field], field, cutoff)
    warnings = []
    history_cutoff = _utc(history_as_of, "history_as_of") if history_as_of is not None else cutoff
    if history_cutoff > cutoff:
        raise ValueError("history_as_of cannot be later than the forecast cutoff")
    eligible, ignored = _records([] if history is None else history, history_cutoff,
                                 match.get("competition") or match.get("league"))
    raw_means, strength = _strength(match, eligible)
    if not min(strength["home_matches"], strength["away_matches"]) and not all(
            match.get(k) is not None for k in ("home_xg", "away_xg")):
        warnings.append("At least one team has no eligible history; estimates depend on priors or supplied ratings.")
    if (any(match.get(k) is not None for k in ("home_xg", "away_xg")) and
            not (match.get("features_at") or match.get("xg_at"))):
        warnings.append("Input xG has no observation timestamp; cutoff cannot be verified.")
    if match.get("home_elo") is not None and not (match.get("features_at") or match.get("elo_at")):
        warnings.append("Input Elo has no observation timestamp; cutoff cannot be verified.")
    deltas, evidence = _evidence(match, cutoff)
    means = [_bound(v + delta, 0.05, 8) for v, delta in zip(raw_means, deltas)]
    rho = _number(match.get("rho", -0.06), "rho", -0.2, 0.2)
    matrix, rho_used = _matrix(means, rho)
    base_probs = _probabilities(matrix)
    raw_probs = _probabilities(_matrix(raw_means, rho)[0]) if evidence else list(base_probs)
    odds = _prices(match, "odds", cutoff, warnings)
    target = _prices(match, "target_odds", cutoff, warnings)
    market_probs = _normalize([1/x for x in odds]) if odds else None
    market_weight = _number(match.get("market_weight", 0.35), "market_weight", 0, 1)
    role_weight = _number(match.get("role_weight", 0.20), "role_weight", 0, 1)
    if market_probs:
        fused = _mix(base_probs, market_probs, market_weight)
    else:
        fused = list(base_probs)
    role_probs, roles = _role_view(match.get("roles", []), cutoff)
    probs = _normalize(_mix(fused, role_probs, role_weight)) if role_probs else fused
    uncalibrated = list(probs)
    temperature = _number(match.get("temperature", 1.0), "temperature", 0.25, 4.0)
    if temperature != 1.0:
        probs = _normalize([p ** (1 / temperature) for p in probs])
    if market_probs and any(r["role"] == "market" for r in roles):
        warnings.append("Both reference odds and a market role are present; their information may overlap.")
    # Scale each outcome region to its final probability, preserving within-region score ratios.
    ratios = [v / baseline for v, baseline in zip(probs, base_probs)]
    matrix = [[v * ratios[_outcome(i, j)] for j, v in enumerate(row)] for i, row in enumerate(matrix)]
    cells = [(p, i, j) for i, row in enumerate(matrix) for j, p in enumerate(row)]
    best = sorted(cells, key=lambda cell: -cell[0])[:5]
    expected = [sum(p * i for p, i, j in cells), sum(p * j for p, i, j in cells)]
    comparison = None
    if target:
        target_probs = _normalize([1/x for x in target])
        shared = bool(odds and market_weight and
                      (target == odds or (match.get("odds_source") and
                       match.get("odds_source") == match.get("target_odds_source"))))
        if shared:
            warnings.append("Target duplicates reference prices or source; independent comparison suppressed.")
        comparison = {"implied_probs": target_probs, "prices": target, "shared_reference": shared,
                      "probability_gap": None if shared else [p-q for p, q in zip(probs, target_probs)],
                      "edge_vs_break_even": None if shared else [p - 1/o for p, o in zip(probs, target)]}
    return {"home": home, "away": away, "kickoff": match["kickoff"], "as_of": match["as_of"],
            "market": "1x2_90", "outcomes": list(OUTCOMES),
            "base_probs": base_probs, "probs": probs, "market_probs": market_probs,
            "pre_calibration_probs": uncalibrated, "temperature": temperature,
            "role_probs": role_probs, "statistical_probs_before_evidence": raw_probs,
            "score_matrix": matrix, "top_scores": [{"home": i, "away": j, "p": p} for p,i,j in best],
            "expected_goals": expected, "model_goal_means": means, "prior_goal_means": raw_means,
            "evidence_xg_delta": deltas, "evidence": evidence, "roles": roles,
            "rho_used": rho_used, "market_weight_used": market_weight if odds else 0,
            "role_weight_used": role_weight if roles else 0,
            "odds_source": match.get("odds_source"), "odds_at": match.get("odds_at"),
            "target_odds_source": match.get("target_odds_source"), "target_odds_at": match.get("target_odds_at"),
            "target_comparison": comparison, "strength": strength,
            "history_as_of": history_cutoff.isoformat(), "eligible_history": len(eligible),
            "ignored_history": ignored, "warnings": warnings}
