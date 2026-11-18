import {api, esc, icon, pct, stamp, teamName,displayName,originalName,safeSourceUrl} from './ui.js';
import {mountSimulator} from './sim-pitch.js';

export function renderMatchroom(container, match, origin='desk'){
  const {input, prediction}=match;
  const home=teamName(input,'home'), away=teamName(input,'away');
  const alternatives=prediction.top_scores.map((score,index)=>
    `<option value="${index}">指定 ${score.home}∶${score.away} · ${pct(score.p)}</option>`).join('');
  const competition=displayName(input,'competition');
  const provisional=['home','away','competition'].filter(key=>input.translation?.[key]?.provisional);
  const source=safeSourceUrl(input.source_url||input.provenance?.web_url);
  container.innerHTML=`<div class="page-head matchroom-head"><div><div class="eyebrow"><i></i> MATCH THEATRE</div>
    <h1>比赛演播室</h1><p title="${esc(originalName(input,'competition'))}">${esc(competition||'单场预测')} · ${esc(stamp(input.kickoff))} UTC+8${input.demo?' · 虚构演示':''}</p></div>
    <div class="head-actions">${source?`<a class="secondary" href="${esc(source)}" target="_blank" rel="noopener noreferrer">${icon('external',15)} 比赛来源</a>`:''}<a class="secondary" href="#${origin}">${origin==='collector'?'返回采集赛程':origin==='batch'?'返回比赛日':'返回工作台'}</a><a class="secondary" href="#report">${icon('report',15)} 预测报告</a></div></div>
    ${provisional.length?`<p class="sim-mode-note">部分名称为自动音译，待核验。来源原名：${provisional.map(key=>esc(originalName(input,key))).join(' / ')}</p>`:''}
    <div class="sim-frame"><div class="matchroom-options"><label for="sim-selection">推演方式</label>
      <select id="sim-selection"><option value="likely">演绎最高概率比分</option><option value="random">按全比分概率随机抽样</option>${alternatives}</select>
      <span class="sim-mode-note">90 分钟 · 模拟画面</span></div><div data-stadium></div></div>
    <section class="sim-basis"><div><h2>本场预测依据</h2><p>比分取自本场预测的完整分布，进球分钟与攻防动作由模拟生成。</p></div>
      <div class="sim-team-stat" title="${esc(originalName(input,'home'))}"><span>${esc(home)} · 主胜</span><strong>${pct(prediction.probs[0])}</strong><small>预计进球 ${prediction.expected_goals[0].toFixed(2)}</small></div>
      <div class="sim-team-stat"><span>平局</span><strong>${pct(prediction.probs[1])}</strong></div>
      <div class="sim-team-stat" title="${esc(originalName(input,'away'))}"><span>${esc(away)} · 客胜</span><strong>${pct(prediction.probs[2])}</strong><small>预计进球 ${prediction.expected_goals[1].toFixed(2)}</small></div></section>`;
  const slot=container.querySelector('[data-stadium]'), selector=container.querySelector('#sim-selection');
  let ticket=0, player=null, closed=false;
  async function loadRound(){
    const request=++ticket;
    player?.destroy();player=null;
    slot.innerHTML='<p class="loading" role="status">正在根据本场预测生成比赛…</p>';
    const chosen=prediction.top_scores[Number(selector.value)];
    const selection=selector.value==='likely'?'most_likely':selector.value==='random'?'sample':[chosen.home,chosen.away];
    try{
      const sim=await api('simulation',{home,away,selection,prediction:{
        model_goal_means:prediction.model_goal_means,probs:prediction.probs,rho_used:prediction.rho_used}});
      if(closed||request!==ticket)return;
      player=mountSimulator(slot,sim,{autoplay:!window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        onResample:()=>{selector.value='random';loadRound();}});
    }catch(err){
      if(closed||request!==ticket)return;
      slot.innerHTML=`<div class="sim-error" role="alert"><p>${esc(err.message)}</p><button class="secondary">重新生成动画</button></div>`;
      slot.querySelector('button').onclick=loadRound;
    }
  }
  selector.addEventListener('change',loadRound);
  loadRound();
  return ()=>{closed=true;ticket++;player?.destroy();};
}
