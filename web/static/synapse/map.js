import {random} from './network.mjs';
import {SignalRoutes} from './signal-routes.mjs';
import {presetSettings,readPresets,writePresets} from './presets.mjs';
import {ConnectionRenderer} from './connection-renderer.js';
const peteyEmbed = new URLSearchParams(location.search).get('embed') === 'petey';
if (peteyEmbed) document.documentElement.classList.add('petey-embed');
const $=id=>document.getElementById(id),canvas=$('map'),ctx=canvas.getContext('2d',{alpha:true});
const connectionCanvas=document.createElement('canvas');connectionCanvas.id='connections-canvas';connectionCanvas.setAttribute('aria-hidden','true');canvas.before(connectionCanvas);
let connectionRenderer=null;
try{connectionRenderer=new ConnectionRenderer(connectionCanvas);}catch(error){connectionCanvas.hidden=true;console.info('Using Canvas connection rendering:',error.message);}
connectionCanvas.addEventListener('webglcontextlost',event=>{event.preventDefault();connectionRenderer=null;connectionCanvas.hidden=true;requestDraw();});
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const state={hoverMode:reduced?'glow':'attract',hoverRadius:140,hoverStrength:.65,showNodes:false,nodeSize:1,nodeStyle:'soft',nodeColor:'theme',nodeCustom:'#ffffff',scaleX:1,scaleY:1,layers:18,neurons:28,connections:14,speed:.7,activity:.45,motion:.55,glow:.65,brightness:.65,routeChance:.4,signalWidth:2,fullLength:true,quiet:true,running:!reduced,theme:'black',seed:42};
const cursor={active:false,x:0,y:0};
const camera={x:0,y:0,zoom:1,fit:1};
let width=0,height=0,dpr=1,nodes=[],edges=[],time=0,last=0,frames=0,bursts=[],pointer=null,hover=null,activeCount=0;
const WORLD_W=1800,WORLD_H=920,TAU=Math.PI*2;
let routeSignals;
let palette,glowSprites=[],nodeSprites=[],nodeColors=[];
const fieldX=x=>WORLD_W/2+(x-WORLD_W/2)*state.scaleX;
const fieldY=y=>WORLD_H/2+(y-WORLD_H/2)*state.scaleY;
const themes={
 black:{bg:'#000000',dot:null,purple:'#c4a3ff',amber:'#ffd09b',text:'#777087',base:['#ad8fdd','#cba77f'],node:'#110b1c'},
 aurora:{bg:'#000000',dot:null,purple:'#62f7dc',amber:'#ec8cfa',text:'#668e88',base:['#6dc4ba','#c184d4'],node:'#061916'},
 ember:{bg:'#080302',dot:null,purple:'#ffb45f',amber:'#ff657c',text:'#9a7561',base:['#d69862','#ce6b78'],node:'#201008'},
 dark:{bg:'#090b14',dot:'#202234',purple:'#b299f1',amber:'#e1ae86',text:'#737b9c',base:['#a08bbc','#baa08b'],node:'#171424'},
 light:{bg:'#f8f6fc',dot:'#ddd3ea',purple:'#8d65c0',amber:'#cb9162',text:'#a28ab5',base:['#b7a1d4','#d4b69e'],node:'#f5effb'}
};
function setPalette(){palette=themes[state.theme];document.documentElement.dataset.theme=state.theme;document.documentElement.style.setProperty('--signal-a',palette.purple);document.documentElement.style.setProperty('--signal-b',palette.amber);document.querySelector('meta[name="theme-color"]').content=palette.bg;
 glowSprites=[palette.purple,palette.amber].map(color=>{const c=document.createElement('canvas');c.width=c.height=64;const g=c.getContext('2d'),gradient=g.createRadialGradient(32,32,0,32,32,32);gradient.addColorStop(0,color+'c0');gradient.addColorStop(.2,color+'60');gradient.addColorStop(1,color+'00');g.fillStyle=gradient;g.fillRect(0,0,64,64);return c;});updateNodePalette();}
