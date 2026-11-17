"""Write portable UTF-8 output and render escaped, self-contained match reports."""
import html
import json
import os
from pathlib import Path
import tempfile


def write_text(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False,
                                     dir=target.parent, prefix=".forecast-") as out:
        temp = Path(out.name)
        try:
            out.write(value)
        except BaseException:
            out.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def esc(value):
    return html.escape(str(value), quote=True)


def pct(value):
    return f"{value:.1%}"


def table(headers, rows):
    heading = "".join("<th>" + esc(s) + "</th>" for s in headers)
    body = "".join("<tr>" + "".join("<td>" + esc(c) + "</td>" for c in row) + "</tr>" for row in rows)
    return "<div class='scroll'><table><thead><tr>" + heading + "</tr></thead><tbody>" + body + "</tbody></table></div>"


def block(title, text):
    return "<h3>" + esc(title) + "</h3><p>" + esc(text) + "</p>"


def match_panel(item):
    m, pred = item["input"], item["prediction"]
    heading = esc(m["home"]) + " — " + esc(m["away"])
    parts = ["<section><h2>" + heading + "</h2><p>开球 " + esc(m["kickoff"]) +
             " · 赛前截点 " + esc(m["as_of"]) + " · 常规时间</p>"]
    if m.get("demo"):
        parts.append("<p><strong>虚构演示数据</strong></p>")
    views = [["基础", *map(pct, pred["base_probs"])], ["最终", *map(pct, pred["probs"])]]
    if pred.get("market_probs"):
        views.append(["参考市场去水", *map(pct, pred["market_probs"])] )
    if pred.get("role_probs"):
        views.append(["研究角色意见", *map(pct, pred["role_probs"])])
    parts.append(table(["胜平负口径", "主胜", "平局", "客胜"], views))
    markets = item["markets"]
    parts.append(block("进球与比分", "预期进球 " + " / ".join(f"{v:.2f}" for v in pred["expected_goals"])
                       + "；比分候选 " + "，".join(f"{x['home']}–{x['away']} ({pct(x['p'])})"
                                               for x in pred["top_scores"][:5])))
    parts.append(block("派生市场", f"双方进球 {pct(markets['both_teams_score'])}；"
                       f"大于 {markets['total_line']} 球 {pct(markets['over_push_under'][0])}；"
                       f"主队让球修正 {markets['home_handicap']:+d} 后胜／平／负 " +
                       " / ".join(map(pct, markets["handicap_home_draw_away"]))))
    if item["scenarios"]:
        parts.append("<h3>情景敏感性</h3>" + table(["情景", "主胜", "平", "客胜", "主胜变化"],
                     ([v["name"], *map(pct, v["probs"]), f"{v['delta_pp'][0]:+.2f} 个百分点"]
                      for v in item["scenarios"])))
    if "advancement" in item:
        adv = item["advancement"]
        parts.append(block("单场淘汰赛晋级", f"主队 {pct(adv['home'])}，客队 {pct(adv['away'])}；90 分钟打平后，假设主队晋级率 {pct(adv['home_if_level_after_90'])}。"))
    if "timeline" in item:
        timing = item["timeline"]
        parts.append(block("半场与进球时段",timing["assumption"]))
        parts.append(block("半场主胜／平局／客胜"," / ".join(pct(p) for p in timing["half_probs"])))
        parts.append(table(["时段（分钟）","预期进球","至少一球"],(
            [f"{p['start_minute']}–{p['end_minute']}",f"{p['expected_goals']:.2f}",pct(p["p_at_least_one_goal"])]
            for p in timing["periods"])))
    audit = item["sources"]
    if audit["snapshots"]:
        parts.append("<h3>取数记录</h3>" + table(["来源", "观测时间", "匹配情况"],
                     ([s.get("source") or s["kind"], s["observed_at"], s.get("status", s.get("matched"))]
                      for s in audit["snapshots"])))
    if audit["quote_history"]:
        parts.append("<h3>市场变动</h3>" + table(["报价更新时间", "抓取时间", "公司", "主／平／客"],
                     ([q["quote_observed_at"], q["captured_at"], q["bookmaker"], " / ".join(map(str, q["odds"]))]
                      for q in audit["quote_history"])))
    if item.get("form"):
        form = item["form"]
        parts.append("<h3>近期表现</h3>" + table(["球队","可得近况场次","胜／平／负","进／失球","距上场天数"],
                     ([team,stat["n"],f"{stat['W']} / {stat['D']} / {stat['L']}",f"{stat['GF']} / {stat['GA']}",
                       stat["days_since_last_listed_game"] if stat["n"] else "未知"] for team,stat in form["teams"].items())))
        parts.append(block("最近直接交锋","；".join(f"{g['date']} {g['home']} {g['score'][0]}–{g['score'][1]} {g['away']}"
                                             for g in form["head_to_head"]) or "已提供历史中无直接交锋。"))
    if m.get("evidence"):
        parts.append("<h3>赛前证据</h3>" + table(["球队", "证据", "来源", "观测时间"],
                     ([e.get("team",""), e.get("note") or e.get("kind",""), e.get("source",""),
                       e.get("observed_at","")] for e in m["evidence"])))
    if pred["warnings"]:
        parts.append(block("数据限制", "；".join(map(str, pred["warnings"]))))
    if audit["upstream"]:
        parts.append("<details><summary>外部预测原始对照</summary><pre>" +
                     esc(json_text(audit["upstream"])) + "</pre></details>")
    comparison = pred.get("target_comparison")
    if comparison:
        if comparison["shared_reference"]:
            parts.append(block("目标价与参考价重合","已跳过独立价差计算。"))
        else:
            parts.append("<h3>目标市场</h3>" + table(
                ["赛果","十进制赔率","去水概率","模型与去水价差"],
                ([label,f"{o:.2f}",pct(p),f"{100*d:+.2f} 个百分点"] for label,o,p,d in
                 zip(("主胜","平","客胜"),comparison["prices"],comparison["implied_probs"],comparison["probability_gap"]))))
    if "rule_index" in item:
        parts.append(block("规则指数",f"{item['rule_index']['score_100']:.1f} / 100（独立展示，未经命中率校准）"))
    if m.get("research_context"):
        parts.append("<details><summary>名单、新闻及其他背景快照</summary><pre>" +
                     esc(json_text(m["research_context"])) + "</pre></details>")
    return "".join(parts) + "</section>"


