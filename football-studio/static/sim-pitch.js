import {esc} from './ui.js';
import {makeScenes,frameAt,labels,seeded} from './sim-motion.js';
import {drawPitch} from './sim-draw.js';

const installed=new WeakMap();
const glyph={
 play:'<path d="m7 4 13 8-13 8z" fill="currentColor" stroke="none"/>',
 pause:'<path d="M8 5v14m8-14v14" stroke-width="4"/>',
 replay:'<path d="M4 10a8 8 0 1 1 1 7m-2-12v6h6"/>',
 sound:'<path d="m3 9 5 0 5-4v14l-5-4H3zM16 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
 mute:'<path d="m3 9 5 0 5-4v14l-5-4H3zm13 1 5 5m0-5-5 5"/>',
 next:'<path d="m5 5 11 7-11 7zm13 0v14"/>',
 highlight:'<path d="m13 2-9 12h7l-1 8 10-13h-8z"/>',
 shuffle:'<path d="M3 6h3c5 0 6 12 12 12h3m-4-4 4 4-4 4M3 18h3c2 0 4-3 5-5m3-4c1-2 3-3 5-3h2m-4-4 4 4-4 4"/>',
 ball:'<circle cx="12" cy="12" r="9"/><path d="m12 7 5 4-2 6H9l-2-6zm0 0V3m5 8 4-1m-6 7 2 3m-8-3-2 3m0-9-4-1"/>',
};
const ico=(type,size=17)=>`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${glyph[type]}</svg>`;
const kit=side=>`<svg class="sim-kit ${side}" viewBox="0 0 36 34" aria-hidden="true"><path d="M10 3 6 5 1 12l6 4 3-3v17h16V13l3 3 6-4-5-7-5-2c-3 3-12 3-15 0Z" fill="currentColor"/><path d="m14 3 4 5 4-5m-12 24h16" stroke="#1f3642" stroke-opacity=".65" fill="none" stroke-width="2"/><path d="M13 11v13m4-13v13m4-13v13" stroke="#fff" stroke-opacity=".24" stroke-width="2"/></svg>`;

