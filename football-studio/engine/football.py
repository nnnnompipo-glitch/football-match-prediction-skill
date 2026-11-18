"""Offline match forecasting, scenarios, competitions, evaluation and publication."""
import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from competitions import backtest_rows, simulate_tournament
from fitting import attach_fit, fit_strength
from ledger import archived, freeze, review, settle
from model import predict_match
from ratings import historical_elo, recent_form
from reporting import json_text, render_html, write_text
from team_names import TeamNames
from workflow import derived_markets, identity, instant, prepare, records, scenario_match, utc_now


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def rule_index(inputs):
    if not isinstance(inputs, dict):
        raise ValueError("rule_inputs 需要对象")
    values = [inputs.get(k) for k in ("motivation", "odds_trend", "form")]
    if not all(type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 1 for v in values):
        raise ValueError("规则指数的战意、走势和状态必须都有 0–1 的分数")
    for flag in ("late_season", "popular"):
        if flag in inputs and type(inputs[flag]) is not bool:
            raise ValueError(f"{flag} 须为布尔值")
    weights = [.50, .35, .15] if inputs.get("late_season") else [.40, .35, .25]
    factor = .85 if inputs.get("popular") else 1.
    return {"score_100": round(100 * factor * sum(v*w for v,w in zip(values,weights)), 2),
            "weights": weights, "popular_factor": factor, "meaning": "heuristic index, uncalibrated"}


def forecast(args):
    data = load(args.input)
    aliases = load(args.aliases) if args.aliases else {}
    teams = TeamNames(aliases)
    rows = [teams.row(row) for row in records(data)]
    base_stamp = data.get("observed_at") if isinstance(data, dict) else None
    if args.home:
        rows = [m for m in rows if teams.name(m["home"]).casefold() == teams.name(args.home).casefold()]
    if args.away:
        rows = [m for m in rows if teams.name(m["away"]).casefold() == teams.name(args.away).casefold()]
    if not rows:
        raise ValueError("没有匹配的比赛")
    localize = getattr(args, "localize", None)
    if localize is not None:
        rows = localize(rows)
    history = [teams.row(r) for r in records(load(args.history))] if args.history else []
    snapshots = [load(path) for path in args.snapshot]
    if aliases:
        snapshots = [{**snap, "records": [teams.row(r) for r in records(snap)]} for snap in snapshots]
    contexts = [load(path) for path in args.context]
    fit = load(args.fit) if args.fit else None
    calibration = load(args.calibration) if args.calibration else None
    scenarios = [teams.row(r) for r in records(load(args.scenarios))] if args.scenarios else []
    if len({s["name"] for s in scenarios}) != len(scenarios):
        raise ValueError("情景名称须唯一")
    if len(rows) > 1 and (scenarios or contexts):
        raise ValueError("请按球队选定单场后再应用情景或关联背景资料")
    batch = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        status = str(row.get("status", "")).strip().upper().replace("-", "_").replace(" ", "_")
        scheduled = {"SCHEDULED", "TIMED", "NS", "NOT_STARTED", "UPCOMING", "PRE_MATCH", "PREMATCH"}
        has_result = row.get("home_goals") is not None or row.get("away_goals") is not None
        if has_result or ("status" in row and status not in scheduled):
            if len(rows) == 1:
                raise ValueError("所选比赛状态不能用于当前赛前预测")
            continue
        row["as_of"] = args.as_of or row.get("as_of") or base_stamp or utc_now()
        if base_stamp and instant(base_stamp) > instant(row["as_of"]):
            raise ValueError("输入赛单的快照获取时间晚于预测截点")
        if identity(row) in seen:
            raise ValueError("输入赛单包含同一场比赛的重复记录")
        seen.add(identity(row))
        m, audit = prepare(row, snapshots, bookmaker=args.bookmaker)
        if aliases:
            m["team_aliases"] = aliases
        if fit:
            m = attach_fit(m, fit)
        match_history = history
        calculation_stamp = m["as_of"]
        if calibration:
            from calibrate import calibration_history, validate_for_match
            from competitions import calibration_cutoff
            temperature = validate_for_match(calibration, m)
            match_history = calibration_history(calibration, m, history)
            calculation_stamp = calibration_cutoff(m)
            m["temperature"] = temperature
            m["calibration_provenance"] = {**calibration, "history_cutoff":calculation_stamp}
        attached = []
        for ctx in contexts:
            if instant(ctx["observed_at"]) > instant(m["as_of"]):
                raise ValueError("背景快照晚于赛前截点")
            attached.append({"kind":ctx["kind"],"source":ctx.get("source"),"observed_at":ctx["observed_at"],
                             "records":records(ctx),"warnings":ctx.get("warnings",[])})
        if attached:
            m["research_context"] = attached
        pred = predict_match(m, match_history, history_as_of=calculation_stamp)
        matrix = pred.pop("score_matrix")
        markets = derived_markets(matrix, args.handicap, args.total)
        variants = []
        for s in scenarios:
            variant = scenario_match(m, s)
            if calibration:
                try:
                    variant.pop("temperature", None)
                    variant["temperature"] = validate_for_match(calibration, variant)
                except ValueError as exc:
                    raise ValueError(f"情景「{s['name']}」与这份校准不兼容：{exc}") from exc
            other = predict_match(variant, match_history, history_as_of=calculation_stamp)
            variants.append({"name": s["name"], "assumptions": {k:v for k,v in s.items() if k != "name"},
                             "probs": other["probs"], "expected_goals": other["expected_goals"],
                             "delta_pp": [100*(a-b) for a,b in zip(other["probs"], pred["probs"])]})
        result = {"input": m, "prediction": pred, "markets": markets, "sources": audit, "scenarios": variants}
        if match_history:
            result["form"] = recent_form(m, match_history)
        if args.matrix:
            pred["score_matrix"] = matrix
        if args.timeline:
            from timeline import timing_summary
            result["timeline"] = timing_summary(matrix)
        if args.knockout or m.get("knockout") is True:
            decider = m.get("decider_home")
            if decider is None:
                gap = (m["home_elo"] - m["away_elo"]) if m.get("home_elo") is not None and m.get("away_elo") is not None else 0
                decider = 1 / (1 + 10 ** (-max(-2400,min(2400,gap)) / 600))
            if type(decider) not in (int,float) or not 0 <= decider <= 1:
                raise ValueError("decider_home 必须是 [0,1] 内的条件概率")
            h,d,a = pred["probs"]
            result["advancement"] = {"home":h+d*decider,"away":a+d*(1-decider),
                                     "home_if_level_after_90":decider}
        if "rule_inputs" in m:
            result["rule_index"] = rule_index(m["rule_inputs"])
        batch.append(result)
    if not batch:
        raise ValueError("赛单中没有可预测的未赛场次")
    if args.ledger:
        freeze(args.ledger, batch, history)
    return {"kind": "forecast", "market": "1x2_90", "matches": batch}


