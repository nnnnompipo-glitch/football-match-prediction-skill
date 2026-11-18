const clamp=(n,lo=0,hi=1)=>Math.max(lo,Math.min(hi,n));
const mix=(a,b,t)=>a+(b-a)*t;
export const HOME_SHIRT='#fbcd58', AWAY_SHIRT='#63b8ff';
export const labels={kickoff:'中圈开球',attack:'进攻推进',pass:'传球配合',tackle:'抢断',shot:'射门',save:'门将扑救',miss:'射门偏出',goal:'进球',halftime:'半场休息',fulltime:'全场结束'};
const formation=[[.045,.50],[.25,.13],[.20,.39],[.21,.63],[.25,.86],[.44,.23],[.41,.49],[.44,.75],[.64,.17],[.68,.49],[.63,.82]];

export function seeded(seed){
  let h=2166136261;
  for(const char of String(seed??7)){h^=char.charCodeAt(0);h=Math.imul(h,16777619);}
  return ()=>{h=(Math.imul(1664525,h)+1013904223)>>>0;return h/4294967296;};
}
function direction(side,half){return (side==='home')===(half===1)?1:-1;}
function transform(u,v,side,half){return {x:direction(side,half)===1?u:1-u,y:v};}
function offset(side){return side==='away'?11:0;}
function other(side){return side==='home'?'away':'home';}
function resolveEvent(item){
  const minute=Number(item.minute);
  if(!Number.isFinite(minute)||!Object.hasOwn(labels,item.type))return null;
  return {...item,minute:clamp(minute,0,90),side:item.side==='away'?'away':'home'};
}
function sortedEvents(items){
  const events=(items||[]).map(resolveEvent).filter(Boolean);
  if(!events.some(e=>e.type==='kickoff'&&e.minute===0))events.push({type:'kickoff',side:'home',minute:0});
  if(!events.some(e=>e.type==='halftime'))events.push({type:'halftime',side:'home',minute:45});
  if(!events.some(e=>e.type==='fulltime'))events.push({type:'fulltime',side:'home',minute:90});
  const order=e=>e.type==='fulltime'?3:e.type==='halftime'?2:e.type==='kickoff'?-1:0;
  return events.sort((a,b)=>a.minute-b.minute||order(a)-order(b));
}
function lineUp(ball,attack,half,wide){
  return Array.from({length:22},(_,i)=>{
    const role=i%11,side=i<11?'home':'away',d=direction(side,half),u=d===1?ball.x:1-ball.x;
    const [bx,by]=formation[role];
    if(role===0)return transform(.032+.037*clamp(u),.5+(ball.y-.5)*.23,side,half);
    const push=(u-.5)*.36+(side===attack?.063:-.065);
    const depth=clamp(bx+push,.09,.91),y=clamp(by+(ball.y-.5)*.20+Math.sin(role*1.7+wide)*.025,.07,.93);
    return transform(depth,y,side,half);
  });
}
function nearest(players,point,side,exclude=-1){
  let best=-1,dist=Infinity;
  for(let i=offset(side)+1;i<offset(side)+11;i++){
    if(i===exclude)continue;
    const p=players[i],dst=(p.x-point.x)**2+(.68*(p.y-point.y))**2;
    if(dst<dist){best=i;dist=dst;}
  }
  return best;
}
function wiggle(rng,amount){return (rng()-.5)*amount;}

