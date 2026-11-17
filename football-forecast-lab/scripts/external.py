"""Optional read-only Binance sports forecasts and stateless signal scenarios."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from reporting import json_text, write_text
from sources import fetch_json

HOST = "web3.binance.com"
BASE = f"https://{HOST}/bapi/defi/v1/public/wc-assistant/match/"
MODEL_FIELDS = ("home_win_prob", "draw_prob", "away_win_prob")
MARKET_FIELDS = ("market_prob_home_win", "market_prob_draw", "market_prob_away_win")


def _now():
    return datetime.now(timezone.utc)


def _stamp(value, field):
    """The provider documents these dates as UTC, including timezone-less UTC strings."""
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value / 1000 if abs(value) > 1e11 else value, timezone.utc)
        if not isinstance(value, str) or " " not in value and "T" not in value:
            raise ValueError()
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError(f"Binance returned an invalid {field}") from exc


def _call(path, payload=None):
    response = fetch_json(BASE + path, allowed_host=HOST, payload=payload)
    if not isinstance(response, dict) or "data" not in response:
        raise ValueError("Unexpected response envelope from Binance")
    code = response.get("code")
    if response.get("success") is False or code is not None and str(code) not in ("000000", "0", "200"):
        raise ValueError(f"Binance declined the sports request (code {str(code)[:32]})")
    return response["data"]


def _id(value, label):
    if not isinstance(value, (int, str)) or isinstance(value, bool):
        raise ValueError(f"Missing or invalid {label}")
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,179}", value):
        raise ValueError(f"Invalid {label}")
    return value


def _team(raw):
    value = raw.get("name") if isinstance(raw, dict) else raw
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Binance did not identify both teams")
    return value.strip()


def resolve(slugs):
    wanted = list(dict.fromkeys(_id(s, "slug") for s in slugs))
    output = {}
    for start in range(0, len(wanted), 50):
        batch = wanted[start:start + 50]
        rows = _call("resolve-by-slug", {"slugs": batch})
        if not isinstance(rows, list):
            raise ValueError("Invalid fixture resolution response")
        for row in rows:
            if not isinstance(row, dict) or row.get("event_slug") not in batch:
                raise ValueError("Unexpected fixture in Binance resolution")
            slug = row["event_slug"]
            normalized = {
                "slug": slug, "canonical_match_id": _id(row.get("canonical_match_id"), "match ID"),
                "home": _team(row.get("home_team")), "away": _team(row.get("away_team")),
                "kickoff": _stamp(row["kickoff_at"], "kickoff").isoformat() if row.get("kickoff_at") else None,
                "status": str(row.get("status") or "UNKNOWN").upper(),
                "competition": row.get("tournament"), "stage": row.get("stage")}
            if slug in output and normalized != output[slug]:
                raise ValueError("A slug resolved to multiple fixtures")
            output[slug] = normalized
    return {"kind": "fixtures", "source": "binance-sports", "observed_at": _now().isoformat(),
            "records": [output[s] for s in wanted if s in output],
            "unresolved_slugs": [s for s in wanted if s not in output]}


def recent(limit=25):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be 1..1000")
    slugs = _call("recent-unfinished")
    if not isinstance(slugs, list):
        raise ValueError("Unexpected unfinished-fixtures response")
    return resolve(slugs[:limit])


def _probs(payload, fields, market=False):
    if not isinstance(payload, dict):
        raise ValueError("Unexpected Binance probability record")
    vals = [payload.get(k) for k in fields]
    if market and any(v is None for v in vals):
        return None
    parsed = []
    for field, val in zip(fields, vals):
        if isinstance(val, bool):
            raise ValueError(f"Invalid {field}")
        try:
            p = float(val)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Missing or invalid {field}") from exc
        if not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError(f"{field} must be in [0,1]")
        parsed.append(p)
    if not market and abs(sum(parsed) - 1.0) > 0.015:
        raise ValueError("Binance 1X2 model probabilities do not sum to one")
    return parsed


def _edits(edits, baseline):
    if not isinstance(edits, list) or not edits or not all(isinstance(e,dict) for e in edits):
        raise ValueError("edits must contain a non-empty array of signal objects")
    signals = baseline.get("signals") or []
    known = {(s.get("signal_id"),s.get("team_side")) for s in signals if isinstance(s,dict)}
    seen = set()
    for edit in edits:
        unknown = set(edit) - {"signal_id","team_side","manual_delta","enabled"}
        key = (edit.get("signal_id"),edit.get("team_side"))
        if unknown or not all(isinstance(v,str) and v for v in key) or key not in known or key in seen:
            raise ValueError("Only distinct signal_id and team_side pairs from this baseline may be edited")
        seen.add(key)
        if key[1] not in ("home","away") or "enabled" not in edit and "manual_delta" not in edit:
            raise ValueError("Provide home/away team_side and enabled or manual_delta")
        if "enabled" in edit and type(edit["enabled"]) is not bool:
            raise ValueError("enabled must be true or false")
        if "manual_delta" in edit:
            delta = edit["manual_delta"]
            if not isinstance(delta, dict) or not delta or set(delta) - {"attack_delta","defense_delta"}:
                raise ValueError("manual_delta accepts attack_delta and defense_delta")
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in delta.values()):
                raise ValueError("Scenario deltas must be finite numbers")
    return edits


def prediction(slug, *, context=False, edits=None):
    matches = resolve([slug])["records"]
    if len(matches) != 1:
        raise ValueError("Fixture slug could not be resolved uniquely")
    fixture = matches[0]
    if fixture["status"] != "SCHEDULED" or not fixture["kickoff"]:
        raise ValueError("A scheduled fixture with a verified kickoff is required")
    kickoff = _stamp(fixture["kickoff"], "kickoff")
    if _now() >= kickoff:
        raise ValueError("Kickoff has passed")
    cmid = fixture["canonical_match_id"]
    raw = _call(f"prediction/{cmid}")
    baseline = _probs(raw, MODEL_FIELDS)
    record = dict(fixture, market="1x2_90", probs=baseline,
                  market_probs=_probs(raw, MARKET_FIELDS, market=True), computed_at=raw.get("computed_at"),
                  score_distribution=raw.get("score_distribution"), signals=raw.get("signals"),
                  market_volume_24h=raw.get("market_volume_24h"))
    if context:
        record["context"] = {name: _call(f"{name}/{cmid}") for name in ("news-insights","master-analysis")}
    if edits is not None:
        changed = _call(f"recompute-final/{cmid}", {"signals": _edits(edits, raw)})
        after = _probs(changed, MODEL_FIELDS)
        record["scenario"] = {"edits": edits, "probs": after,
                              "delta_pp": [100 * (p-q) for p,q in zip(after,baseline)],
                              "applied_signals": changed.get("applied_signals"),
                              "score_distribution": changed.get("score_distribution")}
    observed = _now()
    if observed >= kickoff:
        raise ValueError("Fixture kicked off during retrieval; discard this pre-match snapshot")
    if raw.get("computed_at") is not None and _stamp(raw["computed_at"], "computed_at") > observed:
        raise ValueError("Provider computation timestamp is in the future")
    return {"kind": "external", "source": "binance-sports", "observed_at": observed.isoformat(),
            "records": [record]}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Collect public, read-only Binance sports fixtures and external model comparisons.",
        epilog="Examples: recent --limit 10; resolve SLUG; predict SLUG --context --signals edits.json --out external.json")
    sub = parser.add_subparsers(dest="cmd",required=True)
    recent_cmd = sub.add_parser("recent",help="discover unfinished fixtures, including their statuses")
    recent_cmd.add_argument("--limit",type=int,default=25)
    resolve_cmd = sub.add_parser("resolve",help="resolve public event slugs to kickoff and fixture IDs")
    resolve_cmd.add_argument("slug",nargs="+")
    pred_cmd = sub.add_parser("predict",help="read scheduled pre-match probabilities and optional what-if result")
    pred_cmd.add_argument("slug")
    pred_cmd.add_argument("--context",action="store_true", help="also retrieve external news cards and master analysis")
    pred_cmd.add_argument("--signals",type=Path,help="JSON file with a signals array (validated against the baseline)")
    for command in (recent_cmd,resolve_cmd,pred_cmd):
        command.add_argument("--out",type=Path, help="write snapshot JSON here; default is stdout")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "recent":
            record = recent(args.limit)
        elif args.cmd == "resolve":
            record = resolve(args.slug)
        else:
            changes = None
            if args.signals:
                changes = json.loads(args.signals.read_text(encoding="utf-8-sig"))
                if isinstance(changes,dict):
                    if "signals" not in changes:
                        raise ValueError("Signals file must provide a signals array")
                    changes = changes["signals"]
                if changes is None:
                    raise ValueError("Signals cannot be null")
            record = prediction(args.slug, context=args.context, edits=changes)
        if args.out:
            write_text(args.out, json_text(record))
        else:
            print(json_text(record))
    except (ValueError,OSError) as exc:
        parser.exit(2, f"external: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
