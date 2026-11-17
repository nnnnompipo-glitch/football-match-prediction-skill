---
name: football-forecast-lab
description: 足球比赛赛前分析、阵容和伤停核验、胜平负与比分预测、赔率对照与情景重算、世界杯及杯赛晋级模拟、滚动回测与赛后复盘。适用于足球和 soccer 的单场、比赛日及整届预测。
---

# 足球赛前研究室

先确认对阵、主客顺序、比赛阶段、开球时间、当地时区和用户关心的市场。默认报告给出常规时间胜平负；在淘汰赛问题中另列晋级概率。脚本路径以本 skill 所在目录为基准，输出放在用户的工作目录。Python 3.10+，计算与报告仅使用标准库。

## 选择入口

- **单场或比赛日。** 将赛单、历史比分及可用评级整理为 [输入规范](references/inputs.md)。用 `python scripts/football.py forecast MATCH.json --history HISTORY.json --out prediction.json --html report.html`。赛单数组可批量计算。若用户要求“现在预测”，取最新赛单、核对比赛状态与数据时间；示例队名只用于演示。
- **查询数据、球员和来源。** 用 `python scripts/sources.py --help` 选择赛程、赔率、评级、名册、伤停、新闻、天气或历史结果。爬取或人工核验流程见 [数据与研究分工](references/research.md)。对姓名、球队别称和时间有歧义的记录先留作待核实。没有凭据时可用公开来源或用户快照，保留缺失项。
- **场景、市场及多方判断。** 把可溯源的证据和角色判断加入比赛输入，或用 `--scenarios SCENARIOS.json` 查看相对于同一基线的变化。对比外部服务、盘口变动或赔率截图时保存原始报价及获取时间。引述规则指数、市场概率和入围比分时，标明各自含义。
- **世界杯或其他杯赛。** 用 `python scripts/football.py cup CUP.json --sims 1000 --seed 7 --out cup.json --html cup.html`。按 [赛事与验证](references/evaluation.md) 提供分组、已赛比分、真实晋级者和淘汰对阵；未提供官方落位时说明模拟采用的赛制。
- **复盘。** 赛前生成报告时加 `--ledger forecast.sqlite` 冻结当时输入和输出。用 `settle` 结算常规时间赛果，`review` 查看表现。历史 CSV／JSON 可以走 `backtest` 做按日期滚动的独立检验。参见 [赛事与验证](references/evaluation.md)。

## 交付预测

把数据日期和统计口径放在结论旁边。给出基础与最终胜平负、候选比分和概率、最重要的证据及来源；如果用了赔率、外部概率或情景，说明它们是生成输入、独立对照还是假设。对于只有定性证据的比赛，可以给出倾向和低／中／高信心，说明哪条未决信息会改变判断。用户要求历史解释时用对应日期的留存快照并区分赛前冻结与事后重建。

需要自行重算比分玩法时，给 forecast 加 `--matrix` 将完整常规时间比分概率矩阵写入 JSON。行号为主队进球数，列号为客队进球数，均从零计数。

询问半场走势时，加 `--timeline` 查看半场胜平负、半场候选比分和每 15 分钟进球概率。该分解假设每个进球在 90 分钟内均匀发生，无法据此识别某队在哪段时间更强。需要本地球队实力榜时，可用 `football.py elo` 根据指定截止日期前的赛果逐日更新 Elo。

## 离线试用

```text
python scripts/football.py forecast examples/match.json --history examples/history.json --scenarios examples/scenarios.json --out prediction.json --html report.html
python scripts/football.py cup examples/cup.json --sims 200 --seed 7 --out cup.json
python scripts/football.py backtest examples/history.json --min-train 12 --out backtest.json
```

三个演示均为虚构数据。模型默认系数和各功能从哪些设计演变而来见 [设计与概率口径](references/methods.md)。