def render_html(result):
    style = """*{box-sizing:border-box}body{margin:auto;padding:32px 5vw 60px;max-width:1050px;
font:16px/1.65 system-ui,'Microsoft YaHei',sans-serif;color:#18342f}header,section{border-bottom:1px solid #c3d5cd;
padding:10px 0 24px}header{border-top:4px solid #176450}h1{font-size:2rem}h3{font-size:1.05rem}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}th,td{padding:8px 10px;text-align:left;
border-bottom:1px solid #d6dfdb}th{background:#eef5f1}pre{white-space:pre-wrap;overflow-wrap:anywhere}
@media print{body{max-width:none;padding:0}tr{break-inside:avoid}}"""
    if result.get("kind") == "forecast":
        content = "".join(match_panel(x) for x in result["matches"])
        title = "足球赛前预测"
    elif result.get("kind") == "cup":
        title = "杯赛晋级与夺冠概率"
        teams = result["teams"]
        stages = sorted({k for v in teams.values() for k in v if k.startswith("reach_")},
                        key=lambda s: -int(s.split("_")[-1]))
        content = block("模拟条件",f"{result['sims']} 次模拟 · 随机种子 {result['seed']} · 对阵方式 {result['draw_method']}")
        content += table(["球队", *["进入 "+s.split("_")[-1]+" 强" for s in stages],"夺冠"],
                         ([t,*[pct(vals.get(s,0.)) for s in stages],pct(vals.get("champion",0.))]
                          for t,vals in sorted(teams.items(),key=lambda v:-v[1].get("champion",0.))))
        content += block("赛制假设","；".join(result["assumptions"]))
        if result.get("one_sample_bracket"):
            content += "<h3>一条模拟路径</h3>" + table(["轮次","对阵","晋级球队"],
                ([f"{g['round']} 强",g["home"]+" — "+g["away"],g["advances"]]
                 for g in result["one_sample_bracket"]))
    elif result.get("kind") == "backtest":
        title = "历史赛果滚动回测"
        def metrics(label,m):
            return [label,m["n"],f"{m['log_loss']:.4f}",f"{m['brier']:.4f}",pct(m["top1_accuracy"])]
        rows = [metrics("全部预测",result["metrics"])]
        for timing, pair in result["paired_benchmarks"].items():
            rows += [metrics(timing+" · 本模型",pair["model"]),metrics(timing+" · 赔率基准",pair["market"])]
        dataset = result.get("dataset",{})
        samples = result["forecasts"]
        competitions = sorted({r["competition"] for r in samples if r.get("competition")})
        content = block("回测数据", f"数据源 {dataset.get('source','用户历史')} · 赛事 {', '.join(competitions) or '未标注'} · "
                        f"输入 {dataset.get('rows','未知')} 条 · 各赛事至少 {result['min_train']} 场训练后开始按日预测。")
        if samples:
            dates = [r["date"] for r in samples]
            content += block("评估日期", f"{min(dates)} 至 {max(dates)} · 事后历史重建。")
        content += table(["样本口径","场次","对数损失","Brier（0–2）","胜平负命中率"],rows)
        if not result["paired_benchmarks"]:
            content += block("赔率基准","该批数据未提供可比较的三项赔率。")
        if dataset.get("raw_sha256"):
            content += "<details><summary>核对原始数据</summary><pre>" + esc(json_text(dataset)) + "</pre></details>"
        content += "<h3>头号结果的信心与实际命中</h3>" + table(
            ["区间","场次","平均信心","实际命中"],
            ([f"{b['lower']:.0%}–{b['upper']:.0%}",b["n"],pct(b["mean_confidence"]),pct(b["accuracy"])]
             for b in result["metrics"]["top1_calibration"]))
    else:
        title = {"cup": "赛事模拟", "backtest": "滚动回测", "review": "预测复盘"}.get(result.get("kind"), "足球分析")
        content = "<pre>" + esc(json_text(result)) + "</pre>"
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width, initial-scale=1'><meta http-equiv='Content-Security-Policy' "
            "content=\"default-src 'none'; style-src 'unsafe-inline'\"><title>" + title + "</title><style>" + style +
            "</style></head><body><header><h1>" + title + "</h1></header>" + content + "</body></html>")
