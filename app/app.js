'use strict';
const $ = id => document.getElementById(id);
function element(tag, text, parent) { const e=document.createElement(tag); if(text) e.textContent=text; if(parent)parent.append(e); return e; }
function link(text, url, parent) { const e=element('a',text,parent); e.href=url; e.target='_blank'; e.rel='noopener noreferrer'; return e; }
const memory=new Map();
async function textFetch(url) { const response=await fetch(url,{credentials:'omit',signal:AbortSignal.timeout(15000)}); if(!response.ok)throw Error('HTTP '+response.status); const text=await response.text(); if(text.length>1500000)throw Error('File too large for this viewer'); return text; }
async function boot(){
 const data=JSON.parse(await textFetch('data.json'));
 $('provenance').textContent=JSON.stringify(data.assets,null,2);
 for(const repo of data.repositories){
  const box=element('article','',$('repos')); box.className='repo'; element('h3',repo.name,box);
  const base='https://github.com/iamdarshg/'+repo.name;
  link('Pinned commit',base+'/tree/'+repo.commit,box); link('Latest '+repo.branch,base+'/tree/'+repo.branch,box); link('Download pinned source ZIP','https://codeload.github.com/iamdarshg/'+repo.name+'/zip/'+repo.commit,box);
  element('p','Snapshot: '+repo.commit,box);
  const label=element('label','Allowlisted source file ',box), select=element('select','',label);
  for(const f of repo.files){const option=element('option',f.path,select);option.value=f.path;}
  const live=element('button','Open from GitHub',box), cached=element('button','Open bundled snapshot',box), status=element('p','Not opened. No GitHub content fetched yet.',box);status.setAttribute('role','status');
  const output=element('pre','Choose a file and press Open to inspect actual source text.',box);
  async function open(remote){const f=repo.files.find(f=>f.path===select.value); if(!f)return; const url=remote?'https://raw.githubusercontent.com/iamdarshg/'+repo.name+'/'+repo.commit+'/'+f.path:f.cache;status.textContent='Loading '+(remote?'GitHub':'bundled snapshot')+'…';live.disabled=cached.disabled=true;
   try{const hit=memory.has(url);const text=hit?memory.get(url):await textFetch(url);memory.set(url,text);output.textContent=text;status.textContent=(hit?'Memory cache':'Loaded '+(remote?'from GitHub':'bundled pinned snapshot'))+' · '+f.path+' · rendered as inert text';}
   catch(e){status.textContent='Could not load: '+e.message+'. Try bundled snapshot or direct GitHub link. GitHub rate limits, network/CORS policy or file:// may block fetch; use localhost.';output.textContent='No remote content loaded.';}finally{live.disabled=cached.disabled=false;}}
  live.onclick=()=>open(true);cached.onclick=()=>open(false);
 }
}
// The read-only explorer initializes repository views in explorer.js.
$('pcb').onchange=()=>{const side=$('pcb').value;$('board').src='assets/esc_final_'+side+'.png';$('board').alt='Existing ESC revision-B '+side+' PCB design render';$('board-caption').textContent=side+' render · release blocked · no fabrication/test claim';};
let vertices=[], angle=.52, tilt=.44, zoom=1, generation=0;
const canvas=$('mesh'), ctx=canvas.getContext('2d');
function draw(){if(!ctx)return;ctx.clearRect(0,0,960,480);ctx.strokeStyle='#80d9c3';ctx.lineWidth=.6;const ca=Math.cos(angle),sa=Math.sin(angle),ct=Math.cos(tilt),st=Math.sin(tilt);function project(p){const x=p[0]*ca-p[2]*sa,z=p[0]*sa+p[2]*ca;return [480+x*180*zoom,240+(p[1]*ct-z*st)*180*zoom];}ctx.beginPath();for(let i=0;i<vertices.length;i+=3){for(let j=0;j<4;j++){const p=project(vertices[i+j%3]);if(j===0)ctx.moveTo(...p);else ctx.lineTo(...p);}}ctx.stroke();}
async function loadModel(){const current=++generation, file=$('model').value; $('download').href='assets/'+file;$('mesh-status').textContent='Loading actual local STL…';try{const r=await fetch('assets/'+file);if(!r.ok)throw Error('HTTP '+r.status);const bytes=await r.arrayBuffer();if(current!==generation)return;const view=new DataView(bytes);let points=[];const n=bytes.byteLength>=84?view.getUint32(80,true):0;if(84+n*50===bytes.byteLength){for(let i=0;i<n;i++){for(let j=0;j<3;j++){let o=84+i*50+12+j*12;points.push([view.getFloat32(o,true),view.getFloat32(o+4,true),view.getFloat32(o+8,true)]);}}}else{const text=new TextDecoder().decode(bytes);for(const m of text.matchAll(/vertex\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)/g))points.push(m.slice(1).map(Number));}if(!points.length||points.length%3||points.some(p=>p.some(v=>!Number.isFinite(v))))throw Error('Unsupported STL');const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];for(const p of points)for(let k=0;k<3;k++){min[k]=Math.min(min[k],p[k]);max[k]=Math.max(max[k],p[k]);}const scale=Math.max(...max.map((v,k)=>v-min[k]))/2||1;vertices=points.map(p=>p.map((v,k)=>(v-(max[k]+min[k])/2)/scale));$('mesh-status').textContent=(points.length/3).toLocaleString()+' triangles · '+(file.startsWith('real_')?'historical superseded motor housing':'Phase-15 rotor, unresolved integration')+' · wireframe, not simulation';draw();}catch(e){$('mesh-status').textContent='Model preview unavailable: '+e.message+'. Download STL or inspect PCB views. Use localhost, not file://.';}}
$('model').onchange=loadModel;for(const id of ['rotate','tilt','zoom'])$(id).oninput=()=>{angle=Number($('rotate').value)*Math.PI/180;tilt=Number($('tilt').value)*Math.PI/180;zoom=Number($('zoom').value);draw();};let last=null;canvas.onpointerdown=e=>{last=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};canvas.onpointermove=e=>{if(!last)return;angle+=(e.clientX-last[0])*.01;tilt+=(e.clientY-last[1])*.01;last=[e.clientX,e.clientY];draw();};canvas.onpointerup=canvas.onpointercancel=()=>last=null;canvas.onwheel=e=>{e.preventDefault();zoom=Math.max(.3,Math.min(3,zoom-e.deltaY*.001));$('zoom').value=zoom;draw();};loadModel();
async function loadPhotos(){
 const button=$('photos'), output=$('photo-results'), section=output.closest('details');button.disabled=true;section.hidden=true;output.textContent='';let loaded=0;
 try{const manifest=JSON.parse(await textFetch('photos.json'));
  for(const photo of manifest.photos){
   if(!['drone-arm','drone-mech'].includes(photo.repository)||!['docs/media/build/01-board-assembly.jpg','docs/media/build/01-airframe-assembly.jpg'].includes(photo.path)||!/^[-\w.]+$/.test(photo.branch))continue;
   const box=document.createElement('figure');
   try{const url='https://raw.githubusercontent.com/iamdarshg/'+photo.repository+'/'+photo.branch+'/'+photo.path;const response=await fetch(url,{credentials:'omit',signal:AbortSignal.timeout(10000),cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);const blob=await response.blob();if(blob.size>10000000||!blob.type.startsWith('image/'))throw Error('Not a small image');const objectURL=URL.createObjectURL(blob);const image=new Image();image.alt=photo.displayName+' — physical-build photograph';try{await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Image decode timeout')),5000);image.onload=()=>{clearTimeout(timer);resolve();};image.onerror=()=>{clearTimeout(timer);reject(Error('Image decode failed'));};image.src=objectURL;});box.append(image);element('figcaption',[photo.displayName,photo.status,photo.captureDate,photo.caption,photo.contribution,'Live development photograph'].filter(Boolean).join(' · '),box);output.append(box);loaded++;section.hidden=false;}finally{URL.revokeObjectURL(objectURL);}}
   catch(e){console.info('Development image omitted:',e.message);}
  }
 }catch(e){console.info('Development media omitted:',e.message);}finally{button.disabled=false;section.hidden=loaded===0;}
}
$('photos').onclick=loadPhotos;