function build(){const r=random(state.seed);nodes=[];edges=[];bursts=[];hover=null;$('probe').hidden=true;
 for(let l=0;l<state.layers;l++)for(let j=0;j<state.neurons;j++){const spread=.82+.18*Math.sin(l/(state.layers-1)*Math.PI);nodes.push({l,j,bx:l/(state.layers-1)*WORLD_W,by:WORLD_H/2+(j/(state.neurons-1)-.5)*WORLD_H*spread,phase:r()*TAU,x:0,y:0,energy:0,amber:r()<.18});}
 for(let l=0;l<state.layers-1;l++)for(let j=0;j<state.neurons;j++){const picks=Array.from({length:state.neurons},(_,i)=>i);for(let k=picks.length-1;k>0;k--){const p=Math.floor(r()*(k+1));[picks[k],picks[p]]=[picks[p],picks[k]];}for(let k=0;k<Math.min(state.connections,state.neurons);k++)edges.push({from:l*state.neurons+j,to:(l+1)*state.neurons+picks[k],l,phase:r()*9,gate:r(),color:r()<.22?1:0,bend:r()*2-1,weight:.4+r()*.8});}
 routeSignals=new SignalRoutes(edges,state.layers,state.neurons,random(state.seed+901),time);
 connectionRenderer?.setEdges(edges);
 $('node-count').textContent=nodes.length.toLocaleString();$('edge-count').textContent=edges.length.toLocaleString();updateNodes();draw();}
function fit(){const mobile=width<=700;const left=mobile?45:($('controls').hidden?80:300),right=mobile?50:90,top=mobile?245:205,bottom=mobile?210:180;camera.fit=Math.max(.001,Math.min((width-left-right)/(WORLD_W*state.scaleX),(height-top-bottom)/(WORLD_H*state.scaleY)));camera.zoom=camera.fit;camera.x=left+(width-left-right-WORLD_W*camera.zoom)/2;camera.y=top+(height-top-bottom-WORLD_H*camera.zoom)/2;updateZoom();}
function resize(){width=innerWidth;height=innerHeight;dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);fit();draw();}
function updateZoom(){$('zoom-value').textContent=`${Math.round(camera.zoom/camera.fit*100)}%`;}
function updateNodes(){for(const n of nodes){n.x=fieldX(n.bx+Math.sin(time*.42+n.phase)*state.motion*10);n.y=fieldY(n.by+Math.sin(time*.62+n.l*.48+n.j*.26)*state.motion*18);const wave=(Math.sin(time*1.3-n.l*.56+n.j*.31)+1)/2;n.energy=.05+wave*wave*.18;
 if(cursor.active&&state.hoverMode!=='off'&&state.hoverStrength>0){const dx=cursor.x-(n.x*camera.zoom+camera.x),dy=cursor.y-(n.y*camera.zoom+camera.y),distance=Math.hypot(dx,dy),influence=Math.max(0,1-distance/state.hoverRadius)**2;
  n.energy=Math.min(1,n.energy+influence*state.hoverStrength);
  if(state.hoverMode==='attract'||state.hoverMode==='repel'){const direction=state.hoverMode==='attract'?1:-1,amount=direction*influence*state.hoverStrength*.4/camera.zoom;n.x+=dx*amount;n.y+=dy*amount;}
 }}}