function styleSheet(){
  if(document.querySelector('link[data-simulation]'))return;
  const link=document.createElement('link');link.rel='stylesheet';link.dataset.simulation='pitch';
  link.href=new URL('./sim-pitch.css',import.meta.url).href;document.head.append(link);
}
function clock(minute){
  const seconds=Math.round(minute*60);
  return `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
}
function soundBox(){
  let ctx=null,active=new Set();
  const WebAudio=window.AudioContext||window.webkitAudioContext;
  function stop(){
    for(const src of active){try{src.stop();}catch{}}
    active.clear();
  }
  async function open(){
    if(!WebAudio)return false;
    try{ctx??=new WebAudio();await ctx.resume();return true;}catch{return false;}
  }
  function track(node){
    active.add(node);node.onended=()=>{active.delete(node);node.disconnect();};
  }
  function whistle(start,length,hz,volume){
    const note=ctx.createOscillator(),gain=ctx.createGain();
    note.type='sine';note.frequency.setValueAtTime(hz,start);note.frequency.exponentialRampToValueAtTime(hz*1.08,start+length*.55);
    gain.gain.setValueAtTime(.0001,start);gain.gain.exponentialRampToValueAtTime(volume,start+.035);
    gain.gain.exponentialRampToValueAtTime(.0001,start+length);
    note.connect(gain).connect(ctx.destination);track(note);note.start(start);note.stop(start+length+.01);
  }
  function cheer(){
    if(!ctx||ctx.state!=='running')return;
    stop();
    const now=ctx.currentTime,n=ctx.sampleRate*2.4|0,buf=ctx.createBuffer(1,n,ctx.sampleRate);
    const arr=buf.getChannelData(0);let smooth=0;
    for(let i=0;i<n;i++){
      const noise=Math.random()*2-1;smooth=.87*smooth+.13*noise;
      arr[i]=(noise*.25+smooth*1.55)*(.71+.1*Math.sin(i/800)+.12*Math.sin(i/109));
    }
    const src=ctx.createBufferSource(),filter=ctx.createBiquadFilter(),gain=ctx.createGain();
    src.buffer=buf;filter.type='lowpass';filter.frequency.setValueAtTime(2500,now);filter.frequency.exponentialRampToValueAtTime(900,now+2.3);
    gain.gain.setValueAtTime(.0001,now);gain.gain.exponentialRampToValueAtTime(.66,now+.23);
    gain.gain.setValueAtTime(.51,now+.72);gain.gain.exponentialRampToValueAtTime(.002,now+2.32);
    src.connect(filter).connect(gain).connect(ctx.destination);track(src);src.start();
    whistle(now+.27,.29,1140,.025);whistle(now+.74,.43,890,.022);whistle(now+1.08,.39,1435,.016);
  }
  function endWhistle(){if(ctx?.state==='running'){const t=ctx.currentTime;whistle(t,.19,1490,.040);whistle(t+.29,.42,1650,.037);}}
  function dispose(){stop();if(ctx){ctx.close().catch(()=>{});ctx=null;}}
  return {available:!!WebAudio,open,stop,cheer,endWhistle,dispose};
}
function statement(frame,names){
  const e=frame.event,who=names[e.side],rival=names[e.side==='home'?'away':'home'];
  if(frame.active){
    if(e.text)return e.text;
    return ({kickoff:`${who}在中圈开球。`,pass:`${who}通过中场配合完成传递。`,attack:`${who}沿边路推进。`,
      tackle:`${who}在中场抢断，转入反击。`,goal:`${who}破门，看台响起欢呼！`,
      save:`${rival}门将扑住${who}的射门。`,shot:`${who}完成射门，${rival}门将将球控制住。`,
      miss:`${who}起脚，足球偏出门框。`,halftime:'双方离场休息，下半场将交换进攻方向。',fulltime:`终场哨响，模拟比分 ${frame.score[0]} : ${frame.score[1]}。`})[e.type];
  }
  if(frame.mode==='reset')return '双方回到中圈，准备重新开球。';
  if(frame.mode==='shot')return `${who}在禁区内起脚射门！`;
  if(frame.mode==='tackle')return '双方争抢球权。';
  if(frame.mode==='loose')return `${who}尝试控制第二落点。`;
  if(frame.mode==='carry')return `${who}持球推进，防守球员上前逼抢。`;
  return `${who}寻找接应，队友正在跑位。`;
}

export function mountSimulator(container,simulation,options={}){
  installed.get(container)?.destroy();
  styleSheet();
  const names={home:String(simulation.home||'主队'),away:String(simulation.away||'客队')};
  const scenes=makeScenes(simulation),sound=soundBox(),seedPhase=Math.floor(seeded(simulation.seed)()*20);
  const highlights=scenes.incidents.filter(e=>['goal','tackle','miss','shot','save'].includes(e.type));
  const shell=document.createElement('section');shell.className='sim-theatre';shell.setAttribute('aria-label','二维比赛回放');
  const summaryText=options.probabilityText;
  shell.innerHTML=`<div class="sim-scoreboard">
    <div class="sim-team sim-home">${kit('home')}<div><small>主队</small><strong>${esc(names.home)}</strong></div></div>
    <div class="sim-clockboard"><div class="sim-goals" aria-label="模拟比分"><span data-home-score>0</span><i>:</i><span data-away-score>0</span></div><div><span data-period>上半场</span> <time data-clock>00:00</time></div></div>
    <div class="sim-team sim-away"><div><small>客队</small><strong>${esc(names.away)}</strong></div>${kit('away')}</div>
    </div><div class="sim-stage"><canvas aria-label="球场动画，主队穿金色，客队穿蓝色。场下文字同步播报攻防和比分。">此浏览器无法绘制球场，可以使用下方比赛文字和精彩时刻。</canvas>
    <div data-goal-bug class="sim-goal-bug" hidden><b>${ico('ball',22)} GOAL!</b><span></span></div></div>
    <div class="sim-commentary"><b data-incident>${ico('ball',16)} 场上动态</b><span data-comment></span></div>
    <div class="sim-controls"><div class="sim-track"><div class="sim-marks" aria-hidden="true"></div><input type="range" data-scrub aria-label="比赛回放进度" min="0" max="1000" step="1" value="0"></div>
      <div class="sim-buttons"><button type="button" class="sim-play" data-play></button><button type="button" data-replay>${ico('replay')} 重播</button>
      <button type="button" data-next>${ico('next')} 下一精彩时刻</button>
      <label class="sim-speed">速度 <select aria-label="回放速度"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></label>
      <button type="button" data-audio aria-pressed="false">${ico('mute')} <span>开启声音</span></button></div>
    </div><div data-announcement aria-live="polite" class="sim-sr"></div>`;
  if(summaryText||options.onResample){
    const nav=document.createElement('div');nav.className='sim-sample';
    if(summaryText){const p=document.createElement('p');p.textContent=String(summaryText);nav.append(p);}
    if(typeof options.onResample==='function'){
      const btn=document.createElement('button');btn.type='button';btn.innerHTML=ico('shuffle',15)+' 重新抽样';btn.onclick=()=>options.onResample();nav.append(btn);
    }
    shell.append(nav);
  }
  if(highlights.length){
    const list=document.createElement('details');list.className='sim-highlights';
    list.innerHTML=`<summary>${ico('highlight',15)} 精彩时刻 <small>${highlights.length}</small></summary><div class="sim-clips"></div>`;
    const clips=list.querySelector('div');
    for(const e of highlights){
      const btn=document.createElement('button');btn.type='button';btn.classList.toggle('sim-goal-clip',e.type==='goal');
      btn.innerHTML=`<time>${Math.floor(e.minute)}′</time><b>${esc(labels[e.type])}</b><span>${esc(names[e.side])}</span>`;
      btn.setAttribute('aria-label',`${e.minute} 分钟 ${names[e.side]} ${labels[e.type]}，播放此片段`);
      btn.onclick=()=>jump(e);clips.append(btn);
    }
    shell.append(list);
  }
  container.replaceChildren(shell);
  const node=k=>shell.querySelector(`[data-${k}]`);
  const canvas=shell.querySelector('canvas'),stage=shell.querySelector('.sim-stage');
  const playBtn=node('play'),scrub=node('scrub'),next=node('next'),audio=node('audio');
  for(const e of highlights.filter(e=>e.type==='goal')){
    const dot=document.createElement('i');dot.style.left=`${100*e.actionAt/scenes.duration}%`;shell.querySelector('.sim-marks').append(dot);
  }
  if(!sound.available){audio.disabled=true;audio.title='当前浏览器不支持场内音效';}
  let elapsed=0,lastTick=0,raf=0,playing=false,disposed=false,rate=1,audible=false,priorEvent='',announceKey='',selectedClip=null;
  let observer=null,sizeObserver=null,restorePlay=false;
  const set=(el,v)=>{if(el.textContent!==v)el.textContent=v;};
  const clockEl=node('clock'),period=node('period'),homeScore=node('home-score'),awayScore=node('away-score');
  const goalBug=node('goal-bug'),comment=node('comment'),incident=node('incident'),announcer=node('announcement');
  function paint(allowSound=false){
    if(disposed)return;
    const f=frameAt(scenes,elapsed),e=f.event;
    drawPitch(canvas,f,elapsed,seedPhase);
    const time=clock(f.minute),final=elapsed>=scenes.duration-.001;
    set(homeScore,String(f.score[0]));set(awayScore,String(f.score[1]));set(clockEl,time);
    const periodText=e.type==='halftime'&&f.active?'中场':e.type==='fulltime'&&f.active?'全场':e.half===1?'上半场':'下半场';
    set(period,periodText);
    const narrative=statement(f,names);set(comment,narrative);
    const key=f.active?`${e.actionAt}/${e.type}`:'';
    if(key!==priorEvent){
      if(key&&audible&&allowSound){
        if(e.type==='goal')sound.cheer();
        if(e.type==='fulltime'||e.type==='halftime')sound.endWhistle();
      }
      priorEvent=key;
    }
    const head=f.active?labels[e.type]:f.mode==='shot'?'起脚射门':'场上动态';
    if(incident.dataset.name!==head){incident.innerHTML=ico(e.type==='goal'&&f.active?'highlight':'ball',16)+' '+esc(head);incident.dataset.name=head;}
    if(key&&key!==announceKey){
      set(announcer,`${time}，${narrative} 比分 ${f.score[0]} 比 ${f.score[1]}。`);announceKey=key;
    }
    goalBug.hidden=f.goalAge<0;stage.classList.toggle('scored',f.goalAge>=0);
    if(f.goalAge>=0)set(goalBug.querySelector('span'),`${Math.floor(e.minute)}′　${names[e.side]}`);
    const fraction=elapsed/scenes.duration;scrub.value=String(Math.round(fraction*1000));
    scrub.style.setProperty('--sim-progress',`${(fraction*100).toFixed(2)}%`);
    scrub.setAttribute('aria-valuetext',`${periodText} ${time}，比分 ${f.score[0]} 比 ${f.score[1]}`);
    next.disabled=!nextHighlight();
    shell.dataset.score=f.score.join(':');shell.dataset.event=f.active?e.type:'build-up';
    if(final&&playing){playing=false;setPlay();}
  }
  function setPlay(){
    playBtn.innerHTML=ico(playing?'pause':'play',16)+(playing?' 暂停':elapsed>=scenes.duration?' 再次播放':' 播放');
    playBtn.setAttribute('aria-label',playing?'暂停模拟':'播放模拟');
  }
  function tick(now){
    if(!playing||disposed)return;
    if(!shell.isConnected){destroy();return;}
    if(lastTick)elapsed=Math.min(scenes.duration,elapsed+Math.min((now-lastTick)/1000,.18)*rate);
    lastTick=now;paint(true);
    if(playing)raf=requestAnimationFrame(tick);
  }
  function play(){
    if(disposed||playing)return;
    if(elapsed>=scenes.duration){elapsed=0;priorEvent='';announceKey='';}
    playing=true;lastTick=0;setPlay();raf=requestAnimationFrame(tick);
  }
  function pause(){
    if(disposed)return;
    playing=false;lastTick=0;cancelAnimationFrame(raf);sound.stop();setPlay();
  }
  function seek(fraction){
    if(disposed)return;
    selectedClip=null;sound.stop();elapsed=Math.min(scenes.duration,Math.max(0,Number(fraction)||0)*scenes.duration);
    lastTick=0;paint();setPlay();
  }
  function jump(e){
    seek(Math.max(e.start,e.actionAt-2.8)/scenes.duration);selectedClip=e;next.disabled=!nextHighlight();play();
  }
  function nextHighlight(){return highlights.find(h=>h.actionAt>elapsed+1.1&&h!==selectedClip);}
  playBtn.onclick=()=>playing?pause():play();
  node('replay').onclick=()=>{seek(0);play();};
  next.onclick=()=>{const e=nextHighlight();if(e)jump(e);};
  shell.querySelector('select').onchange=e=>{rate=Number(e.target.value)||1;};
  scrub.oninput=()=>seek(Number(scrub.value)/1000);
  audio.onclick=async()=>{
    audible=!audible&&await sound.open();if(disposed)return;
    if(!audible)sound.stop();
    audio.setAttribute('aria-pressed',String(audible));audio.innerHTML=ico(audible?'sound':'mute')+` <span>${audible?'关闭声音':'开启声音'}</span>`;
    if(audible&&playing&&frameAt(scenes,elapsed).goalAge>=0)sound.cheer();
  };
  function onVisibility(){
    if(document.hidden){restorePlay=playing;pause();}
    else if(restorePlay){restorePlay=false;play();}
  }
  function destroy(){
    if(disposed)return;disposed=true;playing=false;cancelAnimationFrame(raf);sound.dispose();observer?.disconnect();sizeObserver?.disconnect();
    document.removeEventListener('visibilitychange',onVisibility);window.removeEventListener('resize',onResize);
    installed.delete(container);
  }
  function onResize(){paint();}
  document.addEventListener('visibilitychange',onVisibility);window.addEventListener('resize',onResize);
  if('ResizeObserver' in window){sizeObserver=new ResizeObserver(onResize);sizeObserver.observe(canvas);}
  observer=new MutationObserver(()=>{if(!shell.isConnected)destroy();});
  for(let ancestor=container;ancestor;ancestor=ancestor.parentElement)observer.observe(ancestor,{childList:true});
  const controls={destroy,play,pause,seek};installed.set(container,controls);
  paint();setPlay();
  const reduce=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if((options.autoplay??true)&&!reduce&&!document.hidden)play();
  return controls;
}