export function makeScenes(simulation){
  const random=seeded(simulation.seed??JSON.stringify(simulation.events));
  const events=sortedEvents(simulation.events),keys=[],incidents=[];
  let half=1,t=0,ball={x:.5,y:.5},players=lineUp(ball,'home',1,0),carrier=-1;
  let previousType='',lastGoalSide=null;
  const score=[0,0];
  keys.push({t,ball,players,mode:'hold',attack:'home',half,carrier:-1});
  for(const event of events){
    const side=event.side,defence=other(side),team=offset(side),def=offset(defence),start=t;
    const priorScore=[...score];
    if(event.minute>45&&half===1)half=2;
    const d=direction(side,half),asPoint=(u,v)=>transform(u,v,side,half);
    const lane=(random()<.5?.24:.76)+wiggle(random,.15);
    const flank=lane<.5?8:10, midfielder=lane<.5?5:7,centre=team+9;
    const wide=random()*Math.PI*2;
    let actionAt=start,approachTo=side;
    function step(seconds,target,nextCarrier,mode,overrides=[],attack=approachTo){
      const targetPlayers=lineUp(target,attack,half,wide+t*.08);
      if(nextCarrier>=0)targetPlayers[nextCarrier]={x:clamp(target.x-direction(attack,half)*.010,.017,.983),y:clamp(target.y-.007,.025,.975)};
      for(const [index,point] of overrides)targetPlayers[index]=point;
      t+=seconds;
      keys.push({t,players:targetPlayers,ball:target,mode,attack,half,carrier:nextCarrier});
      players=targetPlayers;ball=target;carrier=nextCarrier;
    }
    function hold(seconds,mode='hold'){
      t+=seconds;keys.push({t,players,ball,mode,attack:side,half,carrier});
    }
    function restart(restarting,seconds){
      const sc=offset(restarting),center={x:.5,y:.5};
      const kickoff=lineUp(center,restarting,half,wide);
      kickoff.forEach((p,i)=>{const own=i<11?'home':'away',ownDir=direction(own,half);
        if(i%11!==0)p.x=ownDir===1?Math.min(.455,p.x):Math.max(.545,p.x);
      });
      kickoff[sc+9]=transform(.495,.51,restarting,half);
      kickoff[sc+6]=transform(.427,.565,restarting,half);
      step(seconds,center,sc+9,'reset',kickoff.map((p,i)=>[i,p]),restarting);
    }
    if(event.type==='kickoff'){
      restart(side,start===0?.05:.75);
      actionAt=t;
      step(1.1,transform(.416,.57,side,half),team+6,'pass');
    }else if(event.type==='halftime'||event.type==='fulltime'){
      actionAt=t;
      hold(event.type==='halftime'?1.35:.65);
    }else{
      if(previousType==='halftime')restart(side,.85);
      else if(previousType==='goal')restart(other(lastGoalSide),.85);
      const isFinish=['goal','save','miss','shot'].includes(event.type);
      if(event.type==='tackle'){
        approachTo=defence;
        const opponent=nearest(players,ball,defence);
        const duel=asPoint(.41+wiggle(random,.17),lane);
        const winner=nearest(players,duel,side);
        step(1.0,players[opponent],opponent,'pass',[],defence);
        step(1.15,duel,opponent,'carry',[[winner,{x:duel.x+.019*d,y:duel.y-.017}]],defence);
        step(.38,{x:duel.x+.016*d,y:duel.y-.024},winner,'tackle',[],side);
        actionAt=t;
        step(.88,asPoint(.54,lane+.04),winner,'carry',[],side);
      }else{
        const sameSide=carrier>=team&&carrier<team+11;
        const pivot=sameSide?carrier:nearest(players,ball,side);
        if(!sameSide){
          const turnover=players[pivot];step(.82,turnover,pivot,'loose');
        }
        const inlet=asPoint(.44+wiggle(random,.09),.51+wiggle(random,.28));
        const distributor=pivot===team+6?team+midfielder:team+6;
        step(.92,inlet,distributor,'pass');
        const support=asPoint(.61+wiggle(random,.045),lane);
        const runner=team+flank;
        step(1.08,support,runner,'pass');
        if(isFinish){
          const crossing=asPoint(.77,lane+wiggle(random,.05));
          const pursuer=nearest(players,crossing,defence);
          step(.85,crossing,runner,'carry',[[pursuer,asPoint(.765,lane+.04)]]);
          const box=asPoint(.843,.5+(lane-.5)*.37+wiggle(random,.07));
          const marker=nearest(players,box,defence);
          step(.84,box,centre,'pass',[[marker,asPoint(.87,box.y+.05)]]);
          const shotStart=asPoint(.888,box.y+wiggle(random,.035));
          step(.59,shotStart,centre,'carry',[[marker,asPoint(.86,shotStart.y+.025)]]);
          const targetY=.5+(random()<.5?-1:1)*(.037+random()*.029);
          const keeper=def,goal=event.type==='goal',save=['shot','save'].includes(event.type);
          const target=asPoint(goal?1.014:save?.966:1.025,save?.5+(targetY-.5)*.92:goal?targetY:.5+Math.sign(targetY-.5)*(.13+random()*.09));
          const dive=asPoint(save?.966:.979,save?target.y:.5-(targetY-.5)*.35);
          step(.59,target,save?keeper:-1,'shot',[[keeper,dive],[centre,shotStart]]);
          actionAt=t;
          if(goal){
            score[side==='home'?0:1]++;lastGoalSide=side;
            const celebration=players.map(p=>({...p}));
            const cornerY=lane<.5?.13:.87;
            for(const [role,dx,dy] of [[9,0,0],[8,-.032,.06],[10,-.056,-.04],[7,-.085,.07],[6,-.101,-.05]]){
              celebration[team+role]=asPoint(.89+dx,cornerY+dy);
            }
            step(1.18,ball,-1,'celebrate',celebration.map((p,i)=>[i,p]));
            hold(1.48,'celebrate');
          }else hold(.50,save?'caught':'hold');
        }else{
          actionAt=t;
          const dest=asPoint(event.type==='pass'?.68:.78,lane+(lane<.5?.10:-.10));
          if(event.type==='pass')step(.84,dest,centre,'pass');
          else step(.97,dest,runner,'carry');
        }
      }
    }
    incidents.push({...event,start,end:t,actionAt,half,score:[...score],priorScore});
    previousType=event.type;
  }
  const anchors=[{t:0,minute:0}];
  for(const e of incidents){
    anchors.push({t:e.actionAt,minute:e.minute},{t:e.end,minute:e.minute});
  }
  return {keys,incidents,anchors,duration:t};
}

