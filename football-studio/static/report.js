import {esc,icon,pct,teamName,stamp,download,modules,displayName,nameMarkup,sourceMarkup} from './ui.js';
import {mountAnalysis} from './ai.js';
const labels=['主胜','平局','客胜'];
function rows(data){
  return `<div class="result-rows">${data.map(([label,value])=>`<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('')}</div>`;
}
function card(title,mark,body,wide=false){
  return `<section class="result-card ${wide?'span-all':''}"><h3>${icon(mark,17)} ${title}</h3>${body}</section>`;
}
function probabilities(arr,names=labels){
  return arr.map((n,i)=>`<div class="prob-row"><span>${esc(names[i])}</span><i><b style="width:${Number(n)*100}%"></b></i><strong>${pct(n)}</strong></div>`).join('');
}
function raw(data){return `<details class="raw"><summary>查看原始记录</summary><pre>${esc(JSON.stringify(data,null,2))}</pre></details>`;}
export function report(container,result,flags){
  const m=result.matches[0],p=m.prediction,i=m.input,home=teamName(i,'home'),away=teamName(i,'away');
  const knownTeam=name=>name===i.home?home:name===i.away?away:name;
  const blocks=[
    card('常规时间胜平负','circlechart',`<div class="prob-chart">${probabilities(p.probs)}</div>${rows([['基础模型',p.base_probs.map(pct).join(' / ')],['期望进球（主 / 客）',p.expected_goals.map(v=>v.toFixed(2)).join(' / ')]])}`),
    card('候选比分','pitch',p.top_scores.map(s=>`<div class="score-line"><b>${s.home} : ${s.away}</b><span>${pct(s.p)}</span></div>`).join(''))
  ];
  if(flags.history && m.form) blocks.push(card('近期表现与交锋','chart',rows(Object.entries(m.form.teams).map(([name,t])=>[knownTeam(name),`近 ${t.n} 场 · ${t.W} 胜 ${t.D} 平 ${t.L} 负`]).concat([['可用历史赛果',p.eligible_history+' 场']]))+raw(m.form)));
  if(flags.evidence)blocks.push(card('阵容与伤停','health',p.evidence?.length?rows(p.evidence.map(e=>[knownTeam(displayName(e,'team'))+' · '+e.kind,`xG ${Number(e.bounded_delta_xg).toFixed(2)}`]))+raw(i.evidence):'<p class="hint">本场未提供可量化的阵容情报。</p>'));
  if(flags.odds)blocks.push(card('赔率对照','odds',rows([['参考来源',i.odds_source||'未提供'],['参考报价时间',stamp(i.odds_at)],['参考去水概率',p.market_probs?.map(pct).join(' / ')||'未提供'],['目标来源',i.target_odds_source||'未提供'],['目标报价时间',stamp(i.target_odds_at)],['目标赔率',p.target_comparison?.prices?.join(' / ')||'未提供']])+ (p.target_comparison?raw(p.target_comparison):'')));
  if(flags.ratings)blocks.push(card('实力评级','ranking',rows([[home+' · Elo',i.home_elo??'未提供'],[away+' · Elo',i.away_elo??'未提供'],['评级观测时间',stamp(i.elo_at)],['本场输入 xG',[i.home_xg??'—',i.away_xg??'—'].join(' / ')]])));
  if(flags.scenarios)blocks.push(card('情景重算','scenario',m.scenarios?.length?m.scenarios.map(s=>`<h4>${esc(s.name)}</h4>${probabilities(s.probs)}<p class="hint">相对基线（百分点） ${s.delta_pp.map(n=>(n>=0?'+':'')+n.toFixed(1)).join(' / ')}</p>`).join(''):'<p class="hint">尚未添加情景。可以在模块设置中填写假设。</p>'));
  if(flags.roles)blocks.push(card('多方判断','group',p.role_probs?probabilities(p.role_probs)+raw(p.roles):'<p class="hint">尚未提供角色意见。</p>'));
  if(flags.markets)blocks.push(card('衍生市场','target',rows([['总进球线',m.markets.total_line],['大 / 走 / 小',m.markets.over_push_under.map(pct).join(' / ')],['主队让球',m.markets.home_handicap],['让球主胜 / 平 / 客胜',m.markets.handicap_home_draw_away.map(pct).join(' / ')],['双方均进球',pct(m.markets.both_teams_score)],['零封（主 / 客）',[m.markets.home_clean_sheet,m.markets.away_clean_sheet].map(pct).join(' / ')]])));
  if(m.advancement)blocks.push(card('晋级概率','cup',probabilities([m.advancement.home,m.advancement.away],[home,away])+rows([['90 分钟打平后主队晋级',pct(m.advancement.home_if_level_after_90)]])));
  if(flags.rules)blocks.push(card('独立规则指数','sliders',m.rule_index?rows([['评分',m.rule_index.score_100.toFixed(2)+' / 100']])+'<p class="hint">独立启发式评分，未经概率校准。</p>':'<p class="hint">尚未填写规则输入。</p>'));
  const provenance=sourceMarkup(m);
  if(provenance)blocks.push(card('数据来源与原始记录','data',provenance,true));
  if(flags.snapshots)blocks.push(card('来源快照','data',rows([['关联快照',m.sources?.snapshots?.length||0],['上游预测',m.sources?.upstream?.length||0],['报价记录',m.sources?.quote_history?.length||0],['研究资料',i.research_context?.length||0]])+raw({...m.sources,context:i.research_context||[]})));
  if(flags.training)blocks.push(card('拟合与校准','layers',rows([['概率温度',p.temperature],['进球均值来源',p.strength?.rate_sources?.join(' / ')||'—']])+(i.calibration_provenance?raw(i.calibration_provenance):'')));
  if(m.timeline)blocks.push(card('半场与时间线','clock',`<div class="two-panel"><div><h4>半场胜平负</h4>${probabilities(m.timeline.half_probs)}<h4>半场候选比分</h4>${rows(m.timeline.half_top_scores.map(s=>[s.home+' : '+s.away,pct(s.p)]))}</div><div><h4>时段内至少一球</h4>${probabilities(m.timeline.periods.map(s=>s.p_at_least_one_goal),m.timeline.periods.map(s=>s.start_minute+'–'+s.end_minute+'′'))}<p class="hint">${esc(m.timeline.assumption)}</p></div></div>`,true));
  if(p.score_matrix){
    const matrix=p.score_matrix,max=Math.max(...matrix.flat());
    blocks.push(card('比分概率矩阵','matrix',`<p class="hint">行是主队进球数，列是客队进球数。颜色越深，概率越高。</p><div class="matrix-scroll" tabindex="0"><table class="heatmap"><thead><tr><th>主 / 客</th>${matrix[0].map((_,n)=>`<th>${n}</th>`).join('')}</tr></thead><tbody>${matrix.map((r,n)=>`<tr><th>${n}</th>${r.map(v=>`<td style="background:rgba(146,207,116,${(.04+.82*v/max).toFixed(3)})" title="${pct(v)}">${pct(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`,true));
  }
  if(p.warnings?.length)blocks.push(card('数据缺口','flag',p.warnings.map(w=>`<p>${esc(w)}</p>`).join(''),true));
  container.innerHTML=`<div class="page-head"><div><div class="eyebrow"><i></i> FORECAST REPORT</div><h1>预测报告</h1><p>${nameMarkup(i,"home")} vs ${nameMarkup(i,"away")} · ${i.demo?'虚构演示 · ':''}常规时间 90 分钟</p><p>${nameMarkup(i,"competition")}${i.stage?" · "+nameMarkup(i,"stage"):""}</p></div><div class="head-actions"><a class="primary" href="#simulation">${icon('play',15)} 播放比赛模拟</a><button class="secondary" data-json>${icon('report',16)} 导出 JSON</button><button class="secondary" data-html>${icon('external',16)} 导出 HTML</button></div></div>
  <div class="report-stamp">${icon('clock',16)} 数据截止 ${esc(stamp(i.as_of))} UTC+8 · 开球 ${esc(stamp(i.kickoff))} UTC+8</div><div class="result-grid">${blocks.join('')}</div><div id="ai-analysis"></div>`;
  container.querySelector('[data-json]').onclick=()=>download(JSON.stringify({...result,enabled_modules:Object.keys(flags).filter(key=>flags[key])},null,2),'赛前预测.json');
  container.querySelector('[data-html]').onclick=()=>{
    const head=container.querySelector('.page-head>div').outerHTML;
    const enabled=modules.filter(([id])=>flags[id]).map(([,label])=>label);
    const stampLine=`${container.querySelector('div.report-stamp').outerHTML}<p class="hint">原始数据截点 ${esc(i.as_of)}<br>已启用模块　${esc(enabled.join('、')||'无')}</p>`;
    const answer=container.querySelector('.ai-answer:not([hidden])');
    const ai=answer?`<section><h3>${esc(answer.querySelector('h3').textContent)}</h3><p class="answer">${esc(answer.querySelector('div').textContent)}</p></section>`:'';
    const html=`<!doctype html><html lang="zh-Hans"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(home)} vs ${esc(away)} · 赛前报告</title>
    <style>*{box-sizing:border-box}body{max-width:1050px;margin:auto;padding:30px 18px;color:#203e2b;background:#f6f7f3;font:15px/1.7 system-ui,'Microsoft YaHei',sans-serif}.eyebrow,.hint,.report-stamp{color:#536d5a;font-size:13px}h1,h3{margin:5px 0}h3 svg{vertical-align:middle}.report-stamp{margin:12px 0}.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,310px),1fr));gap:12px}section{min-width:0;padding:16px;border:1px solid #d9e1d6;border-radius:12px;background:white}.span-all{grid-column:1/-1}.result-rows>div,.score-line,.prob-row{display:flex;justify-content:space-between;gap:10px;padding:4px 0;border-bottom:1px solid #edf1eb}.prob-row>i{flex:1;align-self:center;background:#e4eddf;height:6px}.prob-row b{display:block;background:#78a474;height:100%}.prob-row strong{width:52px;text-align:right}.matrix-scroll{overflow:auto}.heatmap{font-size:12px;text-align:center}.heatmap td,.heatmap th{padding:3px}.name-provisional{display:inline-block;margin-left:5px;padding:0 4px;border-radius:3px;background:#f4eddc;color:#7a6338;font-size:10px;font-weight:500}.source-meta{display:grid;gap:7px;margin:10px 0}.source-meta>div{display:grid;grid-template-columns:90px minmax(0,1fr);gap:8px;overflow-wrap:anywhere}.source-links{display:flex;flex-wrap:wrap;gap:8px 18px;margin:10px 0}.source-link{color:#276042;overflow-wrap:anywhere}pre,.answer{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer;color:#537159}details{margin-top:8px}svg{width:16px;height:16px}@media print{section{break-inside:avoid}.heatmap{font-size:9px}body{padding:0;background:white}}</style>
    <main>${head}${stampLine}<div class="result-grid">${blocks.join('')}</div>${ai}</main></html>`;
    download(html,'赛前预测.html','text/html;charset=utf-8');
  };
  if(flags.ai) mountAnalysis(container.querySelector('#ai-analysis'),result,`单场赛前预测 · ${home} 对 ${away}`);
}