function curve(e){const a=nodes[e.from],b=nodes[e.to],dx=b.x-a.x,wave=Math.sin(time*.75+e.l*.6+e.bend*2)*state.motion*17*state.scaleY;return [a.x,a.y,a.x+dx*.46,a.y+wave,b.x-dx*.46,b.y-wave,b.x,b.y];}
function point(c,t){const u=1-t;return [u*u*u*c[0]+3*u*u*t*c[2]+3*u*t*t*c[4]+t*t*t*c[6],u*u*u*c[1]+3*u*u*t*c[3]+3*u*t*t*c[5]+t*t*t*c[7]];}
function fullPath(c,p){p.moveTo(c[0],c[1]);p.bezierCurveTo(c[2],c[3],c[4],c[5],c[6],c[7]);}
function segment(c,t,length,p){const start=Math.max(0,t-length),end=Math.min(1,t);if(start>=end)return;const a=point(c,start);p.moveTo(a[0],a[1]);for(let i=1;i<=8;i++){const q=point(c,start+(end-start)*i/8);p.lineTo(q[0],q[1]);}}
function draw(){if(!width||!nodes.length)return;updateNodes();ctx.setTransform(dpr,0,0,dpr,0,0);ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';ctx.clearRect(0,0,width,height);if(!connectionRenderer){ctx.fillStyle=palette.bg;ctx.fillRect(0,0,width,height);}
 if(palette.dot){ctx.fillStyle=palette.dot;const spacing=26;for(let x=(camera.x%spacing);x<width;x+=spacing)for(let y=camera.y%spacing;y<height;y+=spacing){ctx.beginPath();ctx.arc(x,y,.65,0,TAU);ctx.fill();}}
 ctx.save();ctx.translate(camera.x,camera.y);ctx.scale(camera.zoom,camera.zoom);
 const base=[[],[]],baseCounts=[0,0],tails=[new Path2D(),new Path2D()],charged=Array.from({length:4},()=>[new Path2D(),new Path2D()]),cores=[new Path2D(),new Path2D()],heads=[];
 const routes=routeSignals.sample(time);
 activeCount=0;const selected=hover===null?null:nodes[hover];
 for(let edgeIndex=0;edgeIndex<edges.length;edgeIndex++){const e=edges[edgeIndex],c=connectionRenderer?null:curve(e);if(!connectionRenderer&&state.quiet&&state.brightness>0){const group=base[e.color];if(baseCounts[e.color]++%32===0)group.push(new Path2D());fullPath(c,group.at(-1));}let p=-1;
  if(e.gate<state.activity){const phase=((time-e.l*.29-e.phase)%6.5+6.5)%6.5;p=phase<1.3?phase/1.08:-1;}
  for(const burst of bursts){const distance=e.l-burst.layer;if(distance>=0){const elapsed=time-burst.at-distance*.24;const bp=elapsed/.55;if(bp>=0&&bp<1.22&&(distance>1||Math.abs(nodes[e.from].j-burst.row)<=3+distance*5))p=bp;}}
  if(connectionRenderer){connectionRenderer.signalData[edgeIndex*4]=p;connectionRenderer.signalData[edgeIndex*4+1]=selected&&(e.from===hover||e.to===hover)?1:0;connectionRenderer.signalData[edgeIndex*4+2]=routes.progress[edgeIndex];connectionRenderer.signalData[edgeIndex*4+3]=routes.strength[edgeIndex];}
  else if(selected&&(e.from===hover||e.to===hover)){fullPath(c,tails[e.color]);}
  if(!connectionRenderer&&cursor.active&&state.hoverMode!=='off'&&state.hoverStrength>0){const mid=point(c,.5),distance=Math.hypot(mid[0]*camera.zoom+camera.x-cursor.x,mid[1]*camera.zoom+camera.y-cursor.y);if(distance<state.hoverRadius)fullPath(c,tails[e.color]);}
  if(p>=0&&p<1.22){activeCount++;if(!connectionRenderer){if(state.fullLength){const strength=Math.sin(Math.min(1,p/1.22)*Math.PI);fullPath(c,charged[Math.min(3,Math.floor(strength*4))][e.color]);}segment(c,p,.25,tails[e.color]);segment(c,p,.075,cores[e.color]);if(p<1){const [x,y]=point(c,p);heads.push({x,y,color:e.color,alpha:Math.min(1,p*8)});}}if(p>.78)nodes[e.to].energy=Math.max(nodes[e.to].energy,Math.sin(Math.min(1,(p-.78)/.44)*Math.PI));if(p<.15)nodes[e.from].energy=Math.max(nodes[e.from].energy,.65);}
 }
 const colors=[palette.purple,palette.amber];ctx.lineCap='round';
 if(connectionRenderer)connectionRenderer.draw(nodes,state,camera,palette,time,width,height,dpr,cursor);
 else {
 const light=state.theme==='light';
 for(let i=0;i<2;i++){
  ctx.strokeStyle=palette.base[i];ctx.lineWidth=2.5/camera.zoom;ctx.globalAlpha=Math.min(1,state.brightness*state.glow*(light?.025:.055));for(const path of base[i])ctx.stroke(path);
  ctx.lineWidth=.8/camera.zoom;ctx.globalAlpha=Math.min(1,state.brightness*(light?.36:.52));for(const path of base[i])ctx.stroke(path);
 }
 for(let level=0;level<4;level++)for(let i=0;i<2;i++){
  const strength=(level+1)/4;ctx.strokeStyle=colors[i];
  ctx.lineWidth=7/camera.zoom;ctx.globalAlpha=Math.min(1,strength*state.glow*(light?.025:.065));ctx.stroke(charged[level][i]);
  ctx.lineWidth=2.8/camera.zoom;ctx.globalAlpha=Math.min(1,strength*state.glow*(light?.07:.15));ctx.stroke(charged[level][i]);
  ctx.lineWidth=1/camera.zoom;ctx.globalAlpha=strength*(light?.43:.68);ctx.stroke(charged[level][i]);
 }
 for(let i=0;i<2;i++){ctx.strokeStyle=colors[i];ctx.globalAlpha=Math.min(1,.09*state.glow);ctx.lineWidth=6/camera.zoom;ctx.stroke(tails[i]);ctx.globalAlpha=light?.35:.5;ctx.lineWidth=.9/camera.zoom;ctx.stroke(tails[i]);ctx.globalAlpha=.85;ctx.lineWidth=1.15*state.signalWidth/camera.zoom;ctx.stroke(cores[i]);}
 for(const h of heads){const size=(6+state.glow*14)/camera.zoom;ctx.globalAlpha=Math.min(1,h.alpha*state.glow*.6);ctx.drawImage(glowSprites[h.color],h.x-size/2,h.y-size/2,size,size);ctx.globalAlpha=h.alpha*.9;ctx.fillStyle=colors[h.color];ctx.beginPath();ctx.arc(h.x,h.y,Math.max(.9/camera.zoom,1.1),0,TAU);ctx.fill();}
 }
 if(!connectionRenderer)drawRouteSignals(routes);
 for(let i=0;i<edges.length;i++){if(routes.strength[i]>0){const p=routes.progress[i];if(p>=0&&p<=1){activeCount++;nodes[edges[i].from].energy=Math.max(nodes[edges[i].from].energy,(1-p)*routes.strength[i]);nodes[edges[i].to].energy=Math.max(nodes[edges[i].to].energy,p*routes.strength[i]);}}}
 drawNodes();
 ctx.globalAlpha=1;ctx.fillStyle=palette.text;ctx.font=`${8/camera.zoom}px 'DM Sans',sans-serif`;ctx.textAlign='center';for(let l=0;l<state.layers;l++){const stride=Math.max(1,Math.ceil(38/(WORLD_W*state.scaleX/(state.layers-1)*camera.zoom)));if(l>0&&l<state.layers-1&&(l%stride||state.layers-1-l<stride))continue;ctx.fillText(l===0?'INPUT':l===state.layers-1?'OUTPUT':String(l).padStart(2,'0'),fieldX(l/(state.layers-1)*WORLD_W),fieldY(0)-38/camera.zoom);}
 ctx.restore();ctx.globalAlpha=1;
 if(cursor.active&&state.hoverMode!=='off'&&state.hoverStrength>0){const radius=state.hoverRadius;ctx.globalAlpha=Math.min(.28,state.hoverStrength*.12);ctx.drawImage(glowSprites[0],cursor.x-radius,cursor.y-radius,radius*2,radius*2);ctx.strokeStyle=palette.purple;ctx.lineWidth=1;ctx.globalAlpha=Math.min(.3,state.hoverStrength*.16);ctx.beginPath();ctx.arc(cursor.x,cursor.y,radius,0,TAU);ctx.stroke();ctx.globalAlpha=1;}
 if(frames%8===0||!state.running)$('signal-count').textContent=activeCount.toLocaleString();}