def combo(args):
    forecasts = load(args.forecasts)
    if forecasts.get("kind") != "forecast":
        raise ValueError("需要 forecast 输出")
    bets = records(load(args.picks))
    if not bets:
        raise ValueError("至少需要一个选择")
    index = {identity(item["input"]): item for item in forecasts["matches"]}
    used, legs, joint = set(), [], 1.
    for bet in bets:
        key = identity(bet)
        if key in used or key not in index:
            raise ValueError("跨场组合需要不重复且已预测的比赛")
        used.add(key)
        if bet.get("outcome") not in ("home","draw","away"):
            raise ValueError("outcome 必须是 home、draw 或 away")
        probability = index[key]["prediction"]["probs"][("home","draw","away").index(bet["outcome"])]
        legs.append({"home":bet["home"],"away":bet["away"],"outcome":bet["outcome"],"p":probability})
        joint *= probability
    return {"kind":"combination","assumption":"independent match outcomes","legs":legs,
            "joint_probability":joint,"fair_decimal_under_independence":1/joint if joint else None}


def parser():
    cli = argparse.ArgumentParser(description="足球赛前分析与赛事复盘")
    sub = cli.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("forecast", help="单场或整张赛单，支持市场、证据、角色与假设")
    pre.add_argument("input")
    pre.add_argument("--history")
    pre.add_argument("--aliases", help="用户确认过的球队显示名到统一队名的 JSON 映射")
    pre.add_argument("--snapshot", action="append", default=[])
    pre.add_argument("--context",action="append",default=[],help="将人工确认属于这场的名册、伤停、天气或新闻快照列为资料")
    pre.add_argument("--fit",help="赛前取得的攻防参数 JSON")
    pre.add_argument("--calibration",help="通过时间验证的温度校准 JSON")
    pre.add_argument("--bookmaker")
    pre.add_argument("--home")
    pre.add_argument("--away")
    pre.add_argument("--as-of")
    pre.add_argument("--scenarios")
    pre.add_argument("--matrix", action="store_true", help="在 JSON 中附加完整比分概率矩阵；行是主队进球，列是客队进球")
    pre.add_argument("--timeline", action="store_true", help="在均匀进球时间假设下估算半场和各15分钟时段")
    pre.add_argument("--total", type=float, default=2.5)
    pre.add_argument("--handicap", type=int, default=0)
    pre.add_argument("--knockout",action="store_true",help="另算单场淘汰赛晋级概率")
    pre.add_argument("--ledger")
    cup = sub.add_parser("cup",help="小组与淘汰赛的重复模拟")
    cup.add_argument("input")
    cup.add_argument("--sims",type=int,default=1000)
    cup.add_argument("--seed",type=int,default=7)
    bt = sub.add_parser("backtest",help="逐日滚动检验")
    bt.add_argument("history")
    bt.add_argument("--min-train",type=int,default=20)
    bt.add_argument("--window",type=int)
    fit = sub.add_parser("fit",help="从已知历史拟合攻防与低比分参数")
    fit.add_argument("history")
    fit.add_argument("--as-of",required=True)
    fit.add_argument("--competition")
    elo = sub.add_parser("elo", help="用常规时间历史赛果计算本地 Elo 评级快照")
    elo.add_argument("history")
    elo.add_argument("--as-of", required=True)
    elo.add_argument("--competition")
    sett = sub.add_parser("settle",help="按常规时间赛果结算冻结记录")
    sett.add_argument("ledger")
    sett.add_argument("results")
    rev = sub.add_parser("review",help="分别评估赛前冻结与事后回放")
    rev.add_argument("ledger")
    archive = sub.add_parser("archive",help="按对阵和截点导出冻结预测、实际输入历史及完整报告版本")
    archive.add_argument("ledger")
    archive.add_argument("--home",required=True)
    archive.add_argument("--away",required=True)
    archive.add_argument("--kickoff",required=True)
    archive.add_argument("--as-of",required=True)
    comb = sub.add_parser("combo",help="不同比赛在独立假设下的联合概率")
    comb.add_argument("forecasts")
    comb.add_argument("picks")
    for cmd in (pre,cup,bt,sett,rev,archive,comb,fit,elo):
        cmd.add_argument("--out",help="JSON 文件；默认标准输出")
        cmd.add_argument("--html",help="自包含 HTML 报告")
    return cli


