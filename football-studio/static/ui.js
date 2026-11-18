const paths = {
  dashboard: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  pitch: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M12 5v14M2 9h3v6H2m20-6h-3v6h3"/><circle cx="12" cy="12" r="2.5"/>',
  batch: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18m-14 4h3m4 0h3m-10 3h3"/>',
  cup: '<path d="M8 3h8v6a4 4 0 0 1-8 0zm0 2H4v2a4 4 0 0 0 4 4m8-6h4v2a4 4 0 0 1-4 4m-4 2v5m-4 3h8m-7 0 1-3h4l1 3"/>',
  data: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  ranking: '<path d="M3 20h18M5 16v-5h4v5m1 0V4h4v12m1 0V8h4v8"/>',
  ledger: '<path d="M5 4h14v16H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2m-2 13c1-1 2-1 4-1h11M9 8h7m-7 4h5"/>',
  test: '<path d="M3 13a9 9 0 1 0 1-5l-2 2m0-5v5h5m5-4v6l4 2"/>',
  settings: '<path d="m10 3-.6 2.4-2.2 1-2.1-.8-2 3.4 1.7 1.7v2.6L3 15l2 3.5 2.3-.7 2.1 1 .6 2.2h4l.6-2.2 2.1-1 2.3.7 2-3.5-1.8-1.7v-2.6L21 9l-2-3.4-2.1.8-2.2-1L14 3z"/><circle cx="12" cy="12" r="3"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',down:'<path d="m6 9 6 6 6-6"/>',
  arrow:'<path d="M4 12h15m-6-6 6 6-6 6"/>',external:'<path d="M6 18 18 6M6 6h12v12"/>',
  play:'<path d="m7 4 13 8-13 8z"/>',edit:'<path d="m14 5 5 5M4 20l5-1L21 7l-4-4L5 15z"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  sliders:'<path d="M3 6h7m5 0h6M3 12h2m5 0h11M3 18h10m5 0h3"/><circle cx="12" cy="6" r="2"/><circle cx="7" cy="12" r="2"/><circle cx="15" cy="18" r="2"/>',
  health:'<path d="M3 10h4l3-6 4 15 3-9h4"/>',
  chart:'<path d="M3 4v16h18M6 15l4-5 4 3 6-8"/>',
  odds:'<path d="M3 18 9 12l4 3 8-10m-6 0h6v6"/>',
  matrix:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18m6-18v18M3 9h18M3 15h18"/>',
  scenario:'<circle cx="6" cy="18" r="2"/><circle cx="17" cy="5" r="2"/><path d="M6 16V9a4 4 0 0 1 4-4h5M7 15l12-1m-4-4 4 4-4 4"/>',
  ai:'<path d="m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3z"/>',
  home:'<path d="m3 10 9-7 9 7m-16 0v11h14V10m-9 11v-7h4v7"/>',
  menu:'<path d="M3 6h18M3 12h18M3 18h18"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>',
  target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  circlechart:'<path d="M12 3v9h9a9 9 0 1 1-12-8.5M15 2.8A8 8 0 0 1 21.2 9H15z"/>',
  report:'<path d="M6 3h9l4 4v14H6zM14 3v5h5M9 12h7m-7 4h5"/>',
  group:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2m0-15a3 3 0 0 1 0 6m2 3a5 5 0 0 1 4 5"/>',
  layers:'<path d="m2 8 10-5 10 5-10 5zm1 5 9 5 9-5m-18 5 9 4 9-4"/>',
  bolt:'<path d="m13 2-9 12h7l-1 8 10-13h-8z"/>',upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  check:'<path d="m4 12 5 5L20 6"/>',monitor:'<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M12 17v4m-5 0h10"/>',
  flag:'<path d="M5 21V4c5-4 9 4 14 0v10c-5 4-9-4-14 0"/>',help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 8.5a2.6 2.6 0 0 1 5 .8c0 2-2.5 2.4-2.5 4.5m0 2.3v.2"/>',
};
export const icon = (name, size=20) => `<svg class="ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]||paths.pitch}</svg>`;
export const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
export const pct = n => Number.isFinite(n) ? (n*100).toFixed(1)+'%' : '—';
export async function api(path, payload) {
  const response = await fetch('/api/'+path, payload===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const body = await response.json();
  if(!response.ok || body.error) throw new Error(body.error||'请求失败');
  return body;
}
export function download(content,name,type='application/json') {
  const url=URL.createObjectURL(new Blob([content],{type})), a=document.createElement('a');
  a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function toast(message) {
  const el=document.querySelector('#toast');el.textContent=message;el.hidden=false;
  clearTimeout(toast.timer);toast.timer=setTimeout(()=>{el.hidden=true},3200);
}
export const modules = [
  ['simulation','比赛动画','在球场上观看双方攻防和进球','play','mint',true],
  ['history','历史战绩','历史赛果、近期状态与交锋记录','chart','mint',true],
  ['evidence','阵容与伤停','核验球员状态，修正预期进球','health','peach',true],
  ['odds','赔率对照','参考盘口与目标赔率的概率差','odds','lilac',true],
  ['scenarios','情景重算','比较阵容与参数变化的影响','scenario','blue',false],
  ['matrix','比分矩阵','查看每个常规时间比分的概率','matrix','yellow',false],
  ['timeline','半场时间线','半场比分与每 15 分钟进球概率','clock','aqua',false],
  ['ratings','实力评级','使用双方赛前 Elo 或本场 xG','ranking','blue',true],
  ['roles','多方判断','汇总有来源的角色概率与权重','group','lilac',false],
  ['markets','衍生市场','总进球、整数让球与双方进球','target','peach',false],
  ['knockout','淘汰赛晋级','单列常规时间后双方晋级概率','cup','yellow',false],
  ['rules','规则指数','按战意、走势和状态生成指数','sliders','mint',false],
  ['snapshots','来源快照','关联外部预测、评级及参考资料','data','aqua',false],
  ['training','拟合与校准','导入已训练的模型与温度参数','layers','lilac',false],
  ['ledger','冻结预测','保存本次输入与结果以待结算','ledger','blue',false],
  ['ai','AI 解读','用已配置的大模型解读计算结果','ai','mint',false],
];
export const defaultFlags = Object.fromEntries(modules.map(([id,,,,,on])=>[id,on]));
export const stamp = value => {
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'—':new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Hong_Kong',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date);
};
export function originalName(input,key) {
  return typeof input?.[key]==="string" ? input[key] : "";
}
export function displayName(input,key) {
  const original=originalName(input,key), translation=input?.translation?.[key], translated=input?.[key+"_zh"];
  if(typeof translated==="string" && /[\u3400-\u9fff]/.test(translated) &&
      (translation?.original===undefined || translation.original===original)) return translated;
  const demoNames={"Harbor XI":"海港竞技","Pine XI":"松林联队","Demo League":"研究室演示联赛"};
  return input?.demo && demoNames[original] || original;
}
export function nameMarkup(input,key) {
  const provisional=nameIsProvisional(input,key);
  return `<span title="${esc(originalName(input,key))}${provisional?' · 自动音译，待核验':''}">${esc(displayName(input,key))}</span>${provisional?'<small class="name-provisional">音译待核验</small>':""}`;
}
export function nameIsProvisional(input,key) {
  const info=input?.translation?.[key];
  return Boolean(info && info.original===originalName(input,key) &&
    (info.provisional || info.method==="offline-transliteration"));
}
export function nameTerms(input,key) {
  const info=input?.translation?.[key];
  const current=info?.original===undefined || info.original===originalName(input,key);
  const aliases=current && Array.isArray(input?.[key+"_aliases"])?input[key+"_aliases"]:[];
  return [...new Set([originalName(input,key),displayName(input,key),...aliases].filter(v=>typeof v==="string"&&v.trim()))];
}
export function searchNameText(value) {
  return String(value??"").normalize("NFKD").replace(/\p{M}/gu,"").toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu,"");
}
export function fixtureMatchesSearch(input,query) {
  const wanted=String(query||"").trim().split(/\s+/).map(searchNameText).filter(Boolean);
  const available=["home","away","competition"].flatMap(key=>nameTerms(input,key)).map(searchNameText);
  return wanted.every(term=>available.some(name=>name.includes(term)));
}
export function teamName(input,key) {
  return displayName(input,key);
}
export function safeSourceUrl(value) {
  if(typeof value!=="string" || !/^https?:\/\//i.test(value))return "";
  try {
    const url=new URL(value);
    return ["http:","https:"].includes(url.protocol) && !url.username && !url.password ? url.href : "";
  } catch {return "";}
}
export function sourceLink(value,label) {
  const url=safeSourceUrl(value);
  return url?`<a class="source-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ${icon("external",12)}</a>`:"";
}
function provenanceOf(record) {
  return record?.provenance || record?.input?.provenance || record?.sources?.provenance || record?.collection?.provenance || {};
}
export function sourceMarkup(record,{compact=false}={}) {
  const item=record?.input || record || {},provenance=provenanceOf(record);
  const provider=provenance.source_name||provenance.provider||item.source;
  const collected=provenance.observed_at||item.observed_at||record?.collection?.observed_at;
  const web=safeSourceUrl(provenance.web_url||item.source_url||record?.collection?.source_url);
  const endpoint=safeSourceUrl(provenance.api_url||item.source_endpoint||item.endpoint||record?.collection?.source_endpoint);
  const entries=Array.isArray(provenance.links)?provenance.links:[];
  const schedule=safeSourceUrl(entries.find(entry=>entry.kind==="schedule")?.url);
  const pageUrl=web||schedule;
  const matchLink=pageUrl?sourceLink(pageUrl,web?"打开比赛原网页":"打开来源赛程"):sourceLink(endpoint,"打开原始数据"), links=[];
  const seen=new Set(pageUrl?[pageUrl]:[]);
  if(endpoint){seen.add(endpoint);if(pageUrl)links.push(sourceLink(endpoint,"原始数据接口"));}
  const labels={match:"打开比赛原网页",schedule:"打开来源赛程",home_team:"主队资料原网页",away_team:"客队资料原网页",competition:"赛事原网页",api:"原始数据接口"};
  for(const entry of entries){
    const url=safeSourceUrl(entry.url);
    if(!url||seen.has(url))continue;
    seen.add(url);links.push(sourceLink(url,labels[entry.kind]||entry.label||"来源网页"));
  }
  const methods={dictionary:"内置译名",demo:"演示译名","competition-registry":"内置赛事译名",structure:"规则生成译名",wikidata:"中文资料",mymemory:"自动翻译",model:"模型翻译",provided:"用户提供译名","offline-transliteration":"自动音译 · 待核验",pending:"正在获取中文",unavailable:"中文暂不可用",original:"原名"};
  const translatedFields=["home","away","competition","stage"].filter(key=>item.translation?.[key] && item.translation[key].original===item[key]);
  const translationDetails=translatedFields.length?`<details class="source-translations"><summary>译名与依据</summary>${translatedFields.map(key=>{
    const info=item.translation[key];
    return `<div><strong>${esc(displayName(item,key))}</strong><span>${esc(item[key])} · ${esc(methods[info.method]||info.method||"已提供译名")}</span>${sourceLink(info.source,"中文参考资料")}</div>`;
  }).join("")}</details>`:"";
  if(!provider && !collected && !matchLink && !links.length && !translationDetails)return "";
  if(typeof document!=="undefined" && !document.querySelector('link[href="/sources.css"]')){
    const link=document.createElement("link");link.rel="stylesheet";link.href="/sources.css";document.head.append(link);
  }
  const names=provenance.original_names||{};
  const originals=[["主队原名",names.home||originalName(item,"home")],["客队原名",names.away||originalName(item,"away")],["赛事原名",names.competition||originalName(item,"competition")]].filter(([,v])=>v);
  const content=`<div class="source-meta">${provider?`<div><span>提供者</span><strong>${esc(provider)}</strong></div>`:""}${collected?`<div><span>采集时间</span><time datetime="${esc(collected)}">${esc(collected)}</time></div>`:""}${originals.map(([label,value])=>`<div><span>${label}</span><span>${esc(value)}</span></div>`).join("")}</div>${links.length?`<div class="source-links">${links.join("")}</div>`:""}${translationDetails}`;
  return compact?`<div class="source-block">${matchLink}<details class="source-audit"><summary>来源与原始数据</summary>${content}</details></div>`:
    `<div class="source-block">${matchLink?`<div class="source-links">${matchLink}</div>`:""}${content}</div>`;
}