let redrawPending=false;
function requestDraw(){redrawPending=true;}
function drawRouteSignals(routes){
 ctx.strokeStyle=palette.purple;
 for(let i=0;i<edges.length;i++){
  const alpha=routes.strength[i];if(!alpha)continue;
  const c=curve(edges[i]),p=routes.progress[i];ctx.globalAlpha=alpha*.6;ctx.lineWidth=1.15/camera.zoom;const path=new Path2D();fullPath(c,path);ctx.stroke(path);
  // A tapered swelling straddles neighboring edges as the head travels.
  for(let step=0;step<20;step++){const t=(step+.5)/20,swell=Math.exp(-(((t-p)/.23)**2));if(swell<.015)continue;const a=point(c,step/20),b=point(c,(step+1)/20);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.lineWidth=(1+state.signalWidth*2.5*swell)/camera.zoom;ctx.globalAlpha=alpha*.85;ctx.stroke();}
 }
}
function updateNodePalette(){
 const single=state.nodeColor==='custom'?state.nodeCustom:state.theme==='light'?'#534d63':'#f1f1f5';
 nodeColors=state.nodeColor==='theme'?[palette.purple,palette.amber]:[single,single];
 nodeSprites=state.nodeColor==='theme'?glowSprites:nodeColors.map(color=>{
  const c=document.createElement('canvas');c.width=c.height=64;const g=c.getContext('2d'),gradient=g.createRadialGradient(32,32,0,32,32,32);
  gradient.addColorStop(0,color+'c0');gradient.addColorStop(.2,color+'60');gradient.addColorStop(1,color+'00');g.fillStyle=gradient;g.fillRect(0,0,64,64);return c;
 });
}
function nodeShape(n,r){
 ctx.beginPath();
 if(state.nodeStyle==='diamond'){ctx.moveTo(n.x,n.y-r);ctx.lineTo(n.x+r,n.y);ctx.lineTo(n.x,n.y+r);ctx.lineTo(n.x-r,n.y);ctx.closePath();}
 else ctx.arc(n.x,n.y,r,0,TAU);
}
function drawNodes(){
 if(!state.showNodes)return;
 for(let i=0;i<nodes.length;i++){
  const n=nodes[i],color=n.amber?1:0,r=(3.2+n.energy*1.7)*state.nodeSize,soft=state.nodeStyle==='soft';
  if(soft&&n.energy>.25&&state.glow>0){const size=(9+n.energy*18)*state.nodeSize/Math.sqrt(camera.zoom);ctx.globalAlpha=Math.min(1,n.energy*state.glow*.7);ctx.drawImage(nodeSprites[color],n.x-size/2,n.y-size/2,size,size);}
  nodeShape(n,r);
  if(soft){ctx.globalAlpha=1;ctx.fillStyle=palette.node;ctx.fill();}
  ctx.strokeStyle=nodeColors[color];ctx.globalAlpha=.45+n.energy*.5;ctx.lineWidth=(i===hover?1.8:.85)/Math.sqrt(camera.zoom);ctx.stroke();
  if(state.nodeStyle!=='ring'){ctx.globalAlpha=soft?n.energy*.8:.6+n.energy*.4;ctx.fillStyle=nodeColors[color];ctx.fill();}
  if(i===hover){ctx.globalAlpha=.65;nodeShape(n,r+4/camera.zoom);ctx.stroke();}
 }
}
function tick(now){const dt=Math.min(.05,(now-last)/1000||0);last=now;if(state.running){time+=dt*state.speed;routeSignals.advance(time,state.routeChance);bursts=bursts.filter(b=>time-b.at<state.layers*.24+2);redrawPending=false;draw();frames++;}else if(redrawPending){redrawPending=false;draw();}requestAnimationFrame(tick);}
function playback(){$('play').textContent=state.running?'Ⅱ':'▶';$('play').setAttribute('aria-label',state.running?'Pause animation':'Resume animation');$('live-status').innerHTML=`<i></i> ${state.running?'NETWORK IS ALIVE':'NETWORK IS PAUSED'}`;}
$('play').onclick=()=>{state.running=!state.running;playback();};
function pulse(layer=0,row=Math.floor(state.neurons/2)){bursts.push({at:time,layer,row});if(bursts.length>12)bursts.shift();state.running=true;playback();}
$('pulse').onclick=()=>pulse();
for(const key of ['layers','neurons','connections','speed','activity','motion','glow']){$(key).oninput=e=>{const v=+e.target.value;state[key]=['layers','neurons','connections'].includes(key)?v:v/100;$(key+'-value').textContent=key==='speed'?`${(v/100).toFixed(1)}×`:['activity','motion','glow'].includes(key)?`${v}%`:v;if(['layers','neurons','connections'].includes(key)){if(key==='neurons'){const max=Math.min(64,v);$('connections').max=max;if(state.connections>max){state.connections=max;$('connections').value=max;$('connections-value').textContent=max;}}build();}else{updateNodes();requestDraw();}for(const b of document.querySelectorAll('[data-preset]')){b.classList.remove('selected');b.setAttribute('aria-pressed','false');}};}
for(const [id,key] of [['width-scale','scaleX'],['height-scale','scaleY']]){
 $(id).oninput=e=>{state[key]=Number(e.target.value)/100;$(id+'-value').textContent=e.target.value+'%';hover=null;$('probe').hidden=true;updateNodes();requestDraw();};
}
$('show-nodes').onchange=e=>{state.showNodes=e.target.checked;$('node-options').disabled=!state.showNodes;hover=null;$('probe').hidden=true;requestDraw();};
$('node-size').oninput=e=>{state.nodeSize=Number(e.target.value)/100;$('node-size-value').textContent=e.target.value+'%';requestDraw();};
$('node-style').onchange=e=>{state.nodeStyle=e.target.value;requestDraw();};
$('node-color').onchange=e=>{state.nodeColor=e.target.value;$('node-custom-control').hidden=state.nodeColor!=='custom';updateNodePalette();requestDraw();};
$('node-custom').oninput=e=>{state.nodeCustom=e.target.value;updateNodePalette();requestDraw();};
$('quiet').onchange=e=>{state.quiet=e.target.checked;requestDraw();};$('regenerate').onclick=()=>{state.seed++;build();};
for(const b of document.querySelectorAll('[data-preset]'))b.onclick=()=>{const preset={drift:[70,45,55,65],surge:[110,70,75,80],storm:[170,100,100,100]}[b.dataset.preset];['speed','activity','motion','glow'].forEach((key,i)=>{$(key).value=preset[i];$(key).dispatchEvent(new Event('input'));});b.classList.add('selected');b.setAttribute('aria-pressed','true');};
$('theme').onchange=e=>{state.theme=e.target.value;setPalette();requestDraw();};
$('brightness').oninput=e=>{state.brightness=Number(e.target.value)/100;$('brightness-value').textContent=e.target.value+'%';requestDraw();};
$('hover-mode').value=state.hoverMode;
$('hover-mode').onchange=e=>{state.hoverMode=e.target.value;requestDraw();};
$('hover-radius').oninput=e=>{state.hoverRadius=Number(e.target.value);$('hover-radius-value').textContent=e.target.value+' px';requestDraw();};
$('hover-strength').oninput=e=>{state.hoverStrength=Number(e.target.value)/100;$('hover-strength-value').textContent=e.target.value+'%';requestDraw();};
$('route-chance').oninput=e=>{state.routeChance=Number(e.target.value)/100;$('route-chance-value').textContent=e.target.value+'%';requestDraw();};
$('signal-width').oninput=e=>{state.signalWidth=Number(e.target.value)/100;$('signal-width-value').textContent=state.signalWidth.toFixed(1)+'×';requestDraw();};
$('full-length').onchange=e=>{state.fullLength=e.target.checked;requestDraw();};
$('controls-toggle').onclick=()=>{const hidden=!$('controls').hidden;$('controls').hidden=hidden;$('controls-toggle').setAttribute('aria-expanded',String(!hidden));fit();requestDraw();};
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{$('interaction-hint').textContent='Fullscreen is unavailable in this browser.';}};
function zoom(factor,x=width/2,y=height/2){const next=Math.max(camera.fit*.35,Math.min(camera.fit*16,camera.zoom*factor)),ratio=next/camera.zoom;camera.x=x-(x-camera.x)*ratio;camera.y=y-(y-camera.y)*ratio;camera.zoom=next;updateZoom();requestDraw();}
$('zoom-in').onclick=()=>zoom(1.25);$('zoom-out').onclick=()=>zoom(.8);$('fit').onclick=()=>{fit();requestDraw();};
canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(-e.deltaY*.001),e.clientX,e.clientY);},{passive:false});
function nearest(x,y){if(!state.showNodes)return null;const wx=(x-camera.x)/camera.zoom,wy=(y-camera.y)/camera.zoom;let found=null,best=Math.max(12/camera.zoom,4.9*state.nodeSize+3/camera.zoom)**2;for(let i=0;i<nodes.length;i++){const n=nodes[i],d=(wx-n.x)**2+(wy-n.y)**2;if(d<best){best=d;found=i;}}return found;}
canvas.onpointerdown=e=>{cursor.active=false;requestDraw();pointer={id:e.pointerId,x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,moved:false};canvas.setPointerCapture(e.pointerId);canvas.classList.add('dragging');};
canvas.onpointermove=e=>{cursor.x=e.clientX;cursor.y=e.clientY;cursor.active=e.pointerType!=='touch'&&!pointer;if(pointer&&pointer.id===e.pointerId){const dx=e.clientX-pointer.x,dy=e.clientY-pointer.y;if(Math.hypot(e.clientX-pointer.startX,e.clientY-pointer.startY)>4)pointer.moved=true;if(pointer.moved){camera.x+=dx;camera.y+=dy;requestDraw();}pointer.x=e.clientX;pointer.y=e.clientY;$('probe').hidden=true;}else{hover=nearest(e.clientX,e.clientY);if(hover!==null){const n=nodes[hover];$('probe').textContent=`Layer ${n.l+1} · Neuron ${n.j+1} · Click to spark`;$('probe').style.left=Math.min(width-210,e.clientX+15)+'px';$('probe').style.top=Math.max(75,e.clientY-35)+'px';$('probe').hidden=false;}else $('probe').hidden=true;if(!state.running)requestDraw();}};
canvas.onpointerup=e=>{if(pointer?.id!==e.pointerId)return;if(!pointer.moved){const i=nearest(e.clientX,e.clientY);if(i!==null){const n=nodes[i];pulse(Math.min(n.l,state.layers-2),n.j);}else{const l=Math.round((((e.clientX-camera.x)/camera.zoom-WORLD_W/2)/state.scaleX+WORLD_W/2)/WORLD_W*(state.layers-1)),row=Math.round((((e.clientY-camera.y)/camera.zoom-WORLD_H/2)/state.scaleY+WORLD_H/2)/WORLD_H*(state.neurons-1));pulse(Math.max(0,Math.min(state.layers-2,l)),Math.max(0,Math.min(state.neurons-1,row)));}}pointer=null;canvas.classList.remove('dragging');cursor.active=e.pointerType!=='touch';cursor.x=e.clientX;cursor.y=e.clientY;requestDraw();};
canvas.onpointercancel=()=>{pointer=null;cursor.active=false;canvas.classList.remove('dragging');requestDraw();};canvas.onpointerleave=()=>{cursor.active=false;hover=null;$('probe').hidden=true;requestDraw();};
$('capture').onclick=()=>{draw();const capture=document.createElement('canvas');capture.width=canvas.width;capture.height=canvas.height;const output=capture.getContext('2d');if(connectionRenderer)output.drawImage(connectionCanvas,0,0);output.drawImage(canvas,0,0);capture.toBlob(blob=>{if(!blob)return;const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='synapse-living-network.png';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});};
const presetDefaults={...state};let savedPresets=[];
function presetMessage(message){$('preset-status').textContent=message;}
function renderPresetList(selected=''){
 $('saved-preset').replaceChildren(new Option('Choose a preset…',''),...savedPresets.map(p=>new Option(p.name,p.name)));
 $('saved-preset').value=selected;$('delete-preset').disabled=!selected;
}
function syncPresetControls(){
 const controls={layers:'layers',neurons:'neurons',connections:'connections',speed:'speed',activity:'activity',motion:'motion',glow:'glow',brightness:'brightness','route-chance':'routeChance','signal-width':'signalWidth','node-size':'nodeSize','width-scale':'scaleX','height-scale':'scaleY','hover-strength':'hoverStrength'};
 $('connections').max=state.neurons;
 for(const [id,key] of Object.entries(controls)){
  const integral=['layers','neurons','connections'].includes(key),value=integral?state[key]:Math.round(state[key]*100);$(id).value=value;
  $(id+'-value').textContent=integral?String(value):['speed','signalWidth'].includes(key)?state[key].toFixed(1)+'×':value+'%';
 }
 $('hover-radius').value=state.hoverRadius;$('hover-radius-value').textContent=state.hoverRadius+' px';
 for(const [id,key] of Object.entries({'hover-mode':'hoverMode','theme':'theme','node-style':'nodeStyle','node-color':'nodeColor','node-custom':'nodeCustom'}))$(id).value=state[key];
 for(const [id,key] of Object.entries({'show-nodes':'showNodes','quiet':'quiet','full-length':'fullLength'}))$(id).checked=state[key];
 $('node-options').disabled=!state.showNodes;$('node-custom-control').hidden=state.nodeColor!=='custom';
 for(const button of document.querySelectorAll('[data-preset]')){button.classList.remove('selected');button.setAttribute('aria-pressed','false');}
}
try{savedPresets=readPresets(localStorage,presetDefaults);}catch{presetMessage('Could not read saved presets. Browser storage may be unavailable.');}
renderPresetList();
$('save-preset').onclick=()=>{
 const name=$('preset-name').value.trim();if(!name){presetMessage('Enter a name for this preset.');$('preset-name').focus();return;}
 const next=savedPresets.filter(p=>p.name!==name);next.push({name,settings:presetSettings(state,presetDefaults)});
 try{writePresets(localStorage,next);savedPresets=next;renderPresetList(name);presetMessage('Saved “'+name+'”.');}catch{presetMessage('Could not save. Browser storage may be full or unavailable.');}
};
$('saved-preset').onchange=()=>{
 const preset=savedPresets.find(p=>p.name===$('saved-preset').value);$('delete-preset').disabled=!preset;if(!preset)return;
 Object.assign(state,presetSettings(preset.settings,presetDefaults));syncPresetControls();setPalette();build();fit();requestDraw();$('preset-name').value=preset.name;presetMessage('Loaded “'+preset.name+'”.');
};
$('delete-preset').onclick=()=>{
 const name=$('saved-preset').value;if(!name)return;const next=savedPresets.filter(p=>p.name!==name);
 try{writePresets(localStorage,next);savedPresets=next;renderPresetList();$('preset-name').value='';presetMessage('Deleted “'+name+'”.');}catch{presetMessage('Could not delete this preset from browser storage.');}
};
function markPresetChanged(event){if(event.target.closest('.saved-presets'))return;if($('saved-preset').value){renderPresetList();presetMessage('Modified. Save with the same name to update it.');}}
$('controls').addEventListener('input',markPresetChanged);$('controls').addEventListener('change',markPresetChanged);$('regenerate').addEventListener('click',markPresetChanged);$('theme').addEventListener('change',markPresetChanged);
window.addEventListener('keydown',e=>{if(/INPUT|SELECT|BUTTON|A/.test(document.activeElement.tagName))return;if(e.code==='Space'){e.preventDefault();$('play').click();}if(e.key==='f')$('fit').click();});
window.addEventListener('resize',resize);
if(innerWidth<=700){$('controls').hidden=true;$('controls-toggle').setAttribute('aria-expanded','false');}
setPalette();build();resize();playback();if(!reduced){time=3.5;updateNodes();draw();}requestAnimationFrame(tick);
// Read-only diagnostic snapshot for checking rendering and topology.
window.synapseSnapshot=()=>({neurons:nodes.length,connections:edges.length,activeSignals:activeCount,time,running:state.running,zoom:camera.zoom,theme:state.theme,background:palette.bg,hoverActive:cursor.active,settings:presetSettings(state,presetDefaults),routeChance:state.routeChance,signalWidth:state.signalWidth,activeRoutes:routeSignals.routes.length,routesLaunched:routeSignals.launched,routesCompleted:routeSignals.completed,renderer:connectionRenderer?'webgl2':'canvas2d',showNodes:state.showNodes,nodeSize:state.nodeSize,nodeStyle:state.nodeStyle,nodeColor:state.nodeColor,nodeCustom:state.nodeCustom,fullLength:state.fullLength,brightness:state.brightness,scaleX:state.scaleX,scaleY:state.scaleY,bounds:{left:Math.min(...nodes.map(n=>n.x)),right:Math.max(...nodes.map(n=>n.x)),top:Math.min(...nodes.map(n=>n.y)),bottom:Math.max(...nodes.map(n=>n.y))},valid:edges.every(e=>nodes[e.to].l===nodes[e.from].l+1)});

