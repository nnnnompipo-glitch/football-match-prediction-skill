# 输入与输出

## 一场比赛

可直接修改 [完整离线样例](../examples/match.json)。单场对象、单场对象数组及含 `records` 的 fixtures 快照均可接受。时间用带 UTC 偏移的 ISO 8601，通常用 Z 结尾。

| 字段 | 用法 |
|---|---|
| home, away, kickoff, as_of | 主队、客队、开球、赛前截点；截点必须早于开球。快照输入可以采用其 observed_at。实时临时输入缺截点时 CLI 采用当前 UTC。 |
| competition, neutral | 赛事和中立场标记；建议历史记录也标明同一赛事。 |
| home_elo, away_elo, elo_at | 成对提供实力评级及观测时间。 |
| home_xg, away_xg, xg_at | 本场双方的期望进球估计，逐侧覆盖从历史估计的均值。球队过往场均 xG 应先结合对手防守与场地，不能直接冒充本场预估。 |
| odds, odds_source, odds_at | 独立参考公司的 90 分钟主／平／客十进制赔率，例如 [2.1,3.4,3.6]。缺时间戳会影响历史可验证性。 |
| target_odds, target_odds_source, target_odds_at | 用于评价最终概率的目标价。不得把同一盘口既作输入又作为独立优势的证明。 |
| evidence | 对象数组，每项含 team, kind, delta_xg, confidence（0–1）, source, observed_at，可带 note、稳定 event_id。后续确认应保留同一事件 ID；没有时间或来源的量化依据需补全。 |
| roles | 对象数组，每项含 role, market（1x2_90）, probs（主／平／客，和为 1）, source, observed_at；可用 weight 定制角色相对权重。 |
| market_weight, role_weight, rho | 参考赔率融合比例、角色合并比例、Dixon–Coles 低比分相关系数。比较不同版本时记录这些值。 |
| rule_inputs | 可选独立规则指数：motivation、odds_trend、form 均为 0–1 的有依据判断；popular、late_season 为可选布尔。该指数单独显示，不改变模型概率。 |
| knockout, decider_home | 单场淘汰赛可打开晋级输出。后者是 90 分钟战平后主队最终晋级的条件概率；缺失时按双方 Elo 估计，无成对评级时各半。 |
| accept_clubelo_date | 对只有日期的旧 ClubElo CSV，完成主客队、UTC 日期的人工核对后可设 true。带完整开球时间的快照按时间精确匹配。 |

## 不同来源怎样对应到同一场

Football-Data.org、The Odds API 和 ClubElo 各自分配 `fixture_id`。保留它们以便追溯，跨源匹配使用主队、客队及开球时间。时间比较会换算至 UTC，例如 `15:00Z` 和 `16:00+01:00` 表示同一时刻。主客颠倒或开球改期时，回到来源重新确认。旧 ClubElo CSV 只提供日期时，需要在比赛对象内显式设置 `accept_clubelo_date`，并人工确认同一主客组合、同一 UTC 日期确实对应这场。

队名经常有缩写。实查 2024/25 英超 OpenFootball 历史中的 20 个显示名，在一次 ClubElo 评级快照里均无完全相同的名称。例如同一支球队在两个来源中分别为 `Arsenal FC` 和 `Arsenal`。使用 `forecast --aliases 文件.json` 提供“来源显示名 → 统一队名”的平面对象，例如 `{"Arsenal FC":"Arsenal"}`。核实赛事、队别和参赛实体后再添加映射。映射适用于比赛输入、历史、评级、赔率及上游预测。示例文件展示已确认的映射，新增联赛或女子、青年、预备队赛事时应逐项核对。[队名映射示例](../examples/aliases.json)

一次真实衔接检查使用了 2024/25 英超 380 场赛果和 2026-11-17 取得的两份 ClubElo 快照。对于 2026-11-21 17:30 UTC 的 Newcastle–Arsenal，`{"Newcastle United FC":"Newcastle","Arsenal FC":"Arsenal"}` 让本地历史样本数从主／客 0／0 变为 38／38；报告同时读到了 1853／2047 的评级以及上游 17.1%／26.3%／56.6% 的胜平负对照。该用例核查数据关联；赛后回测另用有结果的样本。

