import {esc,icon,modules,defaultFlags,toast} from './ui.js';
import {builder,bindBuilder} from './entry.js';

const params = [
  ['simulation','','比赛动画','','info','启用后，运行预测会直接进入比赛演播室。可播放最高概率比分、选择候选比分或重新随机模拟。'],
  ['history','history','历史赛果','extra','json','赛果数组或包含 records 的 JSON。'],
  ['evidence','evidence','已核验情报','input','json','每条填写 team、kind、delta_xg、confidence、source 和 observed_at。'],
  ['odds','odds','参考赔率（主／平／客）','input','triplet'],
  ['odds','odds_source','参考公司','input','text'],['odds','odds_at','参考报价时间','input','time'],
  ['odds','target_odds','目标赔率（主／平／客）','input','triplet'],
  ['odds','target_odds_source','目标公司','input','text'],['odds','target_odds_at','目标报价时间','input','time'],
  ['odds','market_weight','参考赔率融合权重','input','number','0 至 1'],
  ['odds','bookmaker','快照中的参考公司键','extra','text'],
  ['scenarios','scenarios','假设情景','extra','json','带唯一 name 的数组，可修改 xG、Elo、证据或权重。'],
  ['timeline','','时间线口径','','info','开启后，报告将显示半场胜平负、半场候选比分和六个 15 分钟时段的进球概率。'],
  ['matrix','','矩阵口径','','info','开启后，报告将展示全部比分格。行表示主队进球，列表示客队进球。'],
  ['ratings','home_elo','主队 Elo','input','number'],['ratings','away_elo','客队 Elo','input','number'],['ratings','elo_at','评级观测时间','input','time'],
  ['ratings','home_xg','主队本场预估 xG','input','number'],['ratings','away_xg','客队本场预估 xG','input','number'],['ratings','xg_at','xG 观测时间','input','time'],
  ['roles','roles','角色概率与来源','input','json','每条提供 role、market、probs、source、observed_at。'],['roles','role_weight','角色融合权重','input','number','0 至 1'],
  ['markets','total','总进球线','extra','number','整数或半球线'],['markets','handicap','主队整数让球','extra','number','例：−1 表示主队让一球'],
  ['knockout','decider_home','90 分钟战平后主队晋级概率','input','number','可选，范围 0 至 1'],
  ['rules','rule_inputs','独立规则指数输入','input','json','motivation、odds_trend、form 为 0 至 1 的判断。'],
  ['snapshots','snapshots','评级、赔率、上游预测快照','extra','json','输入快照数组；导入单个快照文件后自动装入数组。'],
  ['snapshots','contexts','名单、伤停、新闻、天气等资料','extra','json','输入快照数组；导入前核对对阵、球场和开球时间。'],
  ['snapshots','aliases','球队别名映射','extra','json','示例：{"Harbor FC":"Harbor XI"}'],
  ['snapshots','accept_clubelo_date','已核对旧 ClubElo 快照中的主客队和 UTC 日期','input','check'],
  ['training','fit','攻防拟合结果','extra','json','可从 Elo 实力榜 → 攻防拟合下载结果。'],['training','calibration','温度校准结果','extra','json','可从滚动回测的校准结果导入。'],
  ['ledger','','冻结时机','','info','开启后，手动运行预测会将该次输入和结果写入本机台账。'],
  ['ai','','模型服务','','info','开启后，在预测报告中点击生成解读。可在侧栏设置中填写模型、服务地址和 API Key。'],
];
export function buildPayload(state, automatic=false){
  const input=structuredClone(state.input), extras=state.extra, flags=state.flags;
  for(const [group,key,,dest] of params) if(key && dest==='input' && !flags[group]) delete input[key];
  if(input.observed_at && !(Date.parse(input.observed_at)<=Date.parse(input.as_of))) throw Error('数据截止时间不能早于赛单快照的采集时间。');
  if(!flags.odds){input.market_weight=0;}
  if(!flags.roles){input.role_weight=0;}
  if(!flags.snapshots) delete input.research_context;
  if(!flags.training){delete input.temperature;delete input.fit_provenance;delete input.calibration_provenance;}
  input.knockout=!!flags.knockout;
  const payload={input, matrix:flags.matrix, timeline:flags.timeline, knockout:flags.knockout,ledger:!!flags.ledger&&!automatic};
  for(const [group,key,,dest] of params) if(dest==='extra'&&flags[group]&&extras[key]!=null&&extras[key]!=='') payload[key]=extras[key];
  if(payload.snapshots) payload.snapshots=payload.snapshots.filter(s=>(s.kind!=='odds'||flags.odds)&&(s.kind!=='ratings'||flags.ratings));
  if(payload.calibration && !flags.history) throw Error('温度校准需要配套历史数据，请启用「历史战绩」。');
  if(payload.scenarios?.length===0) delete payload.scenarios;
  return payload;
}
export function demoData(examples){
  return {input:structuredClone(examples.match),extra:{history:examples.history,scenarios:examples.scenarios,total:2.5,handicap:0}};
}
function newData(){
  const now=new Date(),kick=new Date(now.getTime()+86400000);
  return {input:{home:'',away:'',competition:'',as_of:now.toISOString(),kickoff:kick.toISOString(),market:'1x2_90'},extra:{total:2.5,handicap:0}};
}
function localTime(v){
  if(!v||!Number.isFinite(Date.parse(v))) return '';
  return new Date(Date.parse(v)+8*3600000).toISOString().slice(0,19);
}
function dateValue(v,original){
  if(!v)return undefined;
  if(original && Date.parse(v+'+08:00')===Date.parse(localTime(original)+'+08:00'))return original;
  return new Date(v+'+08:00').toISOString();
}
function basic(s){
  return `<div class="form-grid">${[['home','主队'],['away','客队'],['competition','赛事名称'],['stage','比赛阶段']].map(([k,l])=>`<label>${l}<input name="${k}" value="${esc(s.input[k])}" ${['home','away'].includes(k)?'required':''}></label>`).join('')}
  ${[['kickoff','开球时间'],['as_of','数据截止时间']].map(([k,l])=>`<label>${l}（UTC+8）<input name="${k}" type="datetime-local" step="1" required value="${localTime(s.input[k])}"></label>`).join('')}
  <label class="checkline"><input type="checkbox" name="neutral" ${s.input.neutral?'checked':''}>中立场地</label>
  <label>低比分相关系数 ρ<input name="rho" type="number" step="any" placeholder="引擎默认" value="${esc(s.input.rho)}"></label></div>`;
}
function field(spec,s){
  const [,key,label,dest,type,hint]=spec, value=s[dest]?.[key], attr=`data-dest="${dest}" data-type="${type}" name="${key}"`;
  if(type==='info')return `<p class="hint">${esc(hint)}</p>`;
  if(type==='check')return `<label class="checkline"><input ${attr} type="checkbox" ${value?'checked':''}>${label}</label>`;
  if(type==='json')return `<label class="wide">${label}<textarea ${attr} rows="5" spellcheck="false" placeholder="粘贴 JSON 或从文件导入">${value==null?'':esc(JSON.stringify(value,null,2))}</textarea><span class="hint">${esc(hint)}</span></label><label class="pick-file">${icon('upload',14)} 读取 JSON 文件<input type="file" data-for="${key}" accept=".json,application/json"></label>`;
  const v=type==='triplet'?(value||[]).join(', '):type==='time'?localTime(value):value??'';
  return `<label>${label}${type==='time'?'（UTC+8）':''}<input ${attr} type="${type==='time'?'datetime-local':type==='number'?'number':'text'}" step="${type==='time'?'1':'any'}" value="${esc(v)}" placeholder="${esc(hint||'可选')}"></label>`;
}
export function editMatch(state,onSave,initial='match'){
  const dlg=document.querySelector('#dialog'),body=document.querySelector('#dialog-body');
  let draft={input:structuredClone(state.input),extra:structuredClone(state.extra),flags:{...state.flags}},tab=initial;
  const options=modules.map(([id,label])=>`<option value="${id}">${label}</option>`).join('');
  function paint(){
    const guided=builder(tab,draft);
    const inputs=`<div class="form-grid">${params.filter(p=>p[0]===tab).map(p=>field(p,draft)).join('')}</div>`;
    const moduleInputs=guided?`${guided}<details class="entry-advanced"><summary>编辑原始记录与导入 JSON</summary>${inputs}</details>`:inputs;
    body.innerHTML=`<div class="dialog-head"><div class="eyebrow">MATCH SETUP</div><button class="icon-btn" data-close aria-label="关闭">${icon('close')}</button></div><h2>对阵与分析设置</h2>
      <label class="editor-select">配置项目<select id="editor-section"><option value="match">对阵资料</option>${options}<option value="import">导入对阵 / 完整配置</option></select></label>
      <form id="editor"><div id="editor-fields">${tab==='match'?basic(draft):tab==='import'?`<label>对阵 JSON 或完整预测请求<textarea id="json-input" rows="9" spellcheck="false" placeholder='{"home":"主队","away":"客队","kickoff":"…","as_of":"…"}'></textarea></label><label class="pick-file">${icon('upload',14)} 读取 JSON 文件<input type="file" data-for="json-input" accept=".json"></label><p class="hint">支持单场对象或含 input 的配置。若要分析多场，请使用比赛日分析。</p>`:
      `<label class="checkline enable"><input name="enabled" type="checkbox" ${draft.flags[tab]?'checked':''}>本次预测启用${modules.find(m=>m[0]===tab)[1]}</label>${moduleInputs}`}</div>
      <p class="error" role="alert" id="edit-error" hidden></p><div class="dialog-foot">${tab==='match'?`<div><button type="button" class="text-btn" id="new-match">新建空白对阵</button><button type="button" class="text-btn" id="restore-demo">载入演示</button></div>`:''}<button type="submit" class="primary">保存设置 ${icon('check',15)}</button></div></form>`;
    body.querySelector('#editor-section').value=tab;
    bindBuilder(body,tab,draft,error);
    body.querySelector('[data-close]').onclick=()=>dlg.close();
    body.querySelectorAll('[data-for]').forEach(file=>file.onchange=async()=>{
      const f=file.files[0];if(!f)return;
      try {
        const json=JSON.parse((await f.text()).replace(/^\uFEFF/,''));
        const key=file.dataset.for; const obj=['snapshots','contexts'].includes(key)&&!Array.isArray(json)?[json]:json;
        const el=body.querySelector(`[name="${key}"], #${key}`);el.value=JSON.stringify(obj,null,2);el.dispatchEvent(new Event('input',{bubbles:true}));
      }catch(e){error('文件无法读取为 JSON。'+e.message);}
    });
    body.querySelector('#new-match')?.addEventListener('click',()=>{Object.assign(draft,newData());paint();body.querySelector('[name=home]').focus()});
    body.querySelector('#restore-demo')?.addEventListener('click',()=>{Object.assign(draft,demoData(state.examples),{flags:{...defaultFlags}});paint()});
    body.querySelector('#editor-section').onchange=e=>{
      const previous=structuredClone(draft);
      try {read();tab=e.target.value;paint();}catch(ex){draft=previous;e.target.value=tab;error(ex.message);}
    };
    body.querySelector('#editor').onsubmit=e=>{e.preventDefault();const previous=structuredClone(draft);try{
      read();if(!draft.input.home?.trim()||!draft.input.away?.trim()||draft.input.home===draft.input.away)throw Error('请填写两个不同的球队名称。');
      if(!(Date.parse(draft.input.as_of)<Date.parse(draft.input.kickoff)))throw Error('数据截止时间必须早于开球时间。');
      if(draft.input.observed_at && Date.parse(draft.input.as_of)<Date.parse(draft.input.observed_at))throw Error('数据截止时间不能早于赛单快照的采集时间。');
      onSave(draft);dlg.close();toast('已保存对阵与分析设置');
    }catch(ex){draft=previous;error(ex.message)}};
  }
  function error(msg){const el=body.querySelector('#edit-error');el.hidden=false;el.textContent=msg;}
  function read(){
    const form=body.querySelector('form');
    if(tab==='match'){
      const values=new FormData(form),home=values.get('home').trim(),away=values.get('away').trim();
      if(draft.input.demo && (home!==draft.input.home||away!==draft.input.away)){
        Object.assign(draft,newData());
      }
      Object.assign(draft.input,{home,away,competition:values.get('competition').trim(),stage:values.get('stage').trim(),neutral:values.has('neutral'),kickoff:dateValue(values.get('kickoff'),draft.input.kickoff),as_of:dateValue(values.get('as_of'),draft.input.as_of)});
      if(draft.input.observed_at && Date.parse(draft.input.as_of)<Date.parse(draft.input.observed_at))throw Error('数据截止时间不能早于赛单快照的采集时间。');
      if(values.get('rho')!=='')draft.input.rho=Number(values.get('rho'));else delete draft.input.rho;
    }else if(tab==='import'){
      const raw=body.querySelector('#json-input').value.trim();if(!raw)return;
      const data=JSON.parse(raw),input=data?.input??data;
      if(typeof input?.home!=='string'||typeof input?.away!=='string')throw Error('单场 JSON 必须包含 home 和 away。');
      draft.input=input;draft.extra={total:2.5,handicap:0};
      for(const [group,key,,dest] of params) if(key){
        if(dest==='extra' && data.input && data[key]!=null){draft.extra[key]=data[key];draft.flags[group]=true;}
        if(dest==='input' && input[key]!=null)draft.flags[group]=true;
      }
      for(const key of ['matrix','timeline','knockout','ledger'])if(typeof data[key]==='boolean')draft.flags[key]=data[key];
      if(typeof input.knockout==='boolean')draft.flags.knockout=input.knockout;
    }else{
      draft.flags[tab]=form.elements.enabled.checked;
      form.querySelectorAll('[data-dest]').forEach(el=>{
        const {dest,type}=el.dataset,k=el.name,v=el.value.trim();
        if(type==='check'){draft[dest][k]=el.checked;return;}
        if(!v){delete draft[dest][k];return;}
        if(type==='json'){try{draft[dest][k]=JSON.parse(v);}catch{throw Error('请检查「'+params.find(p=>p[1]===k)[2]+'」的 JSON 格式。');}}
        else if(type==='triplet'){const arr=v.split(/[\s,，/]+/).map(Number);if(arr.length!==3||arr.some(n=>!Number.isFinite(n)||n<=1))throw Error('赔率需要填写三个大于 1 的数字。');draft[dest][k]=arr;}
        else draft[dest][k]=type==='time'?dateValue(v,draft[dest][k]):type==='number'?Number(v):v;
      });
    }
  }
  paint();if(!dlg.open)dlg.showModal();
}
