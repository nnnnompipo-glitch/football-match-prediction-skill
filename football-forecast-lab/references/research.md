# 采集、核验与研究分工

从 skill 目录运行下列 PowerShell 命令。每个命令生成一份 UTF-8 JSON 快照，包含 `kind`、`source`、`endpoint`、`observed_at`、`raw_sha256`、`records` 和 `warnings`。文件可传给离线预测入口。先用系统的凭据管理工具把 Football-Data.org 密钥设为 `FOOTBALL_DATA_TOKEN`，The Odds API 密钥设为 `THE_ODDS_API_KEY`，API-Football 密钥设为 `API_FOOTBALL_KEY`。历史赛果、ClubElo 的两个入口、天气和新闻可分别免密钥调用。

## 十类数据的采集命令

**赛程**。示例选取英超未来一周。返回空赛单时可调整赛事或日期。`--from` 和 `--to` 须同时提供。这里先挑一场未开球的比赛，保留它的原始队名和 UTC 开球时刻供下文引用。

```powershell
$from = [datetime]::UtcNow.ToString('yyyy-MM-dd')
$to = [datetime]::UtcNow.AddDays(7).ToString('yyyy-MM-dd')
python scripts/sources.py fixtures --competition PL --from $from --to $to --out data/fixtures.json
$fixtures = (Get-Content -Raw -Encoding utf8 data/fixtures.json | ConvertFrom-Json).records
$match = $fixtures | Where-Object { $_.status -in 'SCHEDULED','TIMED' -and [datetimeoffset]$_.kickoff -gt [datetimeoffset]::UtcNow } | Select-Object -First 1
if ($null -eq $match) { throw '这段日期没有可用的未赛场次。请更换日期或赛事。' }
$kickoff = ([datetimeoffset]$match.kickoff).ToUniversalTime().ToString('o')
```

**历史、评级、上游预测、参考赔率**。历史用 openfootball 的赛季和联赛代码。赔率用 The Odds API 自己的赛事代码。ClubElo 最新评级和未赛场次均可整批获取。

```powershell
python scripts/sources.py history --season 2024-25 --league en.1 --out data/history.json
python scripts/sources.py ratings --out data/ratings.json
python scripts/sources.py club-forecast --out data/club.json
python scripts/sources.py odds --sport soccer_epl --regions eu --out data/odds.json
```

**交锋、名册、伤停、天气、新闻**。球队名册示例采集主队；将 `home_id` 换为 `away_id` 可取客队。伤停使用 API-Football 自己的 fixture ID，先在该平台按球队、赛事和 UTC 时间核实。天气输入实际比赛场地的经纬度，包括中立场或临时改场。

```powershell
python scripts/sources.py h2h --fixture-id $match.fixture_id --out data/h2h.json
python scripts/sources.py squad --team-id $match.home_id --out data/home-squad.json
$apiFixture = Read-Host '经核实的 API-Football fixture ID'
python scripts/sources.py injuries --fixture-id $apiFixture --out data/injuries.json
$lat = Read-Host '实际球场纬度，南纬用负数'
$lon = Read-Host '实际球场经度，西经用负数'
python scripts/sources.py weather --lat $lat --lon $lon --kickoff $kickoff --out data/weather.json
$newsQuery = "$($match.home) $($match.away) injury lineup"
python scripts/sources.py news --query $newsQuery --limit 10 --out data/news.json
```

