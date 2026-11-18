import {api, esc, icon, pct, displayName, originalName, nameMarkup, sourceMarkup, nameIsProvisional, fixtureMatchesSearch} from "./ui.js";
const labels={espn:"ESPN 公共赛程","football-data":"Football-Data.org"};
const statusNames={
  SCHEDULED:"未开赛",TIMED:"未开赛",NS:"未开赛",NOT_STARTED:"未开赛",UPCOMING:"未开赛",
  IN_PLAY:"进行中",LIVE:"进行中",IN_PROGRESS:"进行中",PAUSED:"中场",HALFTIME:"中场",
  FINISHED:"已完场",FT:"已完场",FINAL:"已完场",COMPLETED:"已完场",
  POSTPONED:"已延期",CANCELLED:"已取消",CANCELED:"已取消",SUSPENDED:"已中断",UNKNOWN:"状态待定"
};
const settings=[
  ["history","历史赛果",true],["odds","参考三项赔率",false],["matrix","比分矩阵",true],["timeline","半场与分段",false],
  ["knockout","淘汰赛晋级",false],["ledger","冻结入账",false],["ai","报告 AI 解读",false]
];
const timezone="Asia/Hong_Kong";
const dateFormat=new Intl.DateTimeFormat("zh-CN",{timeZone:timezone,month:"2-digit",day:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit",hourCycle:"h23"});
let page, collection, predictions, busy="", timer, translationTimer;
let translating=false, translationError="", lastNameCheck=0;
let autoStarted=false;
const selected=new Set();
const selectedFlags={};
let runFlags={};
let displayed=[];
const q=s=>page.querySelector(s);
const htmlDate=value=>Number.isFinite(Date.parse(value))?dateFormat.format(new Date(value)):"—";
const issueText=value=>{
  if (typeof value==="string") return value;
  if (!value || typeof value!=="object") return "来源未提供说明。";
  const subject=[value.competition||value.league||value.source,value.date].filter(Boolean).join(" ");
  const message=value.reason||value.message||value.error||value.detail||value.note;
  return [subject,message].filter(Boolean).join(" · ")||JSON.stringify(value);
};
const describe=values=>Array.isArray(values)&&values.length?`<ul>${values.map(v=>`<li>${esc(issueText(v))}</li>`).join("")}</ul>`:"";
const details=(title,values)=>Array.isArray(values)&&values.length?`<details><summary>${esc(title)}（${values.length}）</summary>${describe(values)}</details>`:"";
const stat=(label,value)=>`<span class="collect-stat"><b>${esc(value)}</b>${esc(label)}</span>`;
const title=(name,label)=>`<div class="collect-heading"><h2 class="collect-icon-title">${icon(name,18)} ${esc(label)}</h2></div>`;
function hkDate(value) { return new Date(value+8*3600000).toISOString().slice(0,10); }
function dateRange(days) {
  const now=Date.now();
  q("[name=start]").value=hkDate(now)+"T00:00";
  q("[name=end]").value=hkDate(now+(days-1)*86400000)+"T23:59";
}
function feedback(where,text,error=false) {
  const el=q(`[data-message="${where}"]`);
  el.textContent=text;el.classList.toggle("error",error);
}
function allowed(f,now=Date.now()) {
  return f.eligible===true && Date.parse(f.kickoff)>now;
}
function labelForStatus(f,now) {
  if (allowed(f,now))return f.cached_offline?"缓存 · 待核验":"可预测";
  const status=String(f.status||"UNKNOWN").toUpperCase();
  if (f.eligible && Date.parse(f.kickoff)<=now)return "开球时间已过";
  return statusNames[status]||status;
}
function updateButtons() {
  const waiting=Boolean(busy);
  q("[data-search]").disabled=waiting;
  q("[data-search]").innerHTML=icon(busy==="search"?"clock":"data",16)+(busy==="search"?" 正在采集…":" 采集 / 刷新赛程");
  q("[data-query]").setAttribute("aria-busy",String(busy==="search"));
  for(const el of page.querySelectorAll("[data-days], [data-retry-names], [name=start], [name=end], [name=source]"))el.disabled=waiting;
  const all=(collection?.fixtures||[]).filter(f=>allowed(f));
  const current=displayed.filter(f=>allowed(f));
  const n=all.filter(f=>selected.has(f.id)).length;
  q("[data-selected-count]").textContent=`已选 ${n} 场`;
  q("[data-predict-selected]").disabled=waiting||!n;
  q("[data-predict-all]").disabled=waiting||!all.length;
  q("[data-predict-all]").textContent=`预测全部可用（${all.length}）`;
  const toggle=q("[data-check-visible]");
  if(toggle){
    const count=current.filter(f=>selected.has(f.id)).length;
    toggle.checked=current.length>0 && count===current.length;
    toggle.indeterminate=count>0 && count<current.length;
    toggle.disabled=waiting||!current.length;
  }
  q("[data-clear]").disabled=waiting||!n;
  for(const el of page.querySelectorAll("[data-pick], [data-predict-one]")){
    const f=displayed[Number(el.dataset.pick??el.dataset.predictOne)];
    el.disabled=waiting||!f||!allowed(f);
  }
  page.querySelectorAll("[data-flag]").forEach(el=>{el.disabled=waiting;});
  page.classList.toggle("collect-running",waiting);
  const retryNames=q("[data-retry-names]");
  if(retryNames)retryNames.disabled=waiting||translating;
}
function pendingNames(data=collection) {
  return (data?.fixtures||[]).some(row=>Object.values(row.translation||{}).some(info=>info?.pending===true || info?.method==="pending"));
}
function scheduleTranslation() {
  clearTimeout(translationTimer);
  if(!page.isConnected || translationError || translating || busy==="search")return;
  if(pendingNames()){translationTimer=setTimeout(()=>refreshNames(),5000);return;}
  const deadlines=(collection?.fixtures||[]).flatMap(row=>Object.values(row.translation||{}))
    .map(info=>info?.retry_after).filter(time=>Number.isFinite(time)&&time>lastNameCheck);
  if(deadlines.length){
    const delay=Math.max(1000,Math.min(...deadlines)*1000-Date.now());
    translationTimer=setTimeout(()=>refreshNames(),Math.min(delay,2147000000));
  }
}
function alignForecastNames(data) {
  const fixtures=new Map((collection?.fixtures||[]).map(row=>[row.id,row]));
  return {...data,matches:data.matches.map(match=>{
    const row=fixtures.get(match.collection?.id);
    if(!row)return match;
    const input={...match.input,translation:{...match.input.translation}};
    for(const field of ["home","away","competition","stage"]){
      if(row[field]!==input[field] || row[field+"_zh"]===undefined)continue;
      input[field+"_zh"]=row[field+"_zh"];
      if(row.translation?.[field])input.translation[field]=row.translation[field];
      if(Array.isArray(row[field+"_aliases"]))input[field+"_aliases"]=[...row[field+"_aliases"]];
    }
    return {...match,input};
  })};
}
function renderCoverage() {
  q("[data-coverage]").innerHTML=infoFor(collection);
}
function competitionKey(row) {
  const provider=row.provenance?.provider||row.source||collection?.source||"";
  const id=row.competition_id??row.provenance?.competition_id;
  return JSON.stringify([provider,id!=null&&String(id)!==""?"id":"name",
    id!=null&&String(id)!==""?String(id):originalName(row,"competition")]);
}
function leagueGroups() {
  const groups=new Map();
  for(const row of collection?.fixtures||[]){
    if(!row.competition)continue;
    const key=competitionKey(row),group=groups.get(key);
    if(!group)groups.set(key,{row,originals:new Set([row.competition])});
    else{
      group.originals.add(row.competition);
      if(nameIsProvisional(group.row,"competition")&&!nameIsProvisional(row,"competition"))group.row=row;
    }
  }
  return groups;
}
function renderLeagues() {
  const field=q("[name=league]"),selectedLeague=field.value;
  const groups=leagueGroups();
  field.innerHTML='<option value="">所有赛事</option>'+[...groups].sort((a,b)=>displayName(a[1].row,"competition").localeCompare(displayName(b[1].row,"competition"),"zh-CN"))
    .map(([key,{row,originals}])=>`<option value="${esc(key)}" title="${esc([...originals].join(' / '))}">${esc(displayName(row,"competition"))}${nameIsProvisional(row,"competition")?" · 音译待核验":""}</option>`).join("");
  field.value=groups.has(selectedLeague)?selectedLeague:"";
}
async function refreshNames(retry=false) {
  if(!collection||translating||busy==="search"||!page.isConnected)return;
  const id=collection.collection_id;
  translating=true;translationError="";lastNameCheck=Date.now()/1000;clearTimeout(translationTimer);updateButtons();
  try{
    const updated=await api("collector/localize",{collection_id:id,retry});
    if(collection?.collection_id!==id)return;
    if(!Array.isArray(updated.fixtures)||updated.collection_id!==id)throw Error("名称刷新返回了不匹配的赛程。");
    collection=updated;
    renderCoverage();renderLeagues();drawFixtures();
    if(predictions)showPredictions(predictions,runFlags);
  }catch(error){
    if(collection?.collection_id===id){translationError=error.message||"中文名称暂未更新。";renderNameState();}
  }finally{
    translating=false;updateButtons();scheduleTranslation();
  }
}
function scheduleUpdate() {
  clearTimeout(timer);
  const future=(collection?.fixtures||[]).filter(f=>allowed(f)).map(f=>Date.parse(f.kickoff));
  if (!future.length)return;
  const wait=Math.min(Math.min(...future)-Date.now()+100,2147000000);
  timer=setTimeout(()=>{if(page.isConnected)drawFixtures();},Math.max(100,wait));
}
function renderNameState() {
  const host=q("[data-name-state]");
  if(!displayed.length){host.innerHTML="";return;}
  const unique=new Map();
  for(const row of displayed){
    for(const key of ["home","away","competition"]){
      const original=originalName(row,key);
      if(!original)continue;
      const identity=JSON.stringify([key==="competition"?competitionKey(row):"team",original]);
      unique.set(identity,{row,key,info:row.translation?.[key]});
    }
  }
  const names=[...unique.values()];
  const ready=names.filter(({row,key})=>/[\u3400-\u9fff]/.test(displayName(row,key))).length;
  const provisional=names.filter(({row,key})=>nameIsProvisional(row,key)).length;
  const unfinished=names.filter(({info})=>info?.pending===true||info?.method==="pending").length;
  const later=names.some(({info})=>Number.isFinite(info?.retry_after));
  const missing=names.length-ready;
  let text=missing?`当前筛选已有 ${ready} / ${names.length} 个球队与赛事名称显示中文。`:"当前筛选的球队与赛事均已显示中文。";
  if(provisional)text+=` 其中 ${provisional} 个为自动音译，已标注待核验。`;
  if(unfinished&&!translationError)text+=" 后台正在查找常用译名，完成后自动更新。";
  else if(provisional&&later&&!translationError)text+=" 后台稍后继续校正译名。";
  if(translationError&&(provisional||missing))text+=" 译名更新暂不可用，当前名称仍可搜索。";
  const retry=(provisional||missing)&&(!unfinished||translationError);
  host.innerHTML=`<p class="collect-small">${esc(text)}</p>${retry?'<button type="button" class="collect-quiet" data-retry-names>重新核验译名</button>':""}`;
  const button=host.querySelector("[data-retry-names]");
  if(button)button.onclick=()=>refreshNames(true);
}
function clearFilters() {
  q("[name=league]").value="";q("[name=team]").value="";
  drawFixtures();q("[name=team]").focus();
}
function drawFixtures() {
  if (!collection){displayed=[];updateButtons();return;}
  const fixtures=collection.fixtures,now=Date.now(),league=q("[name=league]").value,query=q("[name=team]").value;
  const available=fixtures.filter(f=>allowed(f,now));
  for(const f of fixtures)if(!allowed(f,now))selected.delete(f.id);
  displayed=fixtures.filter(f=>(!league||competitionKey(f)===league)&&fixtureMatchesSearch(f,query));
  q("[data-counts]").innerHTML=stat("采集赛事",leagueGroups().size)+stat("发现比赛",fixtures.length)+stat("当前可预测",available.length);
  const list=q("[data-fixtures]");
  if(!displayed.length){
    list.innerHTML=`<div class="collect-empty">${fixtures.length?"没有匹配当前筛选的比赛。":"本次覆盖范围内没有返回比赛，可调整时段或切换来源后重试。"}${fixtures.length?'<div class="collect-buttons"><button type="button" class="collect-action" data-reset-filters>清除筛选，查看全部已采集比赛</button></div>':""}</div>`;
    const reset=list.querySelector("[data-reset-filters]");if(reset)reset.onclick=clearFilters;
  }else{
    list.innerHTML=`<div class="collect-table"><table><thead><tr><th><input type="checkbox" data-check-visible aria-label="勾选筛选结果中的所有可预测比赛" title="勾选筛选结果中的所有可预测比赛"></th><th>开球 · 香港时间</th><th>联赛 / 对阵</th><th>比赛状态</th><th>来源</th><th>单场操作</th></tr></thead><tbody>${displayed.map((f,i)=>{
      const ok=allowed(f,now), reason=ok?"":f.reason;
      return `<tr><td><input type="checkbox" data-pick="${i}" aria-label="选择 ${esc(displayName(f,"home"))} 对 ${esc(displayName(f,"away"))}" ${selected.has(f.id)&&ok?"checked":""} ${ok?"":"disabled"}></td><td class="nowrap">${esc(htmlDate(f.kickoff))}</td><td><span class="muted">${f.competition?nameMarkup(f,"competition"):"未标赛事"}${f.stage?" · "+nameMarkup(f,"stage"):""}</span><b>${nameMarkup(f,"home")} / ${nameMarkup(f,"away")}</b></td><td><span class="collect-pill ${ok?"":"dim"}">${esc(labelForStatus(f,now))}</span>${reason?`<span class="muted">${esc(reason)}</span>`:""}</td><td>${esc(labels[f.source||collection.source]||f.source||collection.source||"—")}${sourceMarkup(f,{compact:true})}</td><td>${ok?`<button type="button" class="collect-action" data-predict-one="${i}">预测此场</button>`:"—"}</td></tr>`;
    }).join("")}</tbody></table></div>`;
  }
  const checkedAll=q("[data-check-visible]");
  if(checkedAll)checkedAll.onchange=()=>{for(const f of displayed.filter(f=>allowed(f,now)))checkedAll.checked?selected.add(f.id):selected.delete(f.id);drawFixtures();};
  for(const el of list.querySelectorAll("[data-pick]"))el.onchange=()=>{
    const f=displayed[Number(el.dataset.pick)];
    if(!allowed(f)){drawFixtures();return;}
    el.checked?selected.add(f.id):selected.delete(f.id);updateButtons();
  };
  for(const el of list.querySelectorAll("[data-predict-one]"))el.onclick=()=>predict([displayed[Number(el.dataset.predictOne)].id]);
  q("[data-visible-count]").textContent=`筛选结果 ${displayed.length} 场`;
  renderNameState();updateButtons();scheduleUpdate();
}
function infoFor(data) {
  const coverage=data.coverage||{},items=coverage.issues||[];
  const counted=Number.isInteger(coverage.requested)&&Number.isInteger(coverage.succeeded);
  const provider=labels[data.source]||data.source||"数据来源";
  return `<div class="collect-banner">${icon("data",16)}<div><strong>${esc(provider)}${coverage.complete===false?" · 部分覆盖":""}</strong><div>${esc(coverage.label||"按所选时段和来源收录")}${counted?` · 成功 ${coverage.succeeded} / ${coverage.requested} 项查询`:""}</div></div></div>
    <div class="collect-caption"><span>采集于 <time title="${esc(data.observed_at)}">${esc(htmlDate(data.observed_at))} UTC+8</time></span><span>比赛时段 ${esc(htmlDate(data.start))} – ${esc(htmlDate(data.end))}</span></div>${details("未完成的来源查询",items)}`;
}
function setCollection(data) {
  if(!Array.isArray(data.fixtures)||!data.collection_id)throw Error("来源未返回有效赛程集合，请尝试重新采集。");
  collection=data;selected.clear();predictions=null;translationError="";lastNameCheck=0;clearTimeout(translationTimer);
  q("[data-prediction-zone]").hidden=true;
  renderCoverage();q("[name=league]").value="";renderLeagues();
  q("[name=team]").value="";q("[data-collection]").hidden=false;
  feedback("predict","");drawFixtures();
}
async function search(refresh=true) {
  if(busy)return;
  const start=q("[name=start]").value,end=q("[name=end]").value;
  if(!start||!end||start>end){feedback("search","请填写有效的起止时间，结束时间应晚于起始时间。",true);return;}
  busy="search";updateButtons();
  feedback("search","正在查询各赛事来源…");
  try{
    const data=await api("collector/search",{source:q("[name=source]").value,start:start+":00+08:00",end:end+":59+08:00",refresh});
    const failedAll=!data.fixtures?.length && data.coverage?.requested>0 && data.coverage.succeeded===0 && data.coverage.issues?.length;
    if(failedAll && collection)throw Error(`本次未能取得赛程。${issueText(data.coverage.issues[0])}`);
    setCollection(data);
    feedback("search",failedAll?"本次来源请求均失败，可查看覆盖说明后重试。":`收到 ${data.fixtures.length} 场比赛。`,Boolean(failedAll));
  }catch(e){feedback("search",(e.message||"赛程查询失败。")+(collection?" 仍保留上次成功采集的赛程。":""),true);}
  finally{busy="";updateButtons();scheduleTranslation();}
}
function showPredictions(data,flags) {
  if(!Array.isArray(data.matches))throw Error("未收到有效的预测报告。");
  data=alignForecastNames(data);
  predictions=data;runFlags={...flags};
  const matches=data.matches,skipped=data.skipped||[],target=q("[data-results]");
  q("[data-prediction-zone]").hidden=false;
  q("[data-run-stats]").innerHTML=stat("完成预测",matches.length)+stat("已跳过",skipped.length);
  const body=matches.map((m,i)=>{
    const input=m.input,p=m.prediction,meta=m.collection||{},best=p.top_scores?.[0];
    return `<tr><td><span class="muted">${input.competition?nameMarkup(input,"competition"):"未标赛事"}</span><b>${nameMarkup(input,"home")} / ${nameMarkup(input,"away")}</b></td><td>${esc(htmlDate(input.as_of))}<span class="muted">${esc(input.as_of)}</span></td><td>${pct(p.probs[0])}</td><td>${pct(p.probs[1])}</td><td>${pct(p.probs[2])}</td><td>${best?`${esc(best.home)} : ${esc(best.away)}`:"—"}</td><td>${esc(p.eligible_history??meta.history_count??"—")} 场<span class="muted">${meta.home_count!=null?`主队相关 ${esc(meta.home_count)} · `:""}${meta.away_count!=null?`客队相关 ${esc(meta.away_count)}`:""}</span></td><td>${sourceMarkup(m,{compact:true})}<div class="collect-report-links"><button type="button" class="collect-action" data-report="${i}" data-route="simulation">${icon("play",12)} 播放模拟</button><button type="button" class="collect-action" data-report="${i}" data-route="report">查看报告</button></div></td></tr>`;
  }).join("");
  target.innerHTML=matches.length?`<div class="collect-table"><table><thead><tr><th>对阵</th><th>预测截点</th><th>主胜</th><th>平局</th><th>客胜</th><th>首选比分</th><th>可用历史</th><th>单场报告</th></tr></thead><tbody>${body}</tbody></table></div>`:'<div class="collect-empty">本次没有生成赛前预测。请检查跳过原因，或重新采集赛程。</div>';
  q("[data-run-issues]").innerHTML=details("跳过的比赛",skipped.map(r=>({source:[displayName(r,"home"),displayName(r,"away")].filter(Boolean).join(" / ")||r.id,reason:r.reason})))+
    details("历史来源与样本说明",matches.map(m=>{
      const info=m.collection||{},notes=(info.notes||[]).map(issueText);
      return [displayName(m.input,"home")+" / "+displayName(m.input,"away"),info.history_source,...notes].filter(Boolean).join(" · ");
    }).filter(Boolean))+details("数据源覆盖说明",data.coverage?.issues);
  for(const el of target.querySelectorAll("[data-report]"))el.onclick=()=>{
    const m=predictions.matches[Number(el.dataset.report)];
    const result={...predictions,kind:"forecast",market:predictions.market||"1x2_90",matches:[m]};
    window.dispatchEvent(new CustomEvent("studio-open-forecast",{detail:{result,flags:{...runFlags},route:el.dataset.route}}));
  };
}
async function predict(ids,all=false) {
  if(busy||!collection)return;
  const available=collection.fixtures.filter(f=>allowed(f));
  const requested=all?available:available.filter(f=>ids.includes(f.id));
  if(!requested.length){feedback("predict","选择范围内已没有可预测比赛，请重新采集。",true);drawFixtures();return;}
  const flags={...selectedFlags};
  busy="predict";updateButtons();feedback("predict",`正在准备 ${requested.length} 场赛前资料并计算…`);
  const payload={collection_id:collection.collection_id,...(all?{all:true}:{ids:requested.map(f=>f.id)})};
  for(const [key] of settings)if(key!=="ai")payload[key]=flags[key];
  try{
    const data=await api("collector/predict",payload);
    showPredictions(data,flags);
    feedback("predict",`已完成 ${data.matches.length} 场，跳过 ${data.skipped?.length||0} 场。`);
    if(page.isConnected)q("[data-prediction-zone]").scrollIntoView({behavior:"smooth",block:"start"});
  }catch(e){feedback("predict",(e.message||"预测失败。")+(predictions?" 下方保留上一次的预测结果。":""),true);}
  finally{busy="";drawFixtures();}
}
function mount() {
  if(!document.querySelector('link[href="/collector.css"]')){
    const link=document.createElement("link");link.rel="stylesheet";link.href="/collector.css";document.head.append(link);
  }
  page=document.createElement("div");page.className="collector";
  const options=Object.entries(labels).map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join("");
  const flags=settings.map(([key,label,on])=>{selectedFlags[key]=on;return `<label><input type="checkbox" data-flag="${key}" ${on?"checked":""}>${esc(label)}</label>`;}).join("");
  page.innerHTML=`<header class="page-head"><div><h1>自动采集与预测</h1><p>按香港时间收集足球赛程，从多个赛事中选择要预测的比赛。</p></div></header>
    <section class="collect-card">${title("data","采集赛程")}<form data-query>
      <div class="collect-inputs">
        <label class="collect-field">开始时间 · UTC+8<input required type="datetime-local" name="start"></label>
        <label class="collect-field">结束时间 · UTC+8<input required type="datetime-local" name="end"></label>
        <label class="collect-field">数据来源<select name="source">${options}</select></label></div>
      <div class="collect-caption"><span>快捷范围</span><button class="collect-quiet" type="button" data-days="1">今天</button><button class="collect-quiet" type="button" data-days="3">未来 3 天</button><button class="collect-quiet" type="button" data-days="7">未来 7 天</button></div>
      <p class="collect-small" data-source-note></p>
      <div class="collect-buttons"><button type="submit" class="primary" data-search>${icon("data",16)} 自动采集赛程</button></div>
      <p class="collect-feedback" data-message="search" role="status"></p></form></section>
    <section class="collect-card" data-collection hidden>${title("batch","赛程与比赛选择")}<div data-coverage></div><div class="collect-statrow" data-counts></div>
      <div class="collect-inputs"><label class="collect-field">按赛事筛选<select name="league"><option value="">所有赛事</option></select></label>
      <label class="collect-field">搜索球队或赛事<input type="search" name="team" placeholder="支持中文全名、简称、原名，例如英超、曼城" autocomplete="off"></label></div>
      <div data-name-state role="status"></div>
      <div class="collect-caption"><span data-visible-count></span><span data-selected-count>已选 0 场</span><button type="button" class="collect-quiet" data-clear>清空勾选</button></div>
      <div data-fixtures></div>
      <h3>预测设置</h3><div class="collect-chips">${flags}</div>
      <p class="collect-small">运行前重新核验比赛状态。勾选历史赛果后，将为所选对阵收集可用的常规时间比分。</p>
      <div class="collect-buttons"><button type="button" class="primary" data-predict-selected>${icon("play",15)} 预测已选</button><button type="button" class="collect-action" data-predict-all>预测全部可用</button></div>
      <p class="collect-feedback" data-message="predict" role="status"></p></section>
    <section class="collect-card" data-prediction-zone hidden>${title("chart","比赛预测结果")}<div data-run-stats class="collect-statrow"></div><div data-results></div><div data-run-issues></div></section>`;
  const now=Date.now();
  const localMinute=ms=>new Date(ms+8*3600000).toISOString().slice(0,16);
  q("[name=start]").value=localMinute(now);
  q("[name=end]").value=localMinute(now+86400000);
  const source=q("[name=source]");
  function explainSource(){
    q("[data-source-note]").textContent=source.value==="espn"?"按日期查询 ESPN 全球足球索引，覆盖来源已收录的国内、洲际、女子及青年赛事。时段越长，查询时间越长。":"查询 Football-Data.org 已收录且账户有权访问的赛事。需预先在本地服务设置 FOOTBALL_DATA_TOKEN。";
  }
  explainSource();source.onchange=explainSource;
  q("[data-query]").onsubmit=e=>{e.preventDefault();search();};
  for(const el of page.querySelectorAll("[data-days]"))el.onclick=()=>dateRange(Number(el.dataset.days));
  q("[name=league]").onchange=drawFixtures;q("[name=team]").oninput=drawFixtures;
  q("[data-clear]").onclick=()=>{selected.clear();drawFixtures();};
  for(const el of page.querySelectorAll("[data-flag]"))el.onchange=()=>{selectedFlags[el.dataset.flag]=el.checked;};
  q("[data-predict-selected]").onclick=()=>predict([...selected]);
  q("[data-predict-all]").onclick=()=>predict([],true);
}
export function renderCollector(container) {
  if (!page)mount();
  container.replaceChildren(page);
  drawFixtures();
  scheduleTranslation();
  if(!autoStarted){autoStarted=true;search(false);}
}
