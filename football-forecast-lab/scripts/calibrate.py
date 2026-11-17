"""Learn a bounded temperature on historical 1X2 probabilities, then validate on later dates."""

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
from competitions import backtest_cutoff, calibration_cutoff, history_at_cutoff, history_policy


SCHEMA = "football-forecast-lab/temperature-v2"
MIN_TEMP, MAX_TEMP = 0.25, 4.0
UTC = timezone.utc


def _probabilities(probs):
    if not isinstance(probs, (tuple, list)) or len(probs) != 3:
        raise ValueError("Expected three probabilities in H/D/A order")
    if any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p)
           or not 0 <= p <= 1 for p in probs) or not math.isclose(sum(probs), 1.0, abs_tol=1e-6):
        raise ValueError("1X2 probabilities must be finite, between zero and one and sum to one")
    total = sum(probs)
    return [p / total for p in probs]


def apply_temperature(probs, temperature):
    """Apply p_i^(1/T) / sum(p_j^(1/T)); preserves exact zero-probability outcomes."""
    probs = _probabilities(probs)
    if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature) or not MIN_TEMP <= temperature <= MAX_TEMP):
        raise ValueError(f"temperature must be in [{MIN_TEMP}, {MAX_TEMP}]")
    if temperature == 1:
        return probs
    return _transform(probs, temperature)


def _transform(probs, temperature):
    weights = [p ** (1.0 / temperature) for p in probs]
    total = sum(weights)
    return [w / total for w in weights]


def _metrics(rows, temperature):
    loss = brier = 0.0
    for _, probs, outcome, _, _ in rows:
        p = _transform(probs, temperature)
        loss -= math.log(max(1e-15, p[outcome]))
        brier += sum((v - (i == outcome)) ** 2 for i, v in enumerate(p))
    return {"n": len(rows), "log_loss": loss / len(rows), "brier": brier / len(rows)}


def _fit(rows):
    # Bounded deterministic search; compare endpoints and identity as well as the interior optimum.
    lo, hi = MIN_TEMP, MAX_TEMP
    for _ in range(42):
        a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if _metrics(rows, a)["log_loss"] <= _metrics(rows, b)["log_loss"]:
            hi = b
        else:
            lo = a
    candidates = (1.0, MIN_TEMP, MAX_TEMP, (lo + hi) / 2)
    return min(candidates, key=lambda t: _metrics(rows, t)["log_loss"])


def _day(s):
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError) as exc:
        raise ValueError("Each forecast needs date YYYY-MM-DD") from exc