| 输出 | 记录字段 | 如何用于预测 |
|---|---|---|
| fixtures | `fixture_id, home_id, away_id, home, away, kickoff, competition, status, stage, venue, market` | 将文件传给 `forecast` 的第一个参数，用 `--home` 和 `--away` 筛选比赛。 |
| history | `date, home, away, home_goals, away_goals, competition`（若有标识） | 传给 `forecast --history`、`fit` 或 `backtest`。在线英超 `--league en.1` 输出与赛程一致的 `PL`，其他联赛保留原代码。单联赛 CSV 可用 `history --csv local.csv --competition PL` 指定标签。多联赛 CSV 按行保留 `Div`，无标签的单联赛 CSV 可手动指定赛事。完整收盘价另存 `benchmark_odds, odds_horizon, odds_column`。 |
| ratings | `team, elo, country, valid_from, valid_to` | 传给 `--snapshot`。当前公开评级表的日期在 `valid_from`。`ratings --date YYYY-MM-DD` 要求上游确认该日，日期不符会报错。 |
| club-forecast | `home, away, date, kickoff, upstream_probs, top_scores` | 传给 `--snapshot` 作为上游对照。当前页面的胜／平／负按显示精度取值，合计可能与 1 相差 0.001；`top_scores` 为空。旧 `--csv` 档案可能只有日期，并可带逐比分概率。 |
| odds | `home, away, kickoff, fixture_id, bookmaker, odds, market, quote_observed_at` | 传给 `--snapshot`；按公司的 `bookmaker` 键用 `--bookmaker` 选盘。`odds` 依次为主／平／客，小数报价须全部大于 1。保留相同比赛不同时间的文件可对照报价变动。 |
| h2h | `fixture_id, date, kickoff, home, away, home_goals, away_goals, competition` | 用 `--context` 保留双方交锋记录；上游须提供已完赛的常规时间比分。若作为 `--history`，分析样本将局限于两队交锋。 |
| squad | `team, team_id, player, player_id, position, date_of_birth, nationality, shirt_number, team_last_updated` | 用 `--context` 关联当前注册名单。另查比赛日名单、首发和出场状态。 |
| injuries | `fixture_id, kickoff, team, team_id, player, player_id, status, reason` | 用 `--context` 保留报道状态和原因。空列表也可能源自套餐或联赛覆盖。 |
| weather | `hour_utc, latitude, longitude, temperature_2m, precipitation_probability, wind_speed_10m, units` | 用 `--context` 关联开球所在 UTC 整点的预报。以实际返回的 `units` 解读数值。 |
| news | `headline, publisher, published_at, url` | 用 `--context` 保存线索。打开报道核实所述球员、球队和发生时间；`published_at` 是 RSS 给出的报道发布时间。 |

可选的外部体育模型另由 `python scripts/external.py recent --help` 和 `python scripts/external.py predict --help` 提供。先核对平台对阵、状态和时间，再将对应快照传给 `--snapshot` 作上游对照。

## 球员、截图及交叉核验

1. 用赛事、比赛时间和主客两队锁定比赛。遇到同名球员，至少核对俱乐部／国家队、位置和出生日期中的可用标识。把当前效力球队、所属国家队和本场是否入选分别记录。
2. 从俱乐部公告、赛事登记名单、记者原始报道查出场状态。对传闻标记来源、发布时间、获取时间和不确定性。多站转引同一原文时给同一个 event_id。附上冲突信息，未知与确认缺阵分列。搜索到网页标题只能证明报道存在。
3. 用户给赔率截图时，抄录公司、市场（90 分钟／让球／晋级）、主客顺序、十进制报价和截取时间。缺项留空。两次完整报价可制成两个 odds 快照。参考市场用于融合，另一个独立目标价用于对照；历史收盘价单列。
4. 对单场决定性事件列出两种解释，例如“前锋首发／缺阵”。有依据的进球影响放进 scenarios，并标明是分析者假设；不能据伤停人数直接推出固定百分点。

## 多角色与逐场看板

需要并行研判时，可分工给数据、战术、球队新闻和市场研究者，输出统一口径的 `role, market, probs, source, observed_at`。要求各人写出最关键证据、相反证据及来源；由汇总者核对来源重叠，按需要减低相关角色的权重。没有并行代理时照样可以用数值模型，在报告中说明哪些观察由同一位分析者形成。

逐批完成比赛时，把已确认的输入追加到赛单，重跑 `forecast ... --out ... --html ...` 原子替换当地看板；相同冻结记录在账本中保持幂等。无需常驻服务。打不开的网页、验证页或缺失盘口不用于生成“已证实”的消息。
