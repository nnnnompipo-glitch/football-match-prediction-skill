import {icon,esc,pct,api,modules,defaultFlags,stamp,teamName,displayName,originalName,toast} from './ui.js';
import {demoData,editMatch,buildPayload} from './match.js';
import {report} from './report.js';
import {renderTool} from './tools.js';
import {renderSettings} from './ai.js';

const pages=[
  ['desk','研究工作台','dashboard'],['collector','赛程采集','batch'],['simulation','比赛演播室','play'],['single','单场预测','pitch'],['batch','比赛日分析','batch'],['cup','杯赛模拟','cup'],
  ['sources','数据源','data'],['elo','Elo 实力榜','ranking'],['backtest','滚动回测','test'],['ledger','预测台账','ledger'],
  ['report','预测报告','report'],['settings','模型设置','settings']
];
const resolve=()=>pages.find(p=>p[0]===location.hash.slice(1))?.[0]||'desk';
const view=document.querySelector('#view'),side=document.querySelector('#sidebar'),utility=document.querySelector('#utility'),veil=document.querySelector('#veil');
let saved={};
try{saved=JSON.parse(localStorage.getItem('touchline.modules'))||{};}catch{}
const state={flags:{...defaultFlags},input:null,extra:{},result:null,resultFlags:null,dirty:false,filter:'all',expanded:false,chart:'final',running:false,connected:false};
for(const key of Object.keys(defaultFlags)) if(typeof saved[key]==='boolean')state.flags[key]=saved[key];
let runSeq=0;
let focusForecast=null, disposeRoute=null, drawnPage=null;
const dateToday=()=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Hong_Kong',year:'numeric',month:'long',day:'numeric',weekday:'long'}).format(new Date());
function persist(){try{localStorage.setItem('touchline.modules',JSON.stringify(state.flags));}catch{}}
function saveDraft(){
  try{localStorage.setItem('touchline.draft',JSON.stringify({input:state.input,extra:state.extra}));}
  catch{try{localStorage.removeItem('touchline.draft');}catch{}toast('此份数据较大，仅在当前页面保留。');}
}
function title(id){return pages.find(p=>p[0]===id)?.[1]||'';}
function setMenu(open){side.classList.toggle('opened',open);veil.hidden=!open;utility.querySelector('.mobile-menu')?.setAttribute('aria-expanded',String(open));}
veil.onclick=()=>setMenu(false);
function navLink(item,id){
  return `<a href="#${item[0]}" class="nav-item ${item[0]===id?'active':''}" ${item[0]===id?'aria-current="page"':''}>${icon(item[2],18)}<span>${item[1]}</span>${item[0]===id?'<b class="current-dot"></b>':''}</a>`;
}
function frame(id){
  side.innerHTML=`<a class="brand" href="#desk"><img src="/mark.svg" width="41" height="41" alt=""><span><strong>足球赛前研究室</strong><small>TOUCHLINE LAB</small></span></a>
  <div class="nav-section"><div class="nav-caption">工作空间</div>${pages.slice(0,6).map(p=>navLink(p,id)).join('')}</div>
  <div class="nav-section"><div class="nav-caption">数据与复盘</div>${pages.slice(6,-1).map(p=>navLink(p,id)).join('')}</div>
  <div class="side-foot">${navLink(pages.at(-1),id)}<div class="device"><div>${icon('monitor',19)}</div><span><strong>本地工作空间</strong><small>Local workspace</small></span></div></div>`;
  utility.innerHTML=`<div class="crumb"><button class="mobile-menu icon-btn" aria-label="展开导航" aria-expanded="false">${icon('menu')}</button>${icon('layers',16)}<span>工作空间</span><i>/</i><strong>${title(id)}</strong></div><div class="utility-right"><span class="engine-state ${state.connected?'online':''}"><b></b>${state.connected?'本地引擎在线':'引擎连接中'}</span><span class="utility-divider"></span><span class="today">${icon('batch',15)}${dateToday()}</span></div>`;
  utility.querySelector('.mobile-menu').onclick=()=>setMenu(!side.classList.contains('opened'));
  side.querySelectorAll('a').forEach(a=>a.onclick=()=>setMenu(false));
}
function crest(type,isDemo){
  if(!isDemo)return `<span class="generic-crest">${icon('flag',27)}</span>`;
  return type==='home'?`<svg viewBox="0 0 48 54" width="45" height="51" aria-hidden="true"><path d="M5 5 24 1l19 4v21c0 12-10 20-19 25C14 46 5 38 5 26Z" fill="#e8dfb4" stroke="#fdefb4" stroke-width="2"/><path d="m9 8 15-3 15 3v18c0 9-7 16-15 21-8-5-15-12-15-21Z" fill="#304a42"/><path d="m12 30 7 3 5-3 5 3 7-3v4l-7 3-5-3-5 3-7-3z" fill="#e9d69e"/><g fill="#e9d69e"><path d="M23 10v17H13l10-17zm3 3 9 14h-9zM12 29h24l-5 3H17z"/></g></svg>`:
  `<svg viewBox="0 0 48 54" width="45" height="51" aria-hidden="true"><path d="M5 5 24 1l19 4v21c0 12-10 20-19 25C14 46 5 38 5 26Z" fill="#b8dba3" stroke="#e0f0c8" stroke-width="2"/><path d="m9 8 15-3 15 3v18c0 9-7 16-15 21-8-5-15-12-15-21Z" fill="#285647"/><path d="m24 9-7 9h4l-8 10h5l-6 7h10v5h4v-5h10l-6-7h5l-8-10h4z" fill="#d3e7b8"/></svg>`;
}
function matchHero(){
  const i=state.input,home=teamName(i,'home'),away=teamName(i,'away');
  return `<article class="match-hero"><div class="hero-top"><span class="hero-kicker"><i></i>MATCH SPOTLIGHT</span><span class="demo-pill">${i.demo?'虚构演示':'自定义对阵'}</span></div>
  <div class="hero-content"><div class="hero-league" title="${esc(originalName(i,'competition'))}">${icon('cup',15)} ${esc(displayName(i,'competition')||'自定义赛事')}${i.stage?' · '+esc(displayName(i,'stage')):''}</div>
  <div class="versus"><div class="team">${crest('home',i.demo&&i.home==='Harbor XI')}<div><small>主队 · HOME</small><strong title="${esc(originalName(i,'home'))}">${esc(home)}</strong></div></div><b class="vs">vs</b><div class="team">${crest('away',i.demo&&i.away==='Pine XI')}<div><small>客队 · AWAY</small><strong title="${esc(originalName(i,'away'))}">${esc(away)}</strong></div></div></div></div>
  <div class="hero-bottom"><span>${icon('clock',15)}${esc(stamp(i.kickoff))}<small> UTC+8</small></span><div class="hero-buttons"><button data-show-simulation>${icon('play',12)} 播放比赛模拟</button><button data-edit="match">编辑对阵 ${icon('edit',13)}</button></div></div></article>`;
}
const chartColors=['#1e674c','#b3d87c','#e6b185'];
function overview(){
  const m=!state.dirty&&state.result?.matches?.[0],p=m?.prediction;
  if(!p)return `<section class="overview panel"><div class="panel-title"><h2>胜平负概率</h2>${icon('circlechart',20)}</div><div class="waiting">${icon('circlechart',33)}<b>${state.running?'正在计算概率…':'等待运行预测'}</b><span class="hint">${state.running?'正在读取本场数据。':'当前输入或模块已变更。'}</span></div></section>`;
  const probs=state.chart==='base'?p.base_probs:p.probs,top=probs.indexOf(Math.max(...probs));
  let offset=0;
  const segments=probs.map((v,i)=>{const start=offset;offset+=100*v;return `${chartColors[i]} ${start+.45}% ${Math.max(start+.45,offset-.45)}%, #fff ${Math.max(start+.45,offset-.45)}% ${offset+.45}%`}).join(',');
  return `<section class="overview panel"><div class="panel-title"><h2>胜平负概率</h2><span class="micro-tag">90 分钟</span></div><div class="chart-body"><div class="donut" style="background:conic-gradient(from -90deg,${segments})"><div><strong>${(probs[top]*100).toFixed(1)}<small>%</small></strong><span>${['主胜','平局','客胜'][top]}倾向</span></div></div><div class="legend">${['主胜','平局','客胜'].map((k,i)=>`<div><i style="background:${chartColors[i]}"></i><span>${k}</span><b>${pct(probs[i])}</b></div>`).join('')}</div></div>
  <div class="chart-foot"><div class="chart-tabs" aria-label="概率版本">${[['final','综合'],['base','基础']].map(([k,l])=>`<button data-chart="${k}" aria-pressed="${state.chart===k}" class="${state.chart===k?'chosen':''}">${l}</button>`).join('')}</div><a href="#report">查看报告 ${icon('arrow',14)}</a></div></section>`;
}
function modulesHTML(){
  const enabled=Object.values(state.flags).filter(Boolean).length;
  let filtered=modules.filter(([id])=>state.filter==='all'||state.flags[id]),overflow=filtered.length>6;
  if(!state.expanded)filtered=filtered.slice(0,6);
  return `<section class="module-section"><div class="section-heading"><div><div class="eyebrow"><i></i> ANALYSIS MODULES</div><h2>分析模块 <small>${enabled} / ${modules.length} 已启用</small></h2></div>
  <div class="filter-tabs"><button class="${state.filter==='all'?'selected':''}" data-filter="all" aria-pressed="${state.filter==='all'}">全部模块</button><button class="${state.filter==='on'?'selected':''}" data-filter="on" aria-pressed="${state.filter==='on'}">已启用</button></div></div>
  <div class="module-grid">${filtered.map(([id,name,desc,ic,color])=>`<article class="module-card ${state.flags[id]?'on':''}"><div class="module-top"><span class="module-icon ${color}">${icon(ic,21)}</span><button type="button" role="switch" aria-label="${name}" aria-checked="${!!state.flags[id]}" data-toggle="${id}" class="switch"><i></i></button></div><button class="module-details" data-edit="${id}"><strong>${name}</strong>${icon('chevron',14)}</button><p>${desc}</p></article>`).join('')||`<div class="empty">尚未启用模块。切换到「全部模块」即可选择。</div>`}</div>${overflow?`<button class="more" data-more>${state.expanded?'收起模块':'查看其余 '+(state.filter==='on'?enabled-6:modules.length-6)+' 个模块'} ${icon('down',14)}</button>`:''}</section>`;
}
function changed(){
  state.dirty=true;runSeq++;state.running=false;persist();saveDraft();draw();
}
function editor(section){editMatch(state,(draft)=>{Object.assign(state,draft);changed();},section);}
function bindDesk(){
  view.querySelectorAll('[data-edit]').forEach(el=>el.onclick=()=>editor(el.dataset.edit));
  view.querySelectorAll('[data-run]').forEach(el=>el.onclick=()=>run(false));
  view.querySelector('[data-show-simulation]').onclick=()=>{
    focusForecast=null;
    if(state.dirty||!state.result)run(false,'simulation');else location.hash='simulation';
  };
  view.querySelector('a[href="#report"]')?.addEventListener('click',()=>{focusForecast=null;});
  view.querySelectorAll('[data-chart]').forEach(el=>el.onclick=()=>{state.chart=el.dataset.chart;draw()});
  view.querySelectorAll('[data-filter]').forEach(el=>el.onclick=()=>{state.filter=el.dataset.filter;state.expanded=false;draw()});
  view.querySelector('[data-more]')?.addEventListener('click',()=>{state.expanded=!state.expanded;draw()});
  view.querySelectorAll('[data-toggle]').forEach(el=>el.onclick=()=>{
    const id=el.dataset.toggle;state.flags[id]=!state.flags[id];state.dirty=true;persist();runSeq++;state.running=false;draw();
    view.querySelector(`[data-toggle="${id}"]`)?.focus({preventScroll:true});
  });
}
function dashboard(id){
  const detail=id==='single';
  view.innerHTML=`<div class="page-head"><div><div class="eyebrow"><i></i>${detail?'MATCH ANALYSIS':'RESEARCH WORKSPACE'}</div><h1>${detail?'单场预测':'赛前研究工作台'}</h1><p>${detail?'设置比赛资料和参数，计算本场胜平负。':'采集赛程、预测对阵，在球场上观看模拟比赛。'}</p></div><div class="head-actions desk-actions"><a class="secondary" href="#collector">${icon('batch',16)} 采集赛程</a><button class="primary run" data-run ${state.running?'disabled':''}>${icon('play',15)}${state.running?'正在运行…':state.flags.simulation?'预测并模拟':'运行预测'}</button></div></div>
  <div class="overview-grid">${matchHero()}${overview()}</div>${detail?`<div class="setup-strip"><span>${icon('sliders',18)} 单场输入与模型参数</span><button class="secondary" data-edit="import">${icon('upload',15)} 导入对阵</button><button class="secondary" data-edit="match">${icon('edit',15)} 编辑资料</button></div>`:''}${modulesHTML()}`;
  bindDesk();
}
async function run(auto,destination){
  const seq=++runSeq;state.running=true;if(!auto)draw();
  try{
    const out=await api('forecast',buildPayload(state,auto));
    if(seq!==runSeq)return;
    state.result=out;state.resultFlags={...state.flags,ledger:state.flags.ledger&&!auto};state.dirty=false;
    const input=out.matches?.[0]?.input;
    if(input){
      state.input={...state.input,...Object.fromEntries(['home_zh','away_zh','competition_zh','stage_zh','translation','home_aliases','away_aliases','competition_aliases','stage_aliases'].filter(k=>k in input).map(k=>[k,input[k]]))};
      saveDraft();
    }
    if(!auto){focusForecast=null;toast(state.flags.ledger?'预测完成，已写入本地台账':'预测完成');location.hash=destination||(state.flags.simulation?'simulation':'report');}
  }catch(e){
    if(seq!==runSeq)return;
    state.dirty=true;
    const msg='预测未完成：'+e.message;
    toast(msg);state.failure=msg;
  }finally{
    if(seq===runSeq){state.running=false;if(drawnPage===resolve()&&['desk','single','report','simulation'].includes(drawnPage))draw();}
  }
}
function draw(){
  if(disposeRoute){disposeRoute();disposeRoute=null;}
  const id=resolve();drawnPage=id;frame(id);document.title=title(id)+' · 足球赛前研究室';
  const current=focusForecast||{result:state.result,flags:state.resultFlags,origin:'desk'};
  if(!state.input){view.innerHTML='<div class="loading">正在连接本地预测引擎…</div>';return;}
  if(id==='desk'||id==='single'){
    dashboard(id);if(state.failure){const alert=document.createElement('p');alert.className='error';alert.textContent=state.failure;view.querySelector('.overview-grid').before(alert);state.failure=null;}
  }else if(id==='report'){
    if(current.result){report(view,current.result,current.flags);if(!focusForecast&&state.dirty){const msg=document.createElement('p');msg.className='report-stamp';msg.textContent='当前对阵或模块有更改。此处展示上一次完成的预测。';view.querySelector('.page-head').after(msg);}}
    else{view.innerHTML='<h1>预测报告</h1><p>尚未完成预测。</p><a class="primary" href="#desk">返回工作台</a>';}
  }else if(id==='simulation'||id==='collector'){
    const host=document.createElement('div');view.replaceChildren(host);
    host.innerHTML='<p class="loading" role="status">正在载入…</p>';
    async function openPage(){
      if(id==='collector'){
        const {renderCollector}=await import('./collector.js');
        if(host.isConnected)renderCollector(host);
      }else if(current.result){
        const {renderMatchroom}=await import('./matchroom.js');
        if(host.isConnected)disposeRoute=renderMatchroom(host,current.result.matches[0],current.origin);
      }else{host.innerHTML='<h1>比赛演播室</h1><p>生成一场预测后即可观看比赛。</p><a class="secondary" href="#collector">去采集赛程</a> <a class="primary" href="#desk">前往工作台</a>';}
    }
    openPage().catch(e=>{if(host.isConnected)host.textContent='页面未能载入：'+e.message;});
  }else if(id==='settings'){
    view.innerHTML=`<div class="page-head"><div><div class="eyebrow"><i></i> MODEL SETTINGS</div><h1>模型设置</h1><p>配置用于解读计算结果的大模型服务。</p></div></div><div class="settings-host"></div>`;
    renderSettings(view.querySelector('.settings-host'));
  }else{view.innerHTML='<div class="tool-host"></div>';renderTool(id,view.firstElementChild);}
}
window.addEventListener('hashchange',()=>{setMenu(false);draw();window.scrollTo(0,0)});
window.addEventListener('studio-open-forecast',event=>{
  const {result,flags,route}=event.detail||{};
  if(!result?.matches?.[0]?.prediction)return;
  const origin=resolve()==='batch'?'batch':'collector';
  focusForecast={result,flags:flags||{},origin};
  const destination=route==='simulation'?'simulation':'report';
  if(resolve()===destination)draw();else location.hash=destination;
});
window.addEventListener('studio-use-data',event=>{
  const d=event.detail;
  if(!state.input||!d)return;
  if(d.type==='fixture'){
    const cutoff=[d.observed_at,d.input.as_of].filter(v=>Number.isFinite(Date.parse(v))).sort((a,b)=>Date.parse(b)-Date.parse(a))[0];
    if(!cutoff||!(Date.parse(cutoff)<Date.parse(d.input.kickoff))){toast('这份赛单缺少有效赛前采集时间，无法建立赛前对阵。');return;}
    state.input={...d.input,observed_at:d.observed_at,as_of:cutoff};
    state.extra={total:2.5,handicap:0};
  }else if(d.type==='history'){
    state.extra.history=d.data;state.flags.history=true;
  }else if(['context','snapshot'].includes(d.type)){
    if(!Number.isFinite(Date.parse(d.data.observed_at))){toast('快照缺少有效采集时间。');return;}
    if(Date.parse(d.data.observed_at)>Date.parse(state.input.as_of)){toast('快照晚于当前对阵的数据截止时间，请先核对对阵和截点。');return;}
    const key=d.type==='context'?'contexts':'snapshots';
    const docs=state.extra[key]||[];
    if(docs.some(v=>JSON.stringify(v)===JSON.stringify(d.data))){toast('此快照已在当前对阵中。');return;}
    state.extra[key]=[...docs,d.data];state.flags.snapshots=true;
    if(d.data.kind==='odds')state.flags.odds=true;
    if(d.data.kind==='ratings')state.flags.ratings=true;
  }else return;
  location.hash='single';changed();toast(d.type==='fixture'?'赛程已载入单场预测':'资料已加入当前对阵');
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')setMenu(false)});
document.querySelector('#dialog').onclick=e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.currentTarget.close();}};
async function boot(){
  draw();
  try{
    const examples=await api('examples');state.examples=examples;Object.assign(state,demoData(examples));
    try{
      const draft=JSON.parse(localStorage.getItem('touchline.draft'));
      if(draft?.input?.home&&draft.input.away&&draft.extra)Object.assign(state,{input:draft.input,extra:draft.extra});
    }catch{}
    state.connected=true;draw();await run(true);
  }catch(e){view.innerHTML=`<h1>工作台暂时无法打开</h1><p>${esc(e.message)}</p><button class="primary" id="retry">重新连接</button>`;view.querySelector('#retry').onclick=boot;}
}
boot();