function upperKey(array,time,field){
  let lo=0,hi=array.length-1;
  while(lo<hi){
    const mid=(lo+hi+1)>>1;
    if(array[mid][field]<=time)lo=mid;else hi=mid-1;
  }
  return lo;
}
export function frameAt(scenes,elapsed){
  const t=clamp(elapsed,0,scenes.duration);
  const idx=upperKey(scenes.keys,t,'t');
  const a=scenes.keys[idx],b=scenes.keys[Math.min(idx+1,scenes.keys.length-1)];
  const z=b.t>a.t?clamp((t-a.t)/(b.t-a.t)):1,s=z*z*(3-2*z);
  const people=b.players.map((end,i)=>{
    const p=a.players[i],dx=end.x-p.x,dy=end.y-p.y;
    return {x:mix(p.x,end.x,s),y:mix(p.y,end.y,s),dx,dy,moving:Math.hypot(dx,dy)>.018};
  });
  const flight=['pass','shot','loose'].includes(b.mode);
  const ballMix=flight?1-(1-z)**1.35:s;
  const ball={x:mix(a.ball.x,b.ball.x,ballMix),y:mix(a.ball.y,b.ball.y,ballMix),lift:flight?Math.sin(ballMix*Math.PI)*(b.mode==='shot'?8:4):0};
  const e=scenes.incidents[upperKey(scenes.incidents,t,'start')],active=t+.00001>=e.actionAt;
  const last=upperKey(scenes.incidents,t,'actionAt');
  const anchorIdx=upperKey(scenes.anchors,t,'t'),q=scenes.anchors[anchorIdx],r=scenes.anchors[Math.min(anchorIdx+1,scenes.anchors.length-1)];
  const minute=q.t===r.t?r.minute:mix(q.minute,r.minute,(t-q.t)/(r.t-q.t));
  return {ball,people,flight,trail:flight?[a.ball,ball]:null,t,mode:b.mode,carrier:b.carrier,
    event:e,active,last,minute,score:active?e.score:e.priorScore,goalAge:e.type==='goal'&&active?t-e.actionAt:-1,
    direction:direction(e.side,e.half),canDive:b.mode==='shot'&&z>.52};
}
