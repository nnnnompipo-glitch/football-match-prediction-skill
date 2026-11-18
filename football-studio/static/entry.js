import {esc, teamName} from './ui.js';

const fields = {evidence:'evidence', scenarios:'scenarios', roles:'roles', rules:'rule_inputs'};
const types = {availability:'出场情况', lineup:'首发阵容', suspension:'停赛', fitness:'身体状态', tactics:'战术变化', other:'其他情报'};
const roles = {data:'数据分析', tactics:'战术分析', news:'新闻研判', market:'市场分析', synthesis:'综合研判'};
const attr = key => `form="detached-entry-fields" data-entry-field="${key}"`;
const options = pairs => pairs.map(([v,t])=>`<option value="${esc(v)}">${esc(t)}</option>`).join('');
const select = (key,label,pairs) => `<label>${label}<select ${attr(key)}>${options(pairs)}</select></label>`;
const input = (key,label,attrs='') => `<label>${label}<input ${attr(key)} ${attrs}></label>`;
const number = (key,label,min,max) => input(key,label,`type="number" step="any" min="${min}" max="${max}"`);
const teams = draft => ['home','away'].map(side=>[draft.input[side], `${side==='home'?'主队':'客队'} · ${teamName(draft.input,side)||'未填写'}`]);
const hint = text => `<p class="hint wide">${text}</p>`;
const timeValue = iso => Number.isFinite(Date.parse(iso)) ? new Date(Date.parse(iso)+8*3600000).toISOString().slice(0,19) : '';

function sourceFields(draft) {
  const limit = timeValue(draft.input.as_of);
  return input('source','来源名称或链接','type="text" placeholder="填写实际使用的公告、新闻或记录"') +
    input('observed','获知时间（UTC+8）',`type="datetime-local" step="1" max="${limit}"`) +
    hint(`仅录入已核验的信息。数据截止时间为 ${esc(limit.replace('T',' '))}（UTC+8）。`);
}
function scenarioFields(type,draft) {
  if(type==='ground')return select('venue','假设场地',[['neutral','中立场'],['home','常规主场']]);
  if(type==='xg')return number('homeXg','主队预估进球（xG）',0.05,8)+number('awayXg','客队预估进球（xG）',0.05,8)+hint('可填一方或双方，每队范围为 0.05 至 8。留空的一方沿用基线。');
  return select('side','受影响球队',teams(draft)) + input('event','球员或事件名称','type="text"') +
    number('delta','对该队进球的影响（ΔxG）',-8,8) + hint('输入你对缺阵影响的估计。负数会下调该队预期进球，每条最多调整 0.35 xG。本条将标为用户假设。');
}
function ruleFields() {
  return number('motivation','战意评分（0–100）',0,100) + number('odds_trend','赔率走势评分（0–100）',0,100) +
    number('form','近期状态评分（0–100）',0,100) + hint('分数越高表示该因素越支持你的判断。三个分数用于计算独立规则指数。') +
    `<label class="checkline"><input type="checkbox" ${attr('late_season')}>赛季末，提高战意权重</label>
     <label class="checkline"><input type="checkbox" ${attr('popular')}>热门修正，指数乘以 0.85</label>`;
}
export function builder(tab,draft) {
  if(!fields[tab])return '';
  let form, title, action;
  if(tab==='evidence') {
    title='填写已核验情报'; action='添加情报';
    form=select('side','受影响球队',teams(draft)) + select('kind','情报类别',Object.entries(types)) +
      input('event','球员或事件名称','type="text" placeholder="同一事件更新时沿用原名"') +
      input('note','情况说明（选填）','type="text"') + number('delta','进球调整（ΔxG）',-8,8) +
      number('confidence','置信度（0–100%）',0,100) + hint('负数下调该队预期进球，正数上调。每条调整先限制在 ±0.35 xG，再按置信度折算。') + sourceFields(draft);
  } else if(tab==='scenarios') {
    title='建立假设情景'; action='添加情景';
    form=input('name','情景名称','type="text" placeholder="为这组假设起一个唯一名称"') +
      select('type','假设内容',[['absence','球员缺阵'],['ground','变更场地'],['xg','变更预估进球']]) +
      `<div class="form-grid wide" data-scenario-fields>${scenarioFields('absence',draft)}</div>`;
  } else if(tab==='roles') {
    title='填写一份判断'; action='添加判断';
    form=select('role','判断角度',Object.entries(roles)) + number('home','主胜概率（%）',0,100) +
      number('draw','平局概率（%）',0,100) + number('away','客胜概率（%）',0,100) +
      hint('仅填常规时间胜平负，三项合计应为 100%。同一角度的多次判断以最新记录为准。') + sourceFields(draft);
  } else {
    title='设置规则指数'; action='应用评分'; form=ruleFields();
  }
  return `<section class="entry-box wide" data-entry="${tab}"><h3>${title}</h3><div class="form-grid">${form}</div>
    <div class="entry-actions"><button type="button" class="secondary" data-entry-apply>${action}</button>
    <span class="hint" role="status" aria-live="polite" data-entry-feedback></span></div></section>`;
}