def _timestamp(s, label):
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.astimezone(UTC)
    except (AttributeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid timezone-aware {label}") from exc


def _verified_policy(obj):
    settings = obj.get("history_policy")
    if not isinstance(settings, dict) or "min_train" not in settings or "window" not in settings:
        raise ValueError("Missing history_policy; rerun backtest and calibration to record the sampling settings")
    expected = history_policy(settings["min_train"], settings["window"])
    if settings != expected:
        raise ValueError("Incompatible history_policy model version or UTC cutoff; rerun backtest and calibration")
    return expected


def validate_for_match(artifact, match):
    """Return the deployed temperature only for the same prediction profile and a later live cutoff."""
    if not isinstance(artifact, dict) or artifact.get("schema") != SCHEMA:
        raise ValueError("Unsupported temperature calibration schema; rerun backtest and calibration")
    _verified_policy(artifact)
    profile = artifact.get("applicability")
    if not isinstance(profile, dict) or profile.get("profile") != "backtest-history-only":
        raise ValueError("Unsupported calibration profile")
    if (profile.get("market") != "1x2_90" or profile.get("order") != ["H", "D", "A"]
            or match.get("market", "1x2_90") != "1x2_90"):
        raise ValueError("Calibration requires regulation-time 1X2 in H/D/A order")
    if profile.get("competition") != (match.get("competition") or match.get("league")):
        raise ValueError("Calibration competition mismatch (including unlabeled datasets)")
    if (any(match.get(k) is not None for k in ("home_xg", "away_xg", "home_elo", "away_elo", "odds",
                                                "fit_model", "fitted_model", "fitted", "fit_artifact"))
            or match.get("evidence") or match.get("roles") or match.get("rho", -0.06) != -0.06
            or match.get("temperature", 1.0) != 1.0):
        raise ValueError("History-only calibration cannot be applied to this model/market/evidence profile")
    cutoff = _timestamp(match.get("as_of"), "forecast as_of")
    dates = [_day(artifact.get(k)) for k in ("trained_until", "validation_start", "validated_until")]
    if not dates[0] < dates[1] <= dates[2] < cutoff.date():
        raise ValueError("Calibration must be validated on disjoint dates strictly before this as_of date")
    temp = artifact.get("temperature")
    apply_temperature([0.4, 0.3, 0.3], temp)  # Validate against the same numerical contract as application.
    enabled = artifact.get("enabled")
    if type(enabled) is not bool or (not enabled and temp != 1.0):
        raise ValueError("Invalid enabled flag or non-identity temperature on disabled calibration")
    return temp


def calibration_history(artifact, match, history):
    """Return precisely the historical sample that the deployed probability calibration expects."""
    validate_for_match(artifact, match)
    cutoff = _timestamp(calibration_cutoff(match), "calibration cutoff")
    competition = artifact["applicability"]["competition"]
    return history_at_cutoff(history, competition, cutoff, artifact["history_policy"])


def _available(row, day):
    if row.get("result_available_at") is None:
        return datetime.combine(day + timedelta(days=1), time.min, UTC)
    try:
        dt = datetime.fromisoformat(row["result_available_at"].replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.astimezone(UTC).date() < day:
            raise ValueError()
        return dt.astimezone(UTC)
    except (AttributeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid result_available_at for historical forecast") from exc


def fit_calibration(report, *, min_fit=20, min_validation=10, fit_fraction=0.7, competition=None):
    """Select the temperature by fit-period log loss; retain it only on a separate later validation period."""
    if not isinstance(report, dict) or not isinstance(report.get("forecasts"), list):
        raise ValueError("Expected a backtest report containing a forecasts array")
    settings = _verified_policy(report)
    if any(k in report and report[k] != settings[k] for k in ("min_train", "window")):
        raise ValueError("Backtest summary disagrees with its history_policy")
    if (type(min_fit) is not int or min_fit < 2 or type(min_validation) is not int or min_validation < 2
            or type(fit_fraction) not in (int, float) or not 0 < fit_fraction < 1):
        raise ValueError("Both period minima must be >= 2 and fit_fraction must be between zero and one")
    records = []
    seen = set()
    competitions = set()
    for row in report["forecasts"]:
        if not isinstance(row, dict):
            raise ValueError("Each forecast must be an object")
        label = row.get("competition")
        if label is not None and not isinstance(label, str):
            raise ValueError("competition must be a string")
        if competition is not None and label != competition:
            continue
        competitions.add(label)
        if row.get("market", "1x2_90") != "1x2_90":
            raise ValueError("Only regulation-time 1X2 forecasts can share this calibration")
        day = _day(row.get("date"))
        home, away = row.get("home"), row.get("away")
        if any(not isinstance(v, str) or not v for v in (home, away)) or home == away:
            raise ValueError("Each calibration record needs distinct home and away teams")
        key = (day, home, away, label)
        if key in seen:
            raise ValueError(f"Duplicate calibration fixture: {home} vs {away} on {day}")
        seen.add(key)
        actual = row.get("actual")
        if actual not in ("H", "D", "A"):
            raise ValueError("Historical actual must be H, D or A")
        as_of = _timestamp(row.get("as_of"), "historical as_of")
        kickoff = _timestamp(row["kickoff"], "historical kickoff") if row.get("kickoff") else None
        if (kickoff and kickoff.date() != day) or as_of != backtest_cutoff(day, kickoff):
            raise ValueError("Historical forecast cutoff disagrees with the UTC day history_policy")
        count = row.get("training_rows")
        if (type(count) is not int or count < settings["min_train"]
                or (settings["window"] is not None and count > settings["window"])):
            raise ValueError("Historical training_rows violates the backtest history_policy")
        records.append((day, _probabilities(row.get("probs")), ("H", "D", "A").index(actual),
                        _available(row, day), as_of))
    if len(competitions) > 1:
        raise ValueError("Mixed competitions: select --competition before fitting a calibration")
    records.sort(key=lambda r: r[0])
    valid_splits = [i for i in range(min_fit, len(records) - min_validation + 1)
                    if records[i - 1][0] < records[i][0]]
    if not valid_splits:
        raise ValueError(f"Not enough distinct-date data: need >= {min_fit} earlier and >= {min_validation} later fixtures")
    target = len(records) * fit_fraction
    # Training labels must already be visible before the first validation forecast.
    for i in sorted(valid_splits, key=lambda idx: abs(idx - target)):
        cutoff = min(row[4] for row in records[i:])
        fit = [row for row in records[:i] if row[3] <= cutoff]
        if len(fit) >= min_fit:
            break
    else:
        raise ValueError("Too few training outcomes published by the first validation cutoff")
    heldout = records[i:]
    candidate = _fit(fit)
    baseline, alternative = _metrics(heldout, 1.0), _metrics(heldout, candidate)
    enabled = (alternative["log_loss"] + 1e-8 < baseline["log_loss"]
               and alternative["brier"] <= baseline["brier"] + 1e-12)
    last_observed = max(row[3] for row in heldout)
    return {"schema": SCHEMA, "temperature": candidate if enabled else 1.0, "enabled": enabled,
            "history_policy": settings,
            "candidate_temperature": candidate, "trained_until": fit[-1][0].isoformat(),
            "validation_start": heldout[0][0].isoformat(), "validation_last_fixture": heldout[-1][0].isoformat(),
            "validated_until": max(heldout[-1][0], last_observed.date()).isoformat(),
            "results_available_at": last_observed.isoformat(), "excluded_late_fit_labels": i - len(fit),
            "applicability": {"market": "1x2_90", "order": ["H", "D", "A"],
                              "competition": next(iter(competitions)), "profile": "backtest-history-only"},
            "fit": {"identity": _metrics(fit, 1), "candidate": _metrics(fit, candidate)},
            "holdout": {"identity": baseline, "candidate": alternative},
            "reason": ("later-date log loss improved and Brier did not worsen" if enabled else
                       "later-date log loss and Brier acceptance gate not met; identity retained"),
            "notes": "Holdout selects the deployment gate and is not a final independent test. Predict on UTC dates strictly after validated_until. Brier is summed over H/D/A."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backtest", help="JSON report from the backtest command")
    parser.add_argument("--out", type=Path, help="Destination JSON calibration")
    parser.add_argument("--min-fit", type=int, default=20)
    parser.add_argument("--min-validation", type=int, default=10)
    parser.add_argument("--fit-fraction", type=float, default=0.7)
    parser.add_argument("--competition", help="Select one competition from a mixed backtest")
    args = parser.parse_args()
    try:
        report = json.loads(Path(args.backtest).read_text(encoding="utf-8-sig"))
        artifact = fit_calibration(report, min_fit=args.min_fit, min_validation=args.min_validation,
                                   fit_fraction=args.fit_fraction, competition=args.competition)
        payload = json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            temp = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.out.parent,
                                                 prefix=".temperature-", suffix=".tmp", delete=False) as fp:
                    temp = Path(fp.name)
                    fp.write(payload)
                temp.replace(args.out)
            finally:
                if temp:
                    temp.unlink(missing_ok=True)
        else:
            print(payload, end="")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"calibrate: {exc}\n")


if __name__ == "__main__":
    main()
