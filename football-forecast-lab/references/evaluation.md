# 赛事、训练与复盘

## 杯赛

用 [八队样例](../examples/cup.json) 调整队名和日期。groups 为组名到球队列表，ratings 为队名到 Elo；neutral 默认 true。advance_per_group 控制各组直接出线人数，best_thirds 控制跨组最佳第三名人数。48 队、12 个四队小组时支持 2+8。各组按积分、净胜球、进球数和最终的确定性顺序排位，未完整实现特定赛事的纪律分等细则。

group_results 的每行给 home、away、home_goals、away_goals。knockout_results 另含 round（本轮队数，例如 8）及必要时的 winner；实际平局晋级必须明确给出胜者。已赛记录可附时间，请使用截至快照的事实。bracket 可用 [["A:1","B:2"],["B:1","A:2"]] 等名次槽位或 third:1 等最佳第三占位。若官方公布实际对阵，提供 knockout_field 的球队配对数组。缺少匹配规则时输出会标明简化排种；同一模拟内按相邻胜者晋级。

每场从本 skill 的比分矩阵抽样，打平后的淘汰赛单列晋级决定。输出各轮及夺冠概率、固定种子和一个样本淘汰路径。10,000 次独立模拟对一项约 50% 的频率，其近似 95% **抽样**误差为 ±0.98 个百分点；真实实力、主场、赛程和伤病误差另计。

## 模型拟合与校准

训练数据至少含 date（YYYY-MM-DD）、home、away、home_goals、away_goals，比分用常规时间。可额外记录中立场、赛事、真实开球与赛果可用时间。手工 CSV 先通过采集器转换。用同一赛事的数据执行：

```text
python scripts/football.py fit examples/history.json --competition "Demo League" --as-of 2025-04-01T00:00:00Z --out strength.json
python scripts/football.py forecast examples/match.json --fit strength.json --out fitted-prediction.json
python scripts/football.py backtest examples/history.json --min-train 20 --out rolling.json --html rolling.html
python scripts/calibrate.py rolling.json --out temperature.json
python scripts/football.py forecast examples/statistical-match.json --history examples/history.json --calibration temperature.json --out calibrated.json
```

fit 在给定时点对有资格的比分训练攻防因子，在泊松均值确定后以低比分似然选 rho，带小样本先验。--fit 与手工 xG 互斥。滚动回测走默认历史模型，按日期整批留出，历史赔率只作同场基准。fit 制品及融合模型的准确率不能由默认回测直接推出。

温度校准器只从滚动预测学习。训练与验证按日期分开，对比校准前后的对数损失与 Brier；按样本及验证结果决定是否启用。仅当赛事、模型类型与预测时点匹配时，可将 `--calibration temperature.json` 用于之后的同类预测。对含盘口融合、额外 xG/Elo、角色或伤停调整的预测，不能套用仅从历史基础模型学得的温度。

## 赛前冻结和验后评分

```text
python scripts/football.py forecast examples/match.json --history examples/history.json --ledger forecasts.sqlite --out frozen.json
python scripts/football.py settle forecasts.sqlite examples/results.json
python scripts/football.py review forecasts.sqlite --out review.json
python scripts/football.py archive forecasts.sqlite --home "Harbor XI" --away "Pine XI" --kickoff 2025-04-12T15:00:00Z --as-of 2025-04-11T18:00:00Z --out archived.json
```

SQLite 一并保存冻结时钟、截点、输入、预测及按哈希存放的历史。相同比赛和截点重复登记同一版本是幂等操作，不同内容会拒绝覆盖。赛后比分必须按同一主客顺序和 UTC 开球时刻提交；同分重试幂等，冲突结算保留原记录。评估在每场每组内取最新截点，将真正赛前冻结的样本与开球后才重建的记录分组。回放上述虚构历史样例会落入事后重建组。

概率评价用三分类 Brier（每场三项平方误差之和，范围 0–2）和对数损失；两者越低越好。另看头号方向命中率、比分候选命中和信心分箱。历史基准区分截点当时可得、截点后但赛前、无准确观测时间等口径。报告场数、赛事、时窗及缺失覆盖；没有赔率时只报告模型成绩。

archive 可导出所选对阵的历史输入、核心预测及按内容散列保存的报告版本，内含当次附加的情景、来源、派生市场与时间戳。额外情景的实际保存时间单独记录，不能把赛后追加的分析计入赛前成绩。结算输入可用 FINISHED／FT 标明终场；若比赛打了加时或点球，必须另外确认所提交的是 90 分钟比分。

校准制品同时保存训练窗口、最低训练场数、模型版本和 UTC 日期截点。部署会重现回测的取样条件；低于最低历史场数、赛事不匹配、缺少设置的旧制品，以及给校准预测附加了盘口或伤停的情景，都会报告具体原因。独立目标报价可以保留到真实预测截点。