export function bindBuilder(host,tab,draft,showError) {
  const key=fields[tab];
  if(!key)return;
  const box=host.querySelector(`[data-entry="${tab}"]`), target=host.querySelector(`textarea[data-dest][name="${key}"]`);
  if(!box || !target)return;
  const get = k=>box.querySelector(`[data-entry-field="${k}"]`);
  const text = (k,label)=>{const value=get(k).value.trim();if(!value)throw Error(`请填写${label}。`);return value;};
  const num = (k,label)=>{
    const el=get(k),value=Number(text(k,label));
    if(!Number.isFinite(value)||value<Number(el.min)||value>Number(el.max))throw Error(`${label}须为 ${el.min} 至 ${el.max} 之间的数字。`);
    return value;
  };
  const feedback=box.querySelector('[data-entry-feedback]');
  let pending=false;
  function read() {
    if(!target.value.trim())return tab==='rules'?{}:[];
    let data;try{data=JSON.parse(target.value);}catch{throw Error('已有 JSON 格式有误，请先修正后再添加。');}
    if(tab==='rules'?data===null||typeof data!=='object'||Array.isArray(data):!Array.isArray(data))throw Error(tab==='rules'?'规则输入须为对象。':'已有记录须为数组。');
    return data;
  }
  function provenance() {
    const source=text('source','来源'), time=text('observed','获知时间');
    const ts=Date.parse(time+'+08:00');
    if(!Number.isFinite(ts)||ts>Date.parse(draft.input.as_of))throw Error('获知时间须有效且不能晚于数据截止时间。');
    return {source,observed_at:new Date(ts).toISOString()};
  }
  function scenario(records) {
    const name=text('name','情景名称');
    if(records.some(row=>row?.name===name))throw Error('情景名称已存在，请填写不同名称。');
    const type=get('type').value;
    if(type==='ground')return {name,neutral:get('venue').value==='neutral'};
    if(type==='xg') {
      const result={name};
      if(get('homeXg').value!=='')result.home_xg=num('homeXg','主队预估进球');
      if(get('awayXg').value!=='')result.away_xg=num('awayXg','客队预估进球');
      if(Object.keys(result).length===1)throw Error('请至少填写一方的预估进球。');
      return result;
    }
    const event=text('event','球员或事件名称'),team=text('side','球队');
    return {name,evidence:[{team,kind:'availability',event_id:event,delta_xg:num('delta','进球调整'),confidence:1,
      source:'用户情景假设',observed_at:draft.input.as_of,note:`假设${event}缺阵`}]};
  }
  function apply() {
    try {
      const data=read();
      if(tab==='rules') {
        for(const k of ['motivation','odds_trend','form'])data[k]=num(k,'规则评分')/100;
        for(const k of ['late_season','popular'])data[k]=get(k).checked;
      } else if(tab==='scenarios')data.push(scenario(data));
      else if(tab==='roles') {
        const probs=['home','draw','away'].map(k=>num(k,'胜平负概率')/100);
        if(Math.abs(probs.reduce((a,b)=>a+b,0)-1)>0.01500001)throw Error('胜平负合计应为 100%，允许 1.5 个百分点的舍入误差。');
        const record={role:get('role').value,market:'1x2_90',probs,...provenance()};
        if(data.some(r=>r?.role===record.role && Date.parse(r.observed_at)===Date.parse(record.observed_at)))throw Error('这个角度在同一时间已有判断，请检查原记录或填写新的获知时间。');
        data.push(record);
      } else {
        const record={team:text('side','球队'),kind:get('kind').value,event_id:text('event','球员或事件名称'),
          delta_xg:num('delta','进球调整'),confidence:num('confidence','置信度')/100,...provenance()};
        if(get('note').value.trim())record.note=get('note').value.trim();
        if(data.some(r=>r?.team===record.team && r?.kind===record.kind && (r?.event_id||r?.source)===record.event_id && Date.parse(r?.observed_at)===Date.parse(record.observed_at)))throw Error('该事件在同一时间已有记录。');
        data.push(record);
      }
      target.value=JSON.stringify(data,null,2);target.dispatchEvent(new Event('input',{bubbles:true}));
      feedback.textContent=tab==='rules'?'评分已写入，点击保存设置生效。':`已写入，共 ${data.length} 条。点击保存设置生效。`;
      const oldError=host.querySelector('#edit-error');if(oldError)oldError.hidden=true;
      pending=false;
      return true;
    } catch(error) {feedback.textContent=error.message;showError?.(error.message);return false;}
  }
  function syncRule() {
    try {
      const data=read();
      for(const k of ['motivation','odds_trend','form'])get(k).value=typeof data[k]==='number'?String(Number((data[k]*100).toFixed(6))):'';
      for(const k of ['late_season','popular'])get(k).checked=!!data[k];
    } catch { /* Preserve the advanced editor contents while the user is typing. */ }
  }
  if(tab==='rules'){syncRule();target.addEventListener('input',syncRule);}
  if(tab==='scenarios')get('type').addEventListener('change',()=>{box.querySelector('[data-scenario-fields]').innerHTML=scenarioFields(get('type').value,draft);});
  box.addEventListener('input',event=>{
    if(tab==='rules'||event.target.tagName==='INPUT'||Array.from(box.querySelectorAll('input')).some(el=>el.value!==''))pending=true;
  });
  function flush(event) {
    if(!pending||apply())return;
    event.preventDefault();event.stopImmediatePropagation();
    if(event.target.id==='editor-section')event.target.value=tab;
  }
  host.querySelector('#editor')?.addEventListener('submit',flush,true);
  host.querySelector('#editor-section')?.addEventListener('change',flush,true);
  box.querySelector('[data-entry-apply]').addEventListener('click',apply);
  box.addEventListener('keydown',ev=>{if(ev.key==='Enter'&&ev.target.tagName==='INPUT'){ev.preventDefault();apply();}});
}