| 材料 | 命令参数 | 匹配与诊断 |
|---|---|---|
| 已完赛的联赛历史 | `--history history.json` | 比赛主要使用 `date, home, away, home_goals, away_goals`。日期精度只有一天时，从已结束的先前日期取样。openfootball 输出通常无逐行 `competition`，请选相应赛事的文件。查看 `prediction.strength.home_matches` 和 `away_matches`；有历史文件但双方为 0 时，检查队名和日期。 |
| 参考公司的赔率 | `--snapshot odds.json --bookmaker KEY` | 要求同场、同主客、`market=1x2_90`。核对 `sources.quote_history` 内价格、公司、快照采集时间与 `quote_observed_at`。报价更新时间缺失时改用采集时间。 |
| 双方评级 | `--snapshot ratings.json` | 逐队匹配 `team`，两边 Elo 可用后进入模型。查看 `input.home_elo`、`input.away_elo` 和 `sources.snapshots`。 |
| 外部模型 | `--snapshot club.json` 或远端模型快照 | 同场预测进入 `sources.upstream`。当前 ClubElo 页面只提供胜平负，查看 `upstream_probs`。报告中的本地比分来自本地模型的比分矩阵。 |
| 名册、伤停、天气、新闻、交锋 | 每份使用一次 `--context 文件.json` | 先筛到一场，请手动核实资料的对阵、开球、名单及球场。材料写入 `input.research_context`；已确认且能量化影响的情报再以 `evidence` 表达。 |

在 [采集教程](research.md) 完成一场比赛的数据采集后，可用以下 PowerShell 调用。对参考公司采用 `data/odds.json` 的 `bookmaker` 键，对阵采用赛单里的原始显示名称。所有输入取得之后、开球之前记录截点，重复研究时保留这个值和原始快照。

```powershell
$book = Read-Host '实际覆盖此场的 bookmaker 键'
$asOf = [datetime]::UtcNow.ToString('o')
python scripts/football.py forecast data/fixtures.json --home $match.home --away $match.away --as-of $asOf --aliases examples/aliases.json --history data/history.json --snapshot data/odds.json --bookmaker $book --snapshot data/ratings.json --snapshot data/club.json --context data/h2h.json --context data/home-squad.json --context data/injuries.json --context data/weather.json --context data/news.json --out data/prediction.json
```

查看 `matches[0].sources.snapshots` 的 `matched` 和 `status`。普通 `--snapshot` 晚于截点会记录为 `after_cutoff`；晚于截点的主赛单或人工指定的 `--context` 会使预测报错。历史赛果可用于回放；下次才取得的评级、赔率、天气或新闻无法证明当时已经可用。

## 假设重算与市场输出

`--scenarios` 接受带唯一 name 的假设数组。可修改 xG、Elo、rho、中立场、参考赔率及市场／角色权重，追加新证据或替换角色意见。相同赛事事件的较新证据覆盖同一 event_id 旧版本。结果保存完整假设、情景概率和相对基线的百分点变化。多场赛单先用 `--home`／`--away` 选定对阵。示例见 [scenarios.json](../examples/scenarios.json)。

`forecast --total 2.5 --handicap -1 --knockout` 同时给出大／走／小、主队修正 −1 后的三项结果、双方进球、双方零封以及单场晋级。整数总进球线允许走盘，半球线的走盘概率为零。这里只定义三项整数让球；亚洲四分之一球拆注属于另外的结算市场。候选比分 p 来源于完整比分矩阵；前五项通常合计小于 100%。

跨场组合可运行 `python scripts/football.py combo prediction.json picks.json`。每条选择为 `{"home":"…","away":"…","kickoff":"…","outcome":"home"}`，outcome 可取 home、draw、away。仅在不同比赛相互独立的假设下乘出联合概率，并返回对应公平十进制价；同场选择不会被当作相互独立。

默认输出 UTF-8 JSON。单场或整张赛单的 HTML 看板展示模型、参考盘口、目标盘口、情报、情景和数据缺口；任何导入的文本都会转义。输出文件由临时文件原子替换，不能与输入文件同名。