if (peteyEmbed) {
  let peteyState = 'idle';
  const themesByState = {idle:'black', listening:'ember', thinking:'black', speaking:'aurora', muted:'dark', error:'ember'};
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== window.parent || event.data?.type !== 'petey-visual-state') return;
    const {active, phase, energy} = event.data;
    const shouldRun = Boolean(active) && !document.hidden && !reduced;
    if (state.running !== shouldRun) {state.running = shouldRun; playback();}
    if (!active) return;
    const nextState = Object.hasOwn(themesByState, phase) ? phase : 'idle';
    if (nextState !== peteyState) {
      peteyState = nextState;
      state.theme = themesByState[nextState];
      setPalette();
      if (nextState === 'listening' || nextState === 'speaking' || nextState === 'error') pulse();
    }
    const level = Math.max(0, Math.min(1, Number(energy) || 0));
    state.activity = Math.min(1, .18 + level * .75);
    state.routeChance = Math.min(1, .12 + level * .8);
    state.glow = .5 + level * 1.25;
    state.signalWidth = 1.5 + level * 2;
    if (!shouldRun) {state.running = false; requestDraw();}
  });
  document.addEventListener('visibilitychange', () => {if (document.hidden) state.running = false;});
  state.running = false;
  playback();
  requestDraw();
}
