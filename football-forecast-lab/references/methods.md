# 设计来源与数值口径

这是独立编写的标准库实现。下表说明八个项目的设计怎样落到本 skill 的实际入口。

| 借鉴的项目 | 本地实现 |
|---|---|
| Binance Sports AI Analyzer | 可选 external.py 查询远端基础概率、市场价、新闻及点评。对真实 signal ID 做无持久化情景重算，本地预测可与之并列展示。[上游版本](https://github.com/binance/binance-skills-hub/tree/7d1b1f78d525f9e653b96819f91a549302fda1da/skills/binance-web3/binance-sports-ai-analyzer) |
| Machina Football Data | ClubElo 评级、上游赛前预测和自算历史 Elo 分开处理。保留主客顺序和数据覆盖日期。[上游版本](https://github.com/machina-sports/sports-skills/tree/d9510dfce493ae699beb97c16e2fa743abbbcc2c/skills/football-data) |
| Agentara | 带时间与来源的多角色意见、归一化合并、比赛日看板。可选半场与进球时段估计另列假设。[上游版本](https://github.com/agentara/skills/tree/950e1bfb11e1df67b46df19804ed85ada9012c33/skills/entertainment/world-cup-predictor) |
| AnyCap | 结构化球队名册、球员消歧、证据溯源、冲突及资料缺口处理，支持定性赛前报告。[上游版本](https://github.com/anycap-ai/anycap/tree/a7ff827a4fef902c1874163c4ebb36edad6b9932/skills/anycap-worldcup-predict) |
| Soccer Lottery | 历史交锋、赛程、赔率截图与趋势对照、战意规则指数、让球及跨场组合概率。[上游版本](https://github.com/liming199364/soccer-lottery/tree/f17c71174fbd9fbbfdf02bb6184d72eda560eed7) |
| Dxboy | 以比赛和时间留存多源证据，生成常规赛果、比分排序、市场情景、可打印的赛前报告与赛后评分。[上游版本](https://github.com/Dxboy266/FIFA-WINNER-SKILL/tree/aaca64139dabdc1606d249a7f582619d65571162/skill) |
| JetQiao | 时间衰减的攻防估计、可训练的攻防因子与低比分修正、盘口去水、赛前截点、按日滚动评估和温度校准。[上游版本](https://github.com/JetQiao/football-prediction-skill/tree/23ddaf084d6fc9c2491ee2e8a899eb5a22a79817) |
| ggen0488 | 离线球队与证据快照、Elo 实力先验、胜平负与晋级、已知赛果、带种子的小组及淘汰赛模拟。[上游版本](https://github.com/ggen0488-cyber/worldcup-2026-predictor-skill/tree/3f96e930d65cc6cfbb3f971e1cecfeeb30bd1791/worldcup-2026-predictor) |

默认基础模型半衰期 180 天，主客场进球基准以 20 场等价先验平滑，单队攻防以 6 场量级先验收缩。有显式 xG 时优先使用相应侧的输入；有球队历史时 Elo 的倾斜效应逐渐减小。泊松矩阵的 0–0、0–1、1–0、1–1 四格按 Dixon–Coles 系数调整，默认 rho=−0.06。截断尾部后归一化。可选 fit 通过交替优化带收缩的泊松攻防因子，再用网格估计低比分相关参数；这两种路径分别标识。

伤停等证据逐项限制到 ±0.35 个预期进球并乘以可信度，每队总调整限制到 ±0.65。市场采用十进制赔率的倒数归一化，默认参考市场占 35%。角色意见在此后默认再占 20%，权重可显式设置为零。同一盘口已被市场角色引用时需检查重复计入。采用最终三项概率分别调整比分矩阵的主胜区、平局区和客胜区，保留区内比分的相对比例，所以所有派生市场在同一概率分布上计算。

这些默认值是建模选择。验收测试验证时间边界、数学一致性与工作流；判断是否提升预测表现，应保存真实赛前记录并同独立赔率基准比较。交易、钱包、海报命令模板和占卜不进入本地计算。

可用 `python scripts/football.py elo examples/history.json --competition "Demo League" --as-of 2025-04-01T00:00:00Z --out local-ratings.json` 从历史赛果生成球队 Elo。每队从 1500 开始，K=20，非中立场给主队 60 分主场优势，同一 UTC 日期的比赛统一用当天赛前评级计算更新量。文件区分赛果有效截点与实际制表时间；用于未来比赛时，可通过 `--snapshot local-ratings.json` 关联。单场报告还展示给定历史里两队各自的近五场、进失球和直接交锋。最近出战天数仅依据传入的赛程覆盖，跨赛事休息时间须另行核对。
