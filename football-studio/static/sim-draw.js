import {HOME_SHIRT,AWAY_SHIRT,seeded} from './sim-motion.js';

const W=1000,H=550,TAU=Math.PI*2;
const kits=[HOME_SHIRT,AWAY_SHIRT],keepers=['#fd795c','#ceb1eb'];
const shirts=[1,2,4,5,3,8,6,10,7,9,11];
const skin=['#d59b73','#ab7453','#f0ba8e','#8c5a42','#e3ab82','#b77d55'];
const hair=['#3e302b','#422c22','#5b4034','#382d2a','#7d5338','#3d302a'];
function project(u,v){return {x:79-45*v+(842+90*v)*u,y:76+396*v};}
function poly(ctx,points,fill,stroke,width=1){
  ctx.beginPath();points.forEach(({x,y},i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();
  if(fill){ctx.fillStyle=fill;ctx.fill();}
  if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke();}
}
function path(ctx,coordinates,stroke,width){
  ctx.beginPath();coordinates.map(p=>project(...p)).forEach(({x,y},i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));
  ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke();
}
function groundRect(ctx,x1,y1,x2,y2,fill,stroke,width){
  poly(ctx,[[x1,y1],[x2,y1],[x2,y2],[x1,y2]].map(p=>project(...p)),fill,stroke,width);
}
function circle(ctx,x,y,r,fill){
  ctx.beginPath();ctx.arc(x,y,r,0,TAU);ctx.fillStyle=fill;ctx.fill();
}
function ellipse(ctx,x,y,rx,ry,color){
  ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,TAU);ctx.fillStyle=color;ctx.fill();
}
function segment(ctx,x1,y1,x2,y2,color,width){
  ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.lineWidth=width;ctx.strokeStyle=color;ctx.stroke();
}
function fieldArc(ctx,cx,cy,rx,ry,a,b,color,width){
  const points=[];
  for(let i=0;i<=42;i++){const ang=a+(b-a)*i/42;points.push([cx+rx*Math.cos(ang),cy+ry*Math.sin(ang)]);}
  path(ctx,points,color,width);
}