def main():
    args = parser().parse_args()
    inputs = [getattr(args, k, None) for k in ("input","history","scenarios","ledger","results","forecasts","picks","fit","calibration","aliases")]
    inputs.extend(getattr(args,"snapshot",[]))
    inputs.extend(getattr(args,"context",[]))
    prior = [Path(p).resolve() for p in inputs if p]
    outputs = [Path(p).resolve() for p in (args.out,args.html) if p]
    if len(set(outputs)) != len(outputs) or any(p in prior for p in outputs):
        raise ValueError("报告文件不能覆盖输入、账本或另一份输出")
    if args.command == "forecast":
        result = forecast(args)
    elif args.command == "cup":
        result = {**simulate_tournament(load(args.input), sims=args.sims, seed=args.seed), "kind":"cup"}
    elif args.command == "backtest":
        original = load(args.history)
        results = records(original)
        result = {**backtest_rows(results, min_train=args.min_train, window=args.window), "kind":"backtest"}
        result["dataset"] = {k:original[k] for k in ("source","endpoint","observed_at","raw_sha256") if isinstance(original, dict) and k in original}
        result["dataset"]["rows"] = len(results)
    elif args.command == "elo":
        result = historical_elo(records(load(args.history)), args.as_of, args.competition)
    elif args.command == "fit":
        result = {**fit_strength(records(load(args.history)), args.as_of, args.competition),"kind":"fit"}
    elif args.command == "settle":
        result = {**settle(args.ledger, records(load(args.results))), "kind":"settle"}
    elif args.command == "review":
        result = {**review(args.ledger), "kind":"review"}
    elif args.command == "archive":
        result = archived(args.ledger, vars(args), args.as_of)
    else:
        result = combo(args)
    if args.html:
        write_text(args.html, render_html(result))
    if args.out:
        write_text(args.out, json_text(result)+"\n")
    else:
        print(json_text(result))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        sys.exit(f"操作失败：{exc}")
