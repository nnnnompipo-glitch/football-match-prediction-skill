import {api, download, esc as escapeText, pct as percent, displayName, nameMarkup, safeSourceUrl, sourceLink, sourceMarkup} from "./ui.js";
import {mountAnalysis} from "./ai.js";

const toolPages = {
  batch: ["比赛日预测", "编辑一张赛单，统一计算各场常规时间胜平负，并比较跨场组合。"],
  sources: ["数据查询", "按来源获取赛程、球员、赔率及历史资料，也可以导入自己的数据快照。"],
  cup: ["杯赛模拟", "设定分组和晋级规则，通过重复模拟查看各轮晋级与夺冠概率。"],
  elo: ["球队实力", "使用指定截点前的常规时间赛果，计算 Elo 排名或拟合球队攻防参数。"],
  backtest: ["滚动回测", "按 UTC 日期留出比赛，检验历史预测的方向与概率质量。"],
  ledger: ["预测台账", "查看已冻结的预测，录入常规时间赛果并按冻结时点复盘。"]
};
const views = new Map();
let exampleRequest;

const decimal = (v, places = 3) => typeof v === "number" ? v.toFixed(places) : "—";
const json = (v) => JSON.stringify(v, null, 2);
const checked = (root, name) => Boolean(root.querySelector(`[name="${name}"]`)?.checked);
const val = (root, name) => root.querySelector(`[name="${name}"]`)?.value?.trim() || "";
const dateInput = (stamp) => new Date(stamp).toISOString().slice(0,16);
const utc = (value) => value ? new Date(`${value}Z`).toISOString() : undefined;
const list = (data) => Array.isArray(data) ? data : data?.records ?? data?.matches ?? [];
const card = (title, html) => `<section class="tool-card"><h2>${escapeText(title)}</h2>${html}</section>`;
const field = (title, control) => `<label class="tool-field">${escapeText(title)}${control}</label>`;
const input = (title, name, value = "", type = "text", extra = "") => field(title, `<input name="${name}" type="${type}" value="${escapeText(value)}" ${extra}>`);
const select = (title, name, options) => field(title, `<select name="${name}">${Object.entries(options).map(([k,v]) => `<option value="${escapeText(k)}">${escapeText(v)}</option>`).join("")}</select>`);
const check = (title, name, enabled = false) => `<label class="tool-check"><input name="${name}" type="checkbox"${enabled ? " checked" : ""}>${escapeText(title)}</label>`;
const submit = (title) => `<div class="tool-actions"><button class="tool-run" type="submit">${escapeText(title)}</button></div><p class="tool-status" role="status"></p>`;
const block = (title, content) => `<details><summary>${escapeText(title)}</summary>${content}</details>`;
const note = (text) => `<p class="tool-hint">${escapeText(text)}</p>`;
const metric = (label, value) => `<div class="tool-metric"><span>${escapeText(label)}</span><strong>${escapeText(value)}</strong></div>`;
const bars = (value) => `<span class="tool-bars"><i><b style="width:${Math.max(0, Math.min((Number(value) || 0) * 100, 100))}%"></b></i>${percent(value)}</span>`;
const table = (headers, rows) => `<div class="tool-tablewrap"><table><thead><tr>${headers.map(h => `<th scope="col">${escapeText(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
const fileButton = (target, label, accept) => `<label class="tool-file">${escapeText(label)}<input type="file" data-file="${target}" accept="${accept}"></label>`;
function jsonBox(name, title, value, hint = "", accept = ".json,application/json") {
  return `<div class="tool-json">${field(title, `<textarea spellcheck="false" name="${name}" rows="6">${value == null ? "" : escapeText(typeof value === "string" ? value : json(value))}</textarea>`)}${fileButton(name,"导入文件",accept)} ${hint ? note(hint) : ""}</div>`;
}
function parseValue(root, name, title, fallback = undefined) {
  const raw = val(root, name);
  if (!raw) return fallback;
  try { return JSON.parse(raw); } catch { throw Error(`「${title}」的 JSON 格式有误，请检查逗号、引号和括号。`); }
}
async function examples() {
  if (!exampleRequest) exampleRequest = api("examples").catch(e => { exampleRequest = undefined; throw e; });
  return exampleRequest;
}
function message(root, text, isError = false) {
  const p = root.querySelector(".tool-status");
  if (p) { p.textContent = text; p.classList.toggle("error", isError); }
}
function bindSubmit(form, callback) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    if (btn.disabled) return;
    btn.disabled = true;
    message(form,"正在处理…");
    try { await callback(); message(form,"已完成"); }
    catch (err) { message(form, err.message || "处理失败，请检查输入后重试。", true); }
    finally { btn.disabled = false; }
  });
}
function exportsFor(container, data, name, htmlReport = true) {
  const section = document.createElement("div");
  section.innerHTML = `<div class="tool-actions"><button type="button" data-export="json">导出 JSON</button>${htmlReport ? '<button type="button" data-export="html">导出 HTML 报告</button>' : ""}</div><p class="tool-status" role="status"></p>${block("查看完整输出", `<pre>${escapeText(json(data))}</pre>`)}`;
  container.append(section);
  section.querySelector('[data-export="json"]').onclick = () => download(json(data), `${name}.json`, "application/json");
  const htmlButton = section.querySelector('[data-export="html"]');
  if (htmlButton) htmlButton.onclick = async () => {
    htmlButton.disabled = true;
    try { const result = await api("report", {result:data}); download(result.html,`${name}.html`,"text/html"); }
    catch (e) { message(section,e.message,true); }
    finally { htmlButton.disabled = false; }
  };
}
function output(root, title, body, data, name, htmlReport = true) {
  const slot = root.querySelector("[data-output]");
  slot.innerHTML = card(title,body);
  const target = slot.firstElementChild;
  exportsFor(target, data, name, htmlReport);
  const aiPanel = document.createElement("details");
  aiPanel.innerHTML = "<summary>用 AI 解读此结果</summary><div></div>";
  target.append(aiPanel);
  aiPanel.addEventListener("toggle", () => {
    if (aiPanel.open && !aiPanel.querySelector("form")) {
      mountAnalysis(aiPanel.querySelector("div"), data, title);
    }
  });
  return target;
}
function historyBox(history) {
  return block("查看或替换历史赛果", jsonBox("history","常规时间历史比分",history,"可以导入技能 JSON 快照或 Date,HomeTeam,AwayTeam,FTHG,FTAG 格式的 CSV。",".json,.csv"));
}
async function historical(root, competition) {
  const raw = val(root,"history");
  if (!raw) throw Error("请提供历史赛果。");
  if (/^[{[]/.test(raw)) return parseValue(root,"history","历史赛果");
  return api("sources",{kind:"history",csv:raw,...(competition ? {competition} : {})});
}
function installFileImports(root) {
  root.addEventListener("change",async event => {
    const fileInput = event.target.closest("input[data-file]");
    if (!fileInput || !fileInput.files.length) return;
    try {
      const data = (await fileInput.files[0].text()).replace(/^\uFEFF/,"");
      const area = root.querySelector(`[name="${fileInput.dataset.file}"]`);
      area.value = data;
      area.dispatchEvent(new Event("input",{bubbles:true}));
      message(fileInput.closest("form") || root,`已导入 ${fileInput.files[0].name}`);
    } catch(e) { message(fileInput.closest("form") || root, e.message, true); }
    fileInput.value = "";
  });
}
function demoBatch(sample) {
  const m = sample.match;
  return [[m.home,m.away],["Lake XI","Vale XI"],["Stone XI","Hill XI"]].map(([home,away],i) => ({
    home, away, competition:m.competition, kickoff:new Date(Date.parse(m.kickoff)+i*5400000).toISOString(),as_of:m.as_of
  }));
}
function renderBatch(root, sample) {
  const demo = demoBatch(sample);
  root.innerHTML = card("赛单编辑", `<form>${note("已载入虚构演示赛单。开球时间与预测截点均为 UTC。")}<div class="tool-flex">${input("赛事","competition",sample.match.competition)}${input("统一预测截点 · UTC","as_of",dateInput(sample.match.as_of),"datetime-local","required")}</div><div data-matches></div><div class="tool-actions"><button type="button" data-add>＋ 添加比赛</button></div>${block("使用完整 JSON 赛单", note("填写后使用这里的完整赛单，保留各场的原始字段。清空后使用上方表格。")+jsonBox("fixtures","赛单 JSON", null))}${historyBox(sample.history)}<div class="tool-choices">${check("使用历史赛果","use_history",true)}${check("比分矩阵","matrix")}${check("半场与时间线","timeline")}${check("淘汰赛晋级","knockout")}${check("冻结到台账","ledger")}</div>${submit("运行比赛日预测")}</form>`) + '<div data-output></div>';
  const form = root.querySelector("form");
  const rows = form.querySelector("[data-matches]");
  rows.insertAdjacentHTML("beforebegin", `<div class="tool-choices">${check("将表格赛单标记为虚构演示", "demo_table", true)}</div>`);
  const append = (item = {}) => {
    const div = document.createElement("div"); div.className = "tool-fixture";
    div.innerHTML = input("主队","home",item.home) + input("客队","away",item.away) +
      input("开球时间 · UTC","kickoff",item.kickoff ? dateInput(item.kickoff) : dateInput(sample.match.kickoff),"datetime-local") + '<button type="button" class="tool-del">移除</button>';
    div.querySelector("button").onclick = () => div.remove(); rows.append(div);
  };
  demo.forEach(append); form.querySelector("[data-add]").onclick = () => append();
  bindSubmit(form,async () => {
    const competition = val(form,"competition"), as_of = utc(val(form,"as_of"));
    const manual = parseValue(form,"fixtures","赛单 JSON");
    const manualTable = [...rows.children].map(div => ({
      home:val(div,"home"), away:val(div,"away"), kickoff:utc(val(div,"kickoff")), competition, as_of,
      demo:checked(form,"demo_table")
    }));
    const fixtures = manual ?? manualTable;
    if (!list(fixtures).length && !fixtures?.home) throw Error("请至少添加一场比赛。");
    const args = {input:fixtures,matrix:checked(form,"matrix"),timeline:checked(form,"timeline"),knockout:checked(form,"knockout"),ledger:checked(form,"ledger")};
    if (checked(form,"use_history")) args.history = await historical(form,competition);
    const report = await api("forecast",args);
    const matches = report.matches;
    const matchRows = matches.map((m,i) => [nameMarkup(m.input,"home"),nameMarkup(m.input,"away"),escapeText(m.input.as_of),m.input.demo === true ? "虚构演示" : "自备赛单",...m.prediction.probs.map(percent),
      `<label><span hidden>第 ${i+1} 场组合方向</span><select data-pick="${i}"><option value="">跳过</option><option value="home">主胜</option><option value="draw">平局</option><option value="away">客胜</option></select></label>`,`${sourceMarkup(m,{compact:true})}<button type="button" data-simulate="${i}">播放模拟</button>`]);
    const container = output(root,`比赛日结果 · ${matches.length} 场`,table(["主队","客队","预测截点","数据性质","主胜","平局","客胜","跨场组合","比赛动画"],matchRows)+`<form class="tool-sub">${note("选择各场方向后，可按不同比赛相互独立的假设计算组合概率。")}${submit("计算组合概率")}<div data-joint aria-live="polite"></div></form>`,report,"matchday");
    container.querySelectorAll('[data-simulate]').forEach(button=>button.onclick=()=>{
      const match=matches[Number(button.dataset.simulate)];
      window.dispatchEvent(new CustomEvent('studio-open-forecast',{detail:{result:{...report,matches:[match]},flags:{history:!!args.history,matrix:args.matrix,timeline:args.timeline,knockout:args.knockout,ledger:args.ledger,simulation:true},route:'simulation'}}));
    });
    const combination = container.querySelector("form");
    bindSubmit(combination,async () => {
      const picks = [...container.querySelectorAll("[data-pick]")].filter(el=>el.value).map(el=>{
        const {home,away,kickoff}=matches[Number(el.dataset.pick)].input; return {home,away,kickoff,outcome:el.value};
      });
      if (!picks.length) throw Error("请先选择至少一场比赛的方向。");
      const combo = await api("combo",{forecasts:report,picks});
      const slot = combination.querySelector("[data-joint]");
      slot.innerHTML = `<div class="tool-metrics">${metric("已选比赛",picks.length)}${metric("联合概率",percent(combo.joint_probability))}${metric("独立假设公平赔率",decimal(combo.fair_decimal_under_independence,2))}</div>`;
      exportsFor(slot,combo,"combination");
    });
  });
}
function renderCup(root,sample) {
  const spec = sample.cup;
  const advanced = {...spec};
  for (const key of ["groups","as_of","best_thirds","advance_per_group","neutral","ratings","demo"]) delete advanced[key];
  root.innerHTML = card("赛事配置",`<form>${note("已载入八队虚构样例。每组队名用逗号或顿号分隔。")}<div data-groups></div><button type="button" data-add>＋ 添加小组</button><div class="tool-flex">${input("每组直接出线","advance",spec.advance_per_group,"number",'min="1" required')}${input("最佳第三名数量","thirds",spec.best_thirds,"number",'min="0" required')}${input("模拟次数","sims",500,"number",'min="1" required')}${input("随机种子","seed",7,"number","required")}${input("资料截点 · UTC","as_of",dateInput(spec.as_of),"datetime-local","required")}</div><div class="tool-choices">${check("中立场","neutral",spec.neutral!==false)}${check("使用球队 Elo","use_ratings",true)}${check("使用已赛结果及预设对阵","use_draw",true)}</div>${block("球队 Elo",jsonBox("ratings","队名与 Elo 映射",spec.ratings))}${block("已赛比分、淘汰赛和对阵规则",jsonBox("draw","高级赛制 JSON",advanced,"可填写 group_results、knockout_results、bracket 或 knockout_field；球队名要与上方一致。"))}${block("导入完整杯赛配置",jsonBox("spec","杯赛配置 JSON",null,"填写后使用完整配置，可直接导入原 skill 的杯赛文件。模拟次数和随机种子沿用上方数值。"))}${submit("开始杯赛模拟")}</form>`) + '<div data-output></div>';
  const form = root.querySelector("form"), groups = root.querySelector("[data-groups]");
  const add = (group="",teams=[]) => {
    const el=document.createElement("div"); el.className="tool-group-line";
    el.innerHTML=input("组名","group",group)+input("参赛球队","teams",teams.join("、"))+'<button type="button" class="tool-del">移除</button>';
    el.querySelector("button").onclick=()=>el.remove();groups.append(el);
  };
  Object.entries(spec.groups).forEach(([g,t])=>add(g,t));
  form.querySelector("[data-add]").onclick=()=>add();
  bindSubmit(form,async()=>{
    let config=parseValue(form,"spec","完整杯赛配置");
    if (!config) {
      const entries = [...groups.children].map(row=>[val(row,"group"), val(row,"teams").split(/[,，、\n]/).map(s=>s.trim()).filter(Boolean)]);
      if (!entries.length || entries.some(([g,t])=>!g||t.length<2)) throw Error("每组需要一个组名和至少两支球队。");
      if (new Set(entries.map(([g])=>g)).size!==entries.length) throw Error("组名不能重复。");
      config={...(checked(form,"use_draw")?parseValue(form,"draw","高级赛制",{}):{}),groups:Object.fromEntries(entries),as_of:utc(val(form,"as_of")),advance_per_group:Number(val(form,"advance")),best_thirds:Number(val(form,"thirds")),neutral:checked(form,"neutral")};
      if(checked(form,"use_ratings")) config.ratings=parseValue(form,"ratings","球队 Elo",{});
    }
    const report=await api("cup",{input:config,sims:Number(val(form,"sims")),seed:Number(val(form,"seed"))});
    const teams=Object.entries(report.teams).sort((a,b)=>(b[1].champion||0)-(a[1].champion||0));
    const stages=[...new Set(teams.flatMap(([,ps])=>Object.keys(ps).filter(k=>k.startsWith("reach_"))))].sort((a,b)=>Number(b.slice(6))-Number(a.slice(6)));
    const drawLabel={"supplied actual knockout field":"采用指定的真实淘汰赛对阵","supplied rank-slot bracket":"采用预设小组名次对阵","simplified performance seeding":"按小组表现简化排种"};
    const teamsTable=table(["球队",...stages.map(k=>k==="reach_2"?"进决赛":`进 ${k.slice(6)} 强`),"夺冠"],teams.map(([t,p])=>[escapeText(t),...stages.map(k=>percent(p[k]||0)),bars(p.champion||0)]));
    const bracket=table(["轮次","主队","客队","晋级"],report.one_sample_bracket.map(m=>[m.round===2?"决赛":`${m.round} 强`,...["home","away","advances"].map(k=>nameMarkup(m,k))]));
    output(root,"模拟结果",note(drawLabel[report.draw_method]||report.draw_method)+`<div class="tool-metrics">${metric("模拟次数",report.sims)}${metric("淘汰赛席位",report.qualified_teams)}${metric("已计入的小组赛果",report.group_results_locked)}</div>${teamsTable}${block("查看一次模拟的淘汰赛路径",bracket)}`,report,"cup");
  });
}
const catalogs = {
  fixtures:["赛程与比赛状态","Football-Data.org · 服务端环境变量 FOOTBALL_DATA_TOKEN",[
    ["competition","赛事代码","PL"],["date_from","起始日期","","date"],["date_to","截止日期","","date"]]],
  h2h:["历史交锋","Football-Data.org · 服务端环境变量 FOOTBALL_DATA_TOKEN",[["fixture_id","Football-Data 比赛 ID","","text","required"]]],
  odds:["即时赔率","The Odds API · 服务端环境变量 THE_ODDS_API_KEY",[["sport","赛事代码","soccer_epl"],["regions","报价地区","eu"],["bookmaker","博彩公司标识（可选）",""]]],
  ratings:["球队 Elo 评级","ClubElo · 可公开查询或导入 CSV",[["team","俱乐部名称（可选）",""],["date","评级日期","","date"]]],
  "club-forecast":["俱乐部外部预测","ClubElo · 可公开查询或导入 CSV",[["team","俱乐部名称（可选）",""]]],
  squad:["球员名册","Football-Data.org · 服务端环境变量 FOOTBALL_DATA_TOKEN",[["team_id","Football-Data 球队 ID","","text","required"]]],
  injuries:["球员伤停","API-Football · 服务端环境变量 API_FOOTBALL_KEY",[["fixture_id","API-Football 比赛 ID","","text","required"]]],
  news:["球队新闻","Google News RSS · 公开来源",[["query","关键词","","text","required"],["limit","最多条数",15,"number",'min="1" max="100" required']]],
  weather:["开球天气","Open-Meteo · 公开来源",[["lat","纬度",51.55,"number",'step="any" min="-90" max="90" required'],["lon","经度",-0.108,"number",'step="any" min="-180" max="180" required'],["kickoff","开球时间 · UTC","","datetime-local","required"]]],
  history:["历史赛果","openfootball · 可公开查询或导入 CSV",[["season","赛季","2024-25"],["league","联赛代码","en.1"],["competition","本地 CSV 赛事名称（可选）",""]]],
  "external-recent":["外部待赛清单","Binance Sports · 公开赛事源",[["limit","最多条数",25,"number",'min="1" max="1000" required']]],
  "external-resolve":["外部比赛识别","Binance Sports · 按赛事 slug 核对对阵、时刻和状态",[["slugs","赛事 slug（多个用逗号分隔）","","text","required"]]],
  "external-predict":["外部模型与信号重算","Binance Sports · 仅限已确认开球时间的未赛场次",[["slug","赛事 slug","","text","required"]]]
};
const recordLabels = {fixture_id:"比赛 ID",slug:"赛事 slug",home:"主队",away:"客队",team:"球队",elo:"Elo",games:"场次",player:"球员",position:"位置",reason:"原因",status:"状态",probs:"胜平负概率",upstream_probs:"外部胜平负",odds:"胜平负赔率",bookmaker:"博彩公司",date:"日期",kickoff:"开球时间",competition:"赛事",country:"国家",title:"标题",published_at:"发布时间",published:"发布时间",source:"来源",home_goals:"主队进球",away_goals:"客队进球",time_utc:"时间 · UTC",time:"时间",temperature_2m:"气温",precipitation:"降水量",wind_speed_10m:"风速",nationality:"国籍",valid_from:"有效起始",valid_to:"有效截止",url:"链接"};
const prematch = new Set(["SCHEDULED","TIMED","NS","NOT_STARTED","UPCOMING","PRE_MATCH","PREMATCH"]);
const contextKinds = new Set(["squad","injuries","news","weather"]);
const dateWithZone = s => typeof s==="string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(s) && Number.isFinite(Date.parse(s));
function fixtureCanOpen(row, observed) {
  const status=String(row.status || "").trim().replace(/[- ]/g,"_").toUpperCase();
  return row.home && row.away && row.home!==row.away && (!status || prematch.has(status)) &&
    row.home_goals==null && row.away_goals==null && dateWithZone(row.kickoff) &&
    Date.parse(observed)<Date.parse(row.kickoff);
}
function connectSource(result, rows) {
  const fixture = result.kind==="fixtures", context = contextKinds.has(result.kind);
  const stamped = dateWithZone(result.observed_at);
  const type = ["history","h2h"].includes(result.kind) ? "history" :
    ["ratings","odds","club-forecast","external"].includes(result.kind) ? "snapshot" : "";
  const fire = detail => window.dispatchEvent(new CustomEvent("studio-use-data",{detail}));
  const action = (row,i) => {
    if (fixture) return fixtureCanOpen(row,result.observed_at) ? `<button type="button" data-send="${i}">分析此场</button>` : "—";
    return `<button type="button" data-send="${i}">确认此条属于当前对阵并使用</button>`;
  };
  const rowActions = stamped && (fixture || context) ? action : null;
  const useAll = stamped && type && rows.length ? '<div class="tool-actions"><button type="button" data-use-snapshot>用于当前对阵</button></div>' : "";
  let hint = "";
  if (rows.length && (fixture || context || type) && !stamped) hint = "快照缺少带时区的采集时间，请补充来源记录的 observed_at 后再用于预测。";
  if (stamped && context) hint = "请按球队、球员、比赛地点与开球时间核对。点击确认会将选中这条资料作为比赛背景。";
  return {
    rowActions, footer:(hint?note(hint):"")+useAll,
    bind(container) {
      const apply = container.querySelector("[data-use-snapshot]");
      if (apply) apply.onclick=()=>fire({type,data:result});
      container.querySelectorAll("[data-send]").forEach(button=>{
        button.onclick=()=>{
          const index=Number(button.dataset.send), input=rows[index];
          if (fixture) fire({type:"fixture",input,observed_at:result.observed_at});
          else {
            const data=rows.length===1 ? result : {...result, records:[input], selected_record_indexes:[index]};
            if (data!==result && Array.isArray(data.matches)) delete data.matches;
            fire({type:"context",data});
          }
        };
      });
    }
  };
}
function recordTable(records, rowAction = null) {
  if (!records.length) return note("没有符合条件的记录。");
  const keys = Object.keys(records[0]).filter(k=>!k.endsWith("_zh")&&!["translation","provenance"].includes(k));
  const labels = {...recordLabels, headline:"标题", publisher:"发布者", hour_utc:"时刻 · UTC", latitude:"纬度", longitude:"经度", cloud_cover:"云量", visibility:"能见度"};
  const priority = ["home","away","headline","team","player","date","kickoff","hour_utc","temperature_2m","precipitation","wind_speed_10m","home_goals","away_goals","elo","odds","upstream_probs","probs","reason","published_at","url"];
  const shown = [...new Set([...priority.filter(k=>keys.includes(k)),...keys.filter(k=>labels[k]),...keys])].slice(0,8);
  const headers=shown.map(k=>labels[k]||k);
  const withSources=records.some(r=>r.provenance||r.source_url||r.source_endpoint);
  if(withSources)headers.push("原始来源");
  if (rowAction) headers.unshift("操作");
  const preview=rowAction?records:records.slice(0,100);
  const rows=preview.map((r,i)=>{
    const cells=shown.map(k=>{
    const v=r[k];
    if (["home","away","competition","team","stage"].includes(k))return nameMarkup(r,k);
    if (["url","source_url","source_endpoint","endpoint"].includes(k) && safeSourceUrl(v))return sourceLink(v,k==="source_endpoint"||k==="endpoint"?"原始数据接口":"打开原网页");
    if (Array.isArray(v) && ["probs","upstream_probs","market_probs"].includes(k)) return v.map(percent).join(" / ");
    if (typeof v === "number" && r.units?.[k]) return escapeText(`${v} ${r.units[k]}`);
    return escapeText(v==null?"—":typeof v==="object"?JSON.stringify(v):v);
    });
    if(withSources)cells.push(sourceMarkup(r,{compact:true}));
    if (rowAction) cells.unshift(rowAction(r,i));
    return cells;
  });
  return table(headers,rows) + (preview.length<records.length?note(`预览前 100 条，可导出全部 ${records.length} 条。`):"");
}
function showSource(root,result) {
  const rows=list(result);
  if (!Array.isArray(rows) || rows.some(r=>!r||Array.isArray(r)||typeof r!=="object")) throw Error("快照需要由记录对象组成。");
  const description = [result.source, result.observed_at && `采集于 ${result.observed_at}`].filter(Boolean).join(" · ");
  const warnings = Array.isArray(result.warnings)?result.warnings:[];
  const connection=connectSource(result,rows);
  const target=output(root,`来源记录 · ${rows.length} 条`,(description?note(description):"")+sourceMarkup(result)+recordTable(rows,connection.rowActions)+connection.footer+(warnings.length?block("来源说明",note(warnings.join(" "))) : ""),result,"source-snapshot",false);
  connection.bind(target);
}
function renderSources(root) {
  root.innerHTML = card("数据来源",`<form>${select("查询项目","kind",Object.fromEntries(Object.entries(catalogs).map(([k,d])=>[k,d[0]])))}<div data-params></div>${submit("查询并生成快照")}</form>`)+card("打开已有快照",`<form>${jsonBox("snapshot","本地记录或快照 JSON",null)}${submit("读取本地快照")}</form>`)+'<div data-output></div>';
  const [form,local] = root.querySelectorAll("form");
  const kindSelect = form.elements.kind;
  const adapt = () => {
    const kind = kindSelect.value, [,source,fields] = catalogs[kind];
    const hasCSV = ["history","ratings","club-forecast"].includes(kind);
    const demoCSV = kind === "history" ? "Date,HomeTeam,AwayTeam,FTHG,FTAG\n01/03/2025,Harbor XI,Pine XI,2,1" : kind === "ratings" ? "Club,Elo,Country,From,To\nHarbor XI,1550,ENG,2025-03-01,2025-03-31" : "";
    form.querySelector("[data-params]").innerHTML = `<div class="tool-source-note">${escapeText(source)}</div><div class="tool-flex">${fields.map(([key,title,value,type,attr])=>input(title,key,value,type,attr)).join("")}</div>` +
      (hasCSV?block("改用本地 CSV 来源",jsonBox("csv","原始 CSV 内容",null,"填写后直接从这份文件生成快照。",".csv,text/csv")+(demoCSV?'<button type="button" data-csv-demo>填入虚构 CSV 示例</button>':"")):"")+
      (kind==="external-predict"?`<div class="tool-choices">${check("附带新闻和分析背景","context")}</div>${block("信号情景重算",jsonBox("signals","已验证的信号调整 JSON",null,"根据该赛事基线返回的信号，填写包含 signals 数组的对象。"))}`:"");
    const csvButton = form.querySelector("[data-csv-demo]");
    if (csvButton) csvButton.onclick=()=>{form.elements.csv.value=demoCSV;};
    message(form,"");
  };
  kindSelect.value = "history"; adapt(); kindSelect.onchange=adapt;
  bindSubmit(form,async()=>{
    const kind = val(form,"kind"), fields = catalogs[kind][2], args={};
    fields.forEach(([k,, ,type])=>{
      const value = val(form,k);
      if (value==="") return;
      args[k] = type==="number"?Number(value):type==="datetime-local"?utc(value):k==="slugs"?value.split(/[\s,，]+/).filter(Boolean):value;
    });
    if (val(form,"csv")) args.csv=val(form,"csv");
    let result;
    if (kind.startsWith("external-")) {
      const action=kind.slice(9);
      if (action==="predict") {
        args.context=checked(form,"context");
        const edits=parseValue(form,"signals","信号调整");
        if (edits !== undefined) {
          args.signals=Array.isArray(edits)?edits:edits?.signals;
          if (!Array.isArray(args.signals) || !args.signals.length) throw Error("信号调整需要非空的 signals 数组。");
        }
      }
      result=await api("external",{action,...args});
    } else result=await api("sources",{kind,...args});
    showSource(root,result);
  });
  bindSubmit(local,async()=>{
    const data=parseValue(local,"snapshot","本地快照");
    if (!data || (!Array.isArray(data) && !Array.isArray(data.records) && !Array.isArray(data.matches))) throw Error("请导入记录数组，或包含 records / matches 的快照。");
    showSource(root,data);
  });
}
function fitForm(root, sample) {
  root.innerHTML = card("计算参数",`<form>${select("计算方式","method",{elo:"逐日 Elo 评级",fit:"拟合攻防与低比分参数"})}<div class="tool-flex">${input("赛事名称","competition",sample.match.competition)}${input("资料截点 · UTC","as_of",dateInput(sample.match.as_of),"datetime-local","required")}</div>${note(`已载入 ${list(sample.history).length} 场虚构历史赛果。`)}${historyBox(sample.history)}${submit("计算球队实力")}</form>`)+'<div data-output></div>';
  const form=root.querySelector("form");
  bindSubmit(form,async()=>{
    const method=val(form,"method"), competition=val(form,"competition");
    const report=await api(method,{history:await historical(form,competition),as_of:utc(val(form,"as_of")),...(competition?{competition}:{})});
    if (method==="elo") {
      output(root,"球队 Elo 排名",`<div class="tool-metrics">${metric("参赛球队",report.records.length)}${metric("纳入赛果",report.matches)}${metric("初始分",report.initial_rating)}</div>`+table(["排名","球队","Elo","比赛场次"],report.records.map((r,i)=>[i+1,escapeText(r.team),decimal(r.elo,1),escapeText(r.games)])),report,"elo");
    } else {
      const teams = Object.entries(report.teams).sort((a,b)=>b[1].attack-a[1].attack);
      output(root,"攻防拟合结果",`<div class="tool-metrics">${metric("历史场次",report.matches)}${metric("主队进球均值",decimal(report.home_mean))}${metric("客队进球均值",decimal(report.away_mean))}${metric("低比分修正 ρ",decimal(report.rho,2))}</div>`+table(["球队","进攻系数","失球系数"],teams.map(([t,p])=>[escapeText(t),decimal(p.attack),decimal(p.concession)])),report,"strength");
    }
  });
}
function calibration(root, report) {
  const slot=document.createElement("section");slot.className="tool-card";
  slot.innerHTML=`<h2>概率校准</h2><form>${note("用较早日期拟合温度，再用较晚日期验证是否启用。可替换为其他滚动回测报告。")}${block("替换回测报告",jsonBox("backtest","回测报告 JSON",null))}<div class="tool-flex">${input("最少拟合场次","min_fit",20,"number",'min="2" required')}${input("最少验证场次","min_validation",10,"number",'min="2" required')}${input("拟合样本比例","fraction",0.7,"number",'min="0.01" max="0.99" step="0.01" required')}${input("限定赛事（可选）","competition","")}</div>${submit("计算温度校准")}</form><div data-calibration></div>`;
  root.append(slot);
  const form=slot.querySelector("form");
  bindSubmit(form,async()=>{
    const supplied=parseValue(form,"backtest","回测报告",report);
    if (!supplied) throw Error("请先运行回测，或导入已有回测报告。");
    const obj=await api("calibrate",{backtest:supplied,min_fit:Number(val(form,"min_fit")),min_validation:Number(val(form,"min_validation")),fit_fraction:Number(val(form,"fraction")),competition:val(form,"competition")||undefined});
    const out=slot.querySelector("[data-calibration]");
    out.innerHTML=`<div class="tool-metrics">${metric("校准决策",obj.enabled?"已启用":"保留原概率")}${metric("应用温度",decimal(obj.temperature))}${metric("验证至",obj.validated_until)}</div>`+
      table(["验证样本","场数","对数损失","Brier"],[["原始概率",obj.holdout.identity],["候选温度",obj.holdout.candidate]].map(([label,m])=>[label,m.n,decimal(m.log_loss),decimal(m.brier)]));
    exportsFor(out,obj,"calibration",false);
  });
}
function renderBacktest(root,sample) {
  root.innerHTML=card("滚动验证设置",`<form>${note(`已载入 ${list(sample.history).length} 场虚构历史赛果。每个预测日仅使用此前已可获得的赛果。`)}<div class="tool-flex">${input("最少训练场次","min_train",12,"number",'min="1" required')}${input("滚动窗口场次（留空使用全部）","window","","number",'min="1"')}${input("本地 CSV 赛事名称（可选）","competition","")}</div>${historyBox(sample.history)}${submit("运行滚动回测")}</form>`)+'<div data-output></div><div data-cal></div>';
  const form=root.querySelector("form"), calSlot=root.querySelector("[data-cal]");
  calibration(calSlot,null);
  bindSubmit(form,async()=>{
    const report=await api("backtest",{history:await historical(form,val(form,"competition")),min_train:Number(val(form,"min_train")),window:val(form,"window")?Number(val(form,"window")):undefined});
    const metrics=report.metrics, bins=metrics.top1_calibration||[];
    const benchmarkRows=Object.entries(report.paired_benchmarks||{}).map(([scope,p])=>[escapeText(scope),p.model.n,decimal(p.model.log_loss),decimal(p.market.log_loss),decimal(p.model.brier),decimal(p.market.brier)]);
    const forecastRows=report.forecasts.map(r=>[escapeText(r.date),nameMarkup(r,"home"),nameMarkup(r,"away"),...r.probs.map(percent),{H:"主胜",D:"平局",A:"客胜"}[r.actual]]);
    output(root,"回测结果",`<div class="tool-metrics">${metric("验证场次",report.n)}${metric("方向命中率",percent(metrics.top1_accuracy))}${metric("对数损失",decimal(metrics.log_loss))}${metric("Brier 分数",decimal(metrics.brier))}</div>${note("对数损失与 Brier 分数越低越好。三项胜平负的 Brier 范围为 0–2。")}<h3>信心分箱</h3>`+
      table(["预测信心区间","场数","平均信心","实际命中率"],bins.map(b=>[`${percent(b.lower)}–${percent(b.upper)}`,b.n,percent(b.mean_confidence),bars(b.accuracy)]))+
      block("同场赔率基准",benchmarkRows.length?table(["报价时点","场数","模型损失","盘口损失","模型 Brier","盘口 Brier"],benchmarkRows):note("本次历史中没有可比较的同场赔率。"))+
      block("逐场验证记录",table(["日期","主队","客队","主胜","平局","客胜","实际方向"],forecastRows)),report,"backtest");
    calSlot.innerHTML="";calibration(calSlot,report);
  });
}
function displayReview(root,report) {
  const entries=[["真实赛前冻结",report.prospective],["事后重建",report.retrospective]];
  output(root,"结算表现",note("同一对阵在每一组内取最新预测截点；各组仅统计已结算记录。")+
    table(["捕获时点","样本数","方向命中率","对数损失","Brier","首选比分命中率"],entries.map(([label,m])=>[label,m.n,percent(m.accuracy),decimal(m.log_loss),decimal(m.brier_sum),percent(m.top_score_accuracy)])),report,"review");
}
async function renderLedger(root) {
  root.innerHTML = card("冻结记录",'<div class="tool-row"><button type="button" data-refresh>刷新记录</button><button type="button" data-review>查看结算复盘</button></div><p class="tool-status" role="status"></p><div data-records></div>')+
    '<div data-action></div><div data-output></div>';
  const listSlot = root.querySelector("[data-records]"), action = root.querySelector("[data-action]");
  const refresh = async () => {
    const records=(await api("ledger")).records;
    listSlot.innerHTML = records.length ? `<div class="tool-metrics">${metric("冻结版本",records.length)}${metric("待结算版本",records.filter(r=>r.home_goals==null).length)}</div>`+
      table(["对阵","开球 · UTC","预测截点 · UTC","冻结类型","90 分钟赛果","操作"],records.map((r,i)=>[
        `${nameMarkup(r,"home")} / ${nameMarkup(r,"away")}`,escapeText(r.kickoff),escapeText(r.as_of),r.prospective?"赛前冻结":"事后重建",
        r.home_goals==null?"待结算":`${escapeText(r.home_goals)} – ${escapeText(r.away_goals)}`,
        `<div class="tool-row"><button type="button" data-archive="${i}">回放</button>${r.home_goals==null?`<button type="button" data-settle="${i}">录入赛果</button>`:""}</div>`
      ])) : '<div class="tool-sub"><strong>暂无冻结记录</strong><p class="tool-hint">在单场预测开启「冻结预测」，或在比赛日勾选「冻结到台账」，运行后即可在这里回放和结算。</p></div>';
    listSlot.querySelectorAll("[data-archive]").forEach(btn=>btn.onclick=async()=>{
      btn.disabled=true;
      try {
        const {home,away,kickoff,as_of}=records[Number(btn.dataset.archive)];
        const report=await api("archive",{home,away,kickoff,as_of});
        action.innerHTML="";
        const p=report.prediction;
        output(root,`${displayName(report.input,"home")} / ${displayName(report.input,"away")} · 冻结回放`,note(`冻结时间 ${report.frozen_at} · ${report.prospective?"真实赛前冻结":"事后重建"}`)+sourceMarkup(report)+
          `<div class="tool-metrics">${metric("主胜",percent(p.probs[0]))}${metric("平局",percent(p.probs[1]))}${metric("客胜",percent(p.probs[2]))}</div>`+
          block("报告版本",table(["捕获时间","摘要 SHA-256"],report.reports.map(r=>[escapeText(r.captured_at),escapeText(r.sha256)]))),report,"archive");
      } catch(e) {message(root,e.message,true);} finally {btn.disabled=false;}
    });
    listSlot.querySelectorAll("[data-settle]").forEach(btn=>btn.onclick=()=>{
      const row=records[Number(btn.dataset.settle)];
      action.innerHTML=card(`录入赛果 · ${row.home} / ${row.away}`,`<form>${note("填写 90 分钟及伤停补时比分，加时与点球须单独区分。")}<div class="tool-flex">${input(`${row.home} 进球`,"home_goals","","number",'min="0" step="1" required')}${input(`${row.away} 进球`,"away_goals","","number",'min="0" step="1" required')}</div><label class="tool-check"><input type="checkbox" required>已确认比赛完场及常规时间比分</label>${submit("保存赛果")}</form>`);
      const form=action.querySelector("form");
      form.elements.home_goals.focus();
      bindSubmit(form,async()=>{
        const {home,away,kickoff}=row;
        await api("settle",{results:[{home,away,kickoff,status:"FINISHED",market:"1x2_90",home_goals:Number(val(form,"home_goals")),away_goals:Number(val(form,"away_goals"))}]});
        await refresh(); action.innerHTML=""; displayReview(root,await api("review",{}));
      });
    });
  };
  const reload = root.querySelector("[data-refresh]");
  reload.onclick=async()=>{
    reload.disabled=true;
    try {await refresh();message(root,"记录已刷新");}catch(e){message(root,e.message,true);}
    finally{reload.disabled=false;}
  };
  const reviewBtn=root.querySelector("[data-review]");
  reviewBtn.onclick=async()=>{
    reviewBtn.disabled=true;
    try {displayReview(root,await api("review",{}));message(root,"复盘已生成");}
    catch(e){message(root,e.message,true);}finally{reviewBtn.disabled=false;}
  };
  await refresh();
}
export async function renderTool(kind, container) {
  if (!toolPages[kind]) throw Error("未知研究工具");
  if (kind!=="ledger" && views.has(kind)) {container.replaceChildren(views.get(kind));return;}
  const page=document.createElement("div");page.className="tool-page";
  const [title,subtitle]=toolPages[kind];
  page.innerHTML=`<header class="tool-head"><h1>${escapeText(title)}</h1><p>${escapeText(subtitle)}</p></header><div data-tool-body><p class="tool-hint" role="status">正在载入…</p></div>`;
  container.replaceChildren(page);
  const body=page.querySelector("[data-tool-body]");
  try {
    if (kind==="ledger") await renderLedger(body);
    else if (kind==="sources") renderSources(body);
    else {
      const sample=await examples();
      ({batch:renderBatch,cup:renderCup,elo:fitForm,backtest:renderBacktest})[kind](body,sample);
    }
    installFileImports(page);
    if(kind!=="ledger") views.set(kind,page);
  } catch(e) {
    body.innerHTML=card("加载失败",note(e.message)+'<div class="tool-actions"><button type="button">重试</button></div>');
    body.querySelector("button").onclick=()=>renderTool(kind,container);
  }
}