function stadium(){
  const layer=document.createElement('canvas');layer.width=W*1.4;layer.height=H*1.4;
  const g=layer.getContext('2d');g.scale(1.4,1.4);
  const random=seeded('touchline-ground'),crowd=[];
  g.fillStyle='#112c2c';g.fillRect(0,0,W,H);
  for(const top of [true,false]){
    const y0=top?1:501,rows=top?6:5;
    for(let row=0;row<rows;row++){
      const y=y0+row*8;
      g.fillStyle=row%2?'#233837':'#2c4140';g.fillRect(0,y,W,6);
      for(let col=0;col<171;col++){
        const x=col*6+(row%2)*3;
        if((col%30)>26)continue;
        const isHome=(Math.floor(col/27)+Number(!top))%2===0;
        const colors=isHome?['#e7b34e','#8b8e63','#c59452','#67756b','#607772','#bec5a0']:['#5793b6','#a1bdc3','#607a83','#68868f','#477b92','#b0b5a5'];
        const color=colors[Math.floor(random()*colors.length)];
        const yy=y+2.1+random()*1.9;
        g.fillStyle=color;g.fillRect(x,yy,3.7,2.8);
        g.fillStyle=random()>.5?'#ad8e75':'#a9a89b';g.fillRect(x+1,yy-1.6,1.9,1.8);
        if(col%3===0 && row%2===0)crowd.push({x,y:yy,color,isHome,phase:random()*TAU});
      }
    }
  }
  const pitchWash=g.createLinearGradient(0,59,0,496);
  pitchWash.addColorStop(0,'#284a42');pitchWash.addColorStop(.23,'#37624c');pitchWash.addColorStop(.83,'#365f47');pitchWash.addColorStop(1,'#27483e');
  g.fillStyle=pitchWash;g.fillRect(0,60,W,435);
  for(let n=0;n<30;n++){
    const x=n*35;
    g.fillStyle=n%4===0?'#dbc175':n%4===1?'#6997a6':n%4===2?'#4a6665':'#9db3a1';
    g.fillRect(x,48,32,8);g.fillRect(x,490,32,7);
    g.fillStyle='#253d38';g.fillRect(x+2,51,16,1);g.fillRect(x+3,493,11,1);
  }
  segment(g,0,46,W,46,'#9baca0',1.5);segment(g,0,499,W,499,'#678b7c',2);
  for(let i=0;i<12;i++)groundRect(g,i/12,0,(i+1)/12,1,i%2?'#347c4c':'#3e8653');
  const light=g.createLinearGradient(0,75,1000,470);
  light.addColorStop(0,'rgba(143,197,119,.12)');light.addColorStop(.48,'rgba(90,178,92,.05)');light.addColorStop(1,'rgba(9,47,36,.19)');
  groundRect(g,0,0,1,1,light);
  for(let i=0;i<9200;i++){
    const p=project(random(),random());
    g.fillStyle=i%3?'rgba(205,234,155,.086)':'rgba(17,72,33,.15)';
    g.fillRect(p.x,p.y,random()*2+.45,.65);
  }
  const line='#d4e7bdbd',weight=1.55;
  groundRect(g,0,0,1,1,null,line,weight);
  path(g,[[.5,0],[.5,1]],line,weight);
  fieldArc(g,.5,.5,.087,.134,0,TAU,line,weight);
  const center=project(.5,.5);ellipse(g,center.x,center.y,2.4,1.6,'#e8e9be');
  for(const left of [true,false]){
    const flip=x=>left?x:1-x;
    path(g,[[flip(0),.204],[flip(.157),.204],[flip(.157),.796],[flip(0),.796]],line,weight);
    path(g,[[flip(0),.364],[flip(.053),.364],[flip(.053),.636],[flip(0),.636]],line,weight);
    const pk=project(flip(.105),.5);ellipse(g,pk.x,pk.y,1.9,1.35,'#d8e7c4');
    fieldArc(g,flip(.105),.5,.087,.134,left?-.925:Math.PI-.925,left?.925:Math.PI+.925,line,weight);
    for(const v of [0,1]){
      const x=flip(0),start=left?(v===0?0:-Math.PI/2):(v===0?Math.PI/2:Math.PI);
      fieldArc(g,x,v,.012,.021,start,start+Math.PI*.5,line,weight);
      const p=project(x,v);
      segment(g,p.x,p.y,p.x,p.y-9,'#f1e6cb',1);
      poly(g,[{x:p.x,y:p.y-9},{x:p.x+(left?5:-5),y:p.y-7},{x:p.x,y:p.y-5}],'#eabd65');
    }
  }
  for(const side of [0,1])goalFrame(g,side,0,true);
  return {layer,crowd};
}

function goalFrame(g,side,bulge,backOnly){
  const d=side===0?-1:1,yTop=.430,yBot=.570;
  const a=project(side,yTop),b=project(side,yBot);
  const frontA={x:a.x,y:a.y-11},frontB={x:b.x,y:b.y-12};
  const depth=18+bulge*4,backA={x:frontA.x+d*depth,y:frontA.y+1},backB={x:frontB.x+d*depth,y:frontB.y+1};
  if(backOnly){
    poly(g,[frontA,backA,backB,frontB],'rgba(208,228,213,.19)');
    poly(g,[backA,backB,{x:backB.x,y:b.y+1},{x:backA.x,y:a.y+1}],'rgba(176,206,195,.28)');
    for(let r=0;r<=8;r++){
      const u=r/8,x1=frontA.x+(frontB.x-frontA.x)*u,y1=frontA.y+(frontB.y-frontA.y)*u;
      segment(g,x1,y1,x1+d*depth,y1+1,'#c9dbcc85',.7);
      segment(g,x1+d*depth,y1+1,x1+d*depth,y1+12,'#c9dbcc80',.7);
    }
    for(let j=1;j<=4;j++)segment(g,frontA.x+d*depth*j/4,frontA.y,frontB.x+d*depth*j/4,frontB.y,'#c9dbcc80',.7);
  }
  const white='#e1e7cf';
  segment(g,a.x,a.y,frontA.x,frontA.y,white,2);
  segment(g,frontA.x,frontA.y,frontB.x,frontB.y,white,2.2);
  segment(g,frontB.x,frontB.y,b.x,b.y,white,2);
  segment(g,backA.x,backA.y,backB.x,backB.y,'#b9c6b3',1.1);
}

function drawPlayers(g,frame,elapsed,seedPhase){
  const order=frame.people.map((p,i)=>({p,i})).sort((a,b)=>a.p.y-b.p.y||a.i-b.i);
  for(const {p,i} of order){
    const spot=project(p.x,p.y),side=i<11?0:1,role=i%11;
    const scale=.79+.32*p.y,celebrating=frame.goalAge>=0 && (frame.event.side==='home'?side===0:side===1)&&role>=6;
    const step=Math.sin(elapsed*10.8+i*1.3+seedPhase),stride=p.moving?step*1.75:0;
    const bounce=celebrating?Math.abs(Math.sin(elapsed*8.6+i)) * 2:p.moving?Math.abs(step)*.6:0;
    const face=Math.abs(p.dx)>.006?(p.dx>0?1:-1):directionIdle(side,frame.event.half);
    const diving=role===0&&frame.canDive&&((frame.event.side==='home')!==(side===0));
    g.save();g.translate(spot.x,spot.y);g.scale(scale,scale);
    ellipse(g,2,1.4,6.4,2.45,'rgba(10,43,31,.53)');
    if(frame.carrier===i && frame.mode==='carry' && frame.goalAge<0){
      g.beginPath();g.ellipse(0,1.2,8.4,3.45,0,0,TAU);g.strokeStyle='rgba(255,251,192,.72)';g.lineWidth=.95;g.stroke();
    }
    g.translate(0,-bounce);
    if(diving){g.translate(0,-2);g.rotate(face*.85);}
    const jersey=role===0?keepers[side]:kits[side],shorts=side===0?'#282f31':'#ebede8',boots='#232a2b';
    const flesh=skin[(i+seedPhase)%skin.length];
    g.lineCap='round';
    segment(g,-1.65,-5,-2.2+stride,-.7,flesh,2.4);segment(g,1.55,-5,1.95-stride,-.35,flesh,2.4);
    segment(g,-2.1+stride,-1.9,-2.2+stride,-.5,jersey,2.35);segment(g,1.9-stride,-1.6,1.95-stride,-.3,jersey,2.35);
    ellipse(g,-1.8+stride+face*.55,-.3,1.8,.85,boots);ellipse(g,2.1-stride+face*.55,0,1.75,.80,boots);
    poly(g,[{x:-3.1,y:-7.1},{x:3.1,y:-7.1},{x:3,y:-4.0},{x:.55,y:-4.1},{x:0,y:-5},{x:-.55,y:-4.0},{x:-3.0,y:-4.1}],shorts);
    const armY=celebrating?-16:-6.9,pump=p.moving?step*1.3:0;
    segment(g,-3.3,-11.1,-5.0,armY+pump,flesh,2.05);segment(g,3.3,-11.1,5.0,armY-pump,flesh,2.05);
    poly(g,[{x:-3.4,y:-12.3},{x:-5.0,y:-10.5},{x:-4.4,y:-9.0},{x:-3.2,y:-9.2},{x:-2.95,y:-6.3},{x:2.95,y:-6.3},{x:3.2,y:-9.2},{x:4.4,y:-9.0},{x:5.05,y:-10.5},{x:3.4,y:-12.3},{x:1,y:-12.6},{x:-1,y:-12.6}],jersey,'rgba(24,44,42,.62)',.55);
    g.fillStyle=side===0?'#5c471d':'#16486a';g.font='bold 4.7px Arial';g.textAlign='center';g.fillText(String(shirts[role]),0,-7.55);
    circle(g,face*.3,-14.2,2.7,flesh);ellipse(g,face*-.05,-15.3,2.55,1.8,hair[(i+seedPhase)%hair.length]);
    g.restore();
  }
}
function directionIdle(side,half){return (side===0)===(half===1)?1:-1;}
function drawBall(g,frame,elapsed){
  const b=project(frame.ball.x,frame.ball.y);
  if(frame.flight && frame.trail){
    const from=project(frame.trail[0].x,frame.trail[0].y),dx=b.x-from.x,dy=b.y-from.y;
    const length=Math.hypot(dx,dy),k=Math.min(1,(frame.mode==='shot'?35:19)/Math.max(1,length));
    segment(g,b.x-dx*k,b.y-dy*k-frame.ball.lift-1.4,b.x,b.y-frame.ball.lift-1.4,'#f1eebc68',frame.mode==='shot'?2.1:1.4);
  }
  ellipse(g,b.x+.9,b.y+.4,3.3+frame.ball.lift*.05,1.4,'#193c3299');
  const y=b.y-frame.ball.lift-2;
  circle(g,b.x,y,3.3,'#314640');circle(g,b.x,y-.2,2.65,'#fcf9e9');
  circle(g,b.x+Math.sin(elapsed*12)*.75,y+.12,.96,'#414a42');
}
function cheer(g,frame,stad){
  const age=frame.goalAge;
  if(age<0)return;
  const strength=Math.min(1,age*5)*Math.min(1,Math.max(0,(2.9-age)*2)),home=frame.event.side==='home';
  for(const dot of stad.crowd){
    const amplitude=dot.isHome===home?3.9:1.4,wave=Math.sin(age*9+dot.phase+dot.x/58);
    const lift=Math.max(0,wave)*amplitude*strength;
    g.fillStyle=dot.color;g.fillRect(dot.x-.6,dot.y-lift,4.8,3);
    if(wave>.05){segment(g,dot.x,dot.y-lift+1,dot.x-1.8,dot.y-lift-2.4,'#d5bc9c',.9);segment(g,dot.x+3,dot.y-lift+1,dot.x+5.3,dot.y-lift-2.8,'#d5bc9c',.9);}
  }
  const center=project(frame.direction>0?.955:.045,.50);
  const color=home?HOME_SHIRT:AWAY_SHIRT;
  for(let n=0;n<39;n++){
    const q=(n*.617)%1,lifetime=age-(n%5)*.034;if(lifetime<0||lifetime>2.65)continue;
    const speed=16+(n*19)%62,dx=Math.cos(q*TAU)*speed*lifetime;
    const yy=-Math.sin(q*Math.PI)*speed*lifetime+24*lifetime*lifetime;
    g.fillStyle=n%4===0?'#f4f2c9':n%4===1?'#eabd69':color;
    g.globalAlpha=.86*Math.min(1,(2.65-lifetime)*1.4);
    g.fillRect(center.x+dx,center.y+yy,2.4+Math.sin(n+lifetime*5),2.2);
  }
  g.globalAlpha=1;
}
let cachedGround;
export function drawPitch(canvas,frame,elapsed,seed=0){
  const g=canvas.getContext('2d');if(!g)return;
  cachedGround??=stadium();
  const ratio=Math.min(window.devicePixelRatio||1,2);
  const rect=canvas.getBoundingClientRect(),px=Math.round(rect.width*ratio),py=Math.round(rect.height*ratio);
  if(px<2||py<2)return;
  if(canvas.width!==px||canvas.height!==py){canvas.width=px;canvas.height=py;}
  g.setTransform(px/W,0,0,py/H,0,0);g.drawImage(cachedGround.layer,0,0,W,H);
  if(frame.goalAge>=0&&frame.goalAge<.55)goalFrame(g,frame.direction>0?1:0,Math.sin(frame.goalAge*22)*Math.exp(-frame.goalAge*6),true);
  drawPlayers(g,frame,elapsed,seed);drawBall(g,frame,elapsed);
  cheer(g,frame,cachedGround);
}
