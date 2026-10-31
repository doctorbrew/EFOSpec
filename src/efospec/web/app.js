'use strict';
const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem('efospec-token') || '';
sessionStorage.setItem('efospec-token', token);
history.replaceState(null, '', location.pathname);
let original, displayed, recipe, raster, active = 0, job = null, polling = null, skyFraction = null;
const results = new Map();
let historyRecords = [];
const copy = value => JSON.parse(JSON.stringify(value));
function status(message, error=false) { $('status').textContent=message; $('status').classList.toggle('error',error); }
async function api(path, body) {
  const response = await fetch(path,{headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    ...(body === undefined ? {} : {method:'POST',body:JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}
async function attempt(action) { try { return await action(); } catch(error) { status(error.message,true); } }
function download(blob, name) {
  const a=document.createElement('a'); const url=URL.createObjectURL(blob);
  a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function downloadFile(path,name) {
  const response=await fetch(path,{headers:{Authorization:'Bearer '+token}});
  if (!response.ok) throw new Error((await response.json()).error);
  download(await response.blob(),name);
}
function option(value,label) { const node=document.createElement('option');node.value=value;node.textContent=label;return node; }
function button(text,action) { const b=document.createElement('button');b.textContent=text;b.className='secondary';b.onclick=()=>attempt(action);return b; }
function numeric(labelText,value,change) {
  const label=document.createElement('label');label.append(document.createTextNode(labelText));
  const input=document.createElement('input');input.type='number';input.step='0.1';input.value=value;
  input.setAttribute('aria-label',labelText);input.onchange=()=>{change(Number(input.value));edited();};label.append(input);return label;
}
function manual() { if (recipe.source_mode!=='manual') {recipe.source_mode='manual';recipe.objects=[copy(original.primary)];active=0;} }
function editor() {
  $('source-mode').value=recipe.source_mode;$('sky-mode').value=recipe.sky.mode;
  $('objects').replaceChildren();
  recipe.objects.forEach((obj,index)=>{
    const card=document.createElement('div');card.className='object'+(active===index?' active':'');
    const head=document.createElement('div');head.className='object-head';
    head.append(button(index===active?'● '+obj.id:'Select '+obj.id,()=>{active=index;editor();drawAll();}));
    if(index) head.append(button('Remove',()=>{recipe.objects.splice(index,1);active=0;editor();edited();}));
    card.append(head);
    const name=document.createElement('label');name.textContent='Source label';
    const text=document.createElement('input');text.value=obj.label;text.setAttribute('aria-label',obj.id+' label');
    text.onchange=()=>{obj.label=text.value;edited();};name.append(text);card.append(name);
    const kind=document.createElement('select');kind.setAttribute('aria-label',obj.id+' source type');
    kind.append(option('point','Point source'),option('galaxy','Galaxy (inspect boxcar)'));kind.value=obj.kind;
    kind.onchange=()=>{obj.kind=kind.value;if(obj.kind==='galaxy'){$('method').value='boxcar';drawAll();}edited();};card.append(kind);
    const fields=document.createElement('div');fields.className='fields';
    [['spec','Spectral pixel'],['spat','Spatial pixel'],['fwhm','FWHM (px)'],['radius','Half-width (px)']].forEach(([key,label])=>{
      fields.append(numeric(obj.id+' '+label,Math.round(obj[key]*1000)/1000,v=>{obj[key]=v;}));
    });card.append(fields);$('objects').append(card);
  });
  $('add-source').disabled=recipe.source_mode!=='manual'||recipe.objects.length>=2;
  $('add-band').disabled=recipe.sky.mode!=='regions';$('bands').replaceChildren();
  for(const mode of ['include','exclude']) recipe.sky[mode].forEach((band,index)=>{
    const row=document.createElement('div');row.className='band';const title=document.createElement('strong');title.textContent=mode==='include'?'Include sky':'Exclude sky';row.append(title);
    row.append(numeric(mode+' lower',band[0],v=>band[0]=v),numeric(mode+' upper',band[1],v=>band[1]=v),
      button('×',()=>{recipe.sky[mode].splice(index,1);editor();edited();}));$('bands').append(row);
  });
}
let validationVersion=0;
async function edited() {
  drawAll(); const version=++validationVersion;
  try {
    const checked=await api('/api/validate',{product:$('exposure').value,recipe});
    if(version!==validationVersion)return;
    skyFraction=checked.sky_fraction;drawAll();
    status('Recipe ready. Extraction will create a new revision.');
  } catch(error) {if(version===validationVersion){skyFraction=null;status(error.message,true);}}
}
async function show(data) {
  displayed=data;raster=new Image();await new Promise((resolve,reject)=>{raster.onload=resolve;raster.onerror=reject;raster.src=data.image;});
  $('target').textContent=`${data.object} (EFOSC2 / ${data.grism} · ${Math.round(data.exptime)}s)`;
  $('profile-bin').replaceChildren(...data.profiles.map((p,i)=>option(i,`${Math.round(p.range[0])}–${Math.round(p.range[1])} Å`)));
  drawAll();
}
async function loadExposure() {
  status('Reading saved detector window…');
  const data=await api('/api/exposure?id='+encodeURIComponent($('exposure').value));
  original=data;recipe=copy(data.recipe);active=0;skyFraction=null;results.clear();
  $('result').replaceChildren(option('original','Original reduction'));$('downloads').replaceChildren();
  $('revision-path').textContent='Original products stay unchanged.';
  const [ny,nx]=data.window.shape,[y,x]=data.window.origin;
  $('window-note').textContent=`Saved window: ${nx} × ${ny} pixels. Spatial ${x}–${x+nx-1}; spectral ${y}–${y+ny-1}. Crop widening is not available.`;
  for (const revision of historyRecords.filter(r=>r.product===$('exposure').value)) {
    for (const product of revision.products) {const key=revision.id+'/'+product;results.set(key,{job:revision.id,product});$('result').append(option(key,'Saved · '+product+' · '+revision.id.slice(0,15)));}
  }
  editor();await show(data);status('Original reduction loaded. Choose manual anchors to edit the extraction.');
}
function axes(canvas,xmin,xmax,ymin,ymax,xlabel,ylabel) {
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);ctx.fillStyle='#fffef9';ctx.fillRect(0,0,w,h);
  const box={l:83,r:w-26,t:16,b:h-48};
  const x=v=>box.l+(v-xmin)/(xmax-xmin)*(box.r-box.l),y=v=>box.b-(v-ymin)/(ymax-ymin)*(box.b-box.t);
  ctx.font='15px Avenir, Arial';ctx.fillStyle='#586359';ctx.strokeStyle='#bfc8bc';ctx.lineWidth=1;
  ctx.strokeRect(box.l,box.t,box.r-box.l,box.b-box.t);
  for(let i=0;i<=5;i++){
    const xv=xmin+(xmax-xmin)*i/5, px=x(xv);ctx.beginPath();ctx.moveTo(px,box.b);ctx.lineTo(px,box.b-6);ctx.moveTo(px,box.t);ctx.lineTo(px,box.t+6);ctx.stroke();
    ctx.textAlign='center';ctx.fillText(xv.toFixed(0),px,box.b+22);
    const yv=ymin+(ymax-ymin)*i/5,py=y(yv);ctx.beginPath();ctx.moveTo(box.l,py);ctx.lineTo(box.l+6,py);ctx.stroke();
    ctx.textAlign='right';ctx.fillText(Math.abs(yv)>1e4?yv.toExponential(1):yv.toFixed(1),box.l-9,py+5);
  }
  ctx.textAlign='center';ctx.fillText(xlabel,(box.l+box.r)/2,h-7);
  ctx.save();ctx.translate(19,(box.t+box.b)/2);ctx.rotate(-Math.PI/2);ctx.fillText(ylabel,0,0);ctx.restore();
  return {ctx,box,x,y};
}
function line(ctx,x,y,xx,yy,color,width=1.5) {
  ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();let started=false;
  xx.forEach((v,i)=>{if(yy[i]===null||!Number.isFinite(yy[i])){started=false;return;}if(!started){ctx.moveTo(x(v),y(yy[i]));started=true;}else ctx.lineTo(x(v),y(yy[i]));});ctx.stroke();
}
function clipping(a,draw) {const {ctx,box}=a;ctx.save();ctx.beginPath();ctx.rect(box.l,box.t,box.r-box.l,box.b-box.t);ctx.clip();draw();ctx.restore();}
function extent(values) {const good=values.filter(v=>v!==null&&Number.isFinite(v)).sort((a,b)=>a-b);if(!good.length)return[-1,1];let lo=good[Math.floor(good.length*.01)],hi=good[Math.floor((good.length-1)*.99)];const margin=Math.max((hi-lo)*.12,Math.abs(hi)*.01,1e-8);return[lo-margin,hi+margin];}
function drawSpectrum() {
  const s=displayed.spectrum,method=$('method').value,flux=s[method].map(v=>v===null?null:v/1e-16),[lo,hi]=extent(flux);
  const a=axes($('spectrum'),s.wave[0],s.wave.at(-1),lo,hi,'Observed air wavelength (Å)','Fλ (10⁻¹⁶ erg s⁻¹ cm⁻² Å⁻¹)');
  clipping(a,()=>{
    if(method==='optimal'){
      a.ctx.strokeStyle='#efd0ca';a.ctx.lineWidth=1;
      s.wave.forEach((v,i)=>{if(flux[i]===null||s.sigma[i]===null)return;const e=s.sigma[i]/1e-16;a.ctx.beginPath();a.ctx.moveTo(a.x(v),a.y(flux[i]-e));a.ctx.lineTo(a.x(v),a.y(flux[i]+e));a.ctx.stroke();});
    }
    line(a.ctx,a.x,a.y,s.wave,flux,'#df7976');
  });
  a.ctx.textAlign='center';a.ctx.fillStyle='#475748';a.ctx.font='14px Avenir, Arial';a.ctx.fillText(`Median SNR = ${displayed.snr.toFixed(1)} per pixel`,(a.box.l+a.box.r)/2,a.box.b-10);
  $('flux-note').textContent=method==='optimal'?'PypeIt · propagated ±1σ · observed air wavelength':'PypeIt boxcar · optimal uncertainty is not applied to boxcar flux';
}
let detectorAxes;
function drawDetector() {
  const [ny,nx]=displayed.window.shape,[oy,ox]=displayed.window.origin;
  const a=axes($('detector'),oy-.5,oy+ny-.5,ox-.5,ox+nx-.5,'Spectral detector pixel','Spatial detector pixel');detectorAxes=a;
  clipping(a,()=>{
    a.ctx.drawImage(raster,a.box.l,a.box.t,a.box.r-a.box.l,a.box.b-a.box.t);
    const fraction=recipe.sky.mode==='regions'?skyFraction:displayed.sky_fraction;
    if(fraction) fraction.forEach((f,i)=>{a.ctx.fillStyle=`rgba(80,151,187,${.24*f})`;a.ctx.fillRect(a.box.l,a.y(ox+i+.5),a.box.r-a.box.l,a.y(ox+i-.5)-a.y(ox+i+.5));});
    a.ctx.setLineDash([6,4]);line(a.ctx,a.x,a.y,displayed.trace.map((_,i)=>oy+i),displayed.trace,'#faf6d6',1.7);a.ctx.setLineDash([]);
    const objects=recipe.source_mode==='manual'?recipe.objects:[displayed.primary];
    objects.forEach((obj,i)=>{
      a.ctx.fillStyle=i===0?'rgba(223,121,118,.25)':'rgba(218,175,92,.25)';
      a.ctx.fillRect(a.box.l,a.y(obj.spat+obj.radius),a.box.r-a.box.l,a.y(obj.spat-obj.radius)-a.y(obj.spat+obj.radius));
      a.ctx.strokeStyle=i===0?'#e98e88':'#ecc67d';a.ctx.lineWidth=2;
      a.ctx.beginPath();a.ctx.arc(a.x(obj.spec),a.y(obj.spat),i===active?6:4,0,Math.PI*2);a.ctx.stroke();
      a.ctx.fillStyle='#fffdf5';a.ctx.textAlign='left';a.ctx.font='14px Avenir, Arial';a.ctx.fillText(obj.id,a.x(obj.spec)+10,a.y(obj.spat)-8);
    });
  });
}
function drawProfile() {
  const p=displayed.profiles[Number($('profile-bin').value)||0],scaled=p.flux.map(v=>v===null?null:v/1000),[lo,hi]=extent(scaled);
  const a=axes($('profile'),p.spatial[0],p.spatial.at(-1),lo,hi,'Spatial detector pixel','Summed electrons (10³)');
  clipping(a,()=>{
    const fraction=recipe.sky.mode==='regions'?skyFraction:displayed.sky_fraction;
    if(fraction) fraction.forEach((f,i)=>{a.ctx.fillStyle=`rgba(80,151,187,${.18*f})`;a.ctx.fillRect(a.x(p.spatial[i]-.5),a.box.t,a.x(p.spatial[i]+.5)-a.x(p.spatial[i]-.5),a.box.b-a.box.t);});
    const objects=recipe.source_mode==='manual'?recipe.objects:[displayed.primary];
    objects.forEach(obj=>{a.ctx.fillStyle='rgba(223,121,118,.20)';a.ctx.fillRect(a.x(obj.spat-obj.radius),a.box.t,a.x(obj.spat+obj.radius)-a.x(obj.spat-obj.radius),a.box.b-a.box.t);});
    line(a.ctx,a.x,a.y,p.spatial,scaled,'#244d3d',1.8);
  });
}
function drawAll(){if(!displayed||!raster?.complete)return;drawSpectrum();drawDetector();drawProfile();}
function detectorPoint(event) {
  const rect=$('detector').getBoundingClientRect(),{box}=detectorAxes;
  const x=(event.clientX-rect.left)/rect.width*1100,y=(event.clientY-rect.top)/rect.height*340;
  const [ny,nx]=original.window.shape,[oy,ox]=original.window.origin;
  return {inside:x>=box.l&&x<=box.r&&y>=box.t&&y<=box.b,
    spec:oy-.5+(x-box.l)/(box.r-box.l)*ny,spat:ox-.5+(box.b-y)/(box.b-box.t)*nx};
}
let start;
$('detector').onpointerdown=e=>{if(!original)return;start=detectorPoint(e);$('detector').setPointerCapture(e.pointerId);};
$('detector').onpointermove=e=>{if(!original)return;const p=detectorPoint(e);if(p.inside)$('coordinates').textContent=`Spectral pixel ${p.spec.toFixed(2)} · spatial pixel ${p.spat.toFixed(2)} · zero-based, after binning`;};
$('detector').onpointerup=e=>attempt(async()=>{
  if(!start?.inside)return;const end=detectorPoint(e);if(!end.inside)return;manual();
  if($('tool').value==='anchor'){recipe.objects[active].spec=end.spec;recipe.objects[active].spat=end.spat;}
  else{recipe.sky.mode='regions';const lo=Math.min(start.spat,end.spat),hi=Math.max(start.spat,end.spat);if(hi-lo<1)return;recipe.sky[$('tool').value].push([Math.round(lo*10)/10,Math.round(hi*10)/10]);}
  start=null;editor();await edited();
});
$('source-mode').onchange=()=>{if($('source-mode').value==='manual')manual();else{recipe.source_mode='automatic';recipe.objects=[];recipe.sky={mode:'automatic',include:[],exclude:[]};}editor();edited();};
$('sky-mode').onchange=()=>{if($('sky-mode').value==='regions')manual();recipe.sky={mode:$('sky-mode').value,include:[],exclude:[]};editor();edited();};
$('add-source').onclick=()=>{const first=recipe.objects[0],right=original.window.origin[1]+original.window.shape[1]-2-first.radius;recipe.objects.push({...first,id:'host',label:'Galaxy',kind:'galaxy',spat:Math.min(first.spat+Math.max(30,5*first.fwhm+1),right)});active=1;editor();edited();};
$('add-band').onclick=()=>{const x=original.window.origin[1];recipe.sky.include.push([x+5,x+25]);editor();edited();};
$('reset').onclick=()=>{recipe=copy(original.recipe);active=0;skyFraction=null;editor();edited();};
$('save-recipe').onclick=()=>attempt(async()=>{const checked=await api('/api/validate',{product:$('exposure').value,recipe});download(new Blob([JSON.stringify(checked.recipe,null,2)+'\n'],{type:'application/json'}),'extraction-recipe.json');status('Recipe saved. It can be replayed by the CLI or loaded here.');});
$('load-recipe').onclick=()=>$('recipe-file').click();
$('recipe-file').onchange=()=>attempt(async()=>{const file=$('recipe-file').files[0];if(!file)return;if(file.size>65536)throw new Error('Recipe exceeds 64 KiB');const candidate=JSON.parse(await file.text());const checked=await api('/api/validate',{product:$('exposure').value,recipe:candidate});recipe=checked.recipe;skyFraction=checked.sky_fraction;active=0;editor();drawAll();status('Saved recipe restored.');$('recipe-file').value='';});
function busy(value){$('extract').disabled=value;$('cancel').hidden=!value;$('exposure').disabled=value;}
async function poll(){
  const current=await api('/api/jobs');if(!current)return;job=current;$('log').textContent=current.log;
  if(current.status==='running'){status('PypeIt extraction is running. Original products remain unchanged.');return;}
  clearInterval(polling);polling=null;busy(false);
  if(current.status!=='complete'){status(`Extraction ${current.status}. See worker log; the original reduction is unchanged.`,current.status==='failed');return;}
  for(const product of current.products){const key=current.id+'/'+product;if(results.has(key))continue;results.set(key,{job:current.id,product});$('result').append(option(key,'Revision · '+product));}
  $('revision-path').textContent=current.directory;
  $('result').value=current.id+'/'+current.products[0];await showResult();
  status(current.report?.status==='incomplete'?'Extraction complete; report plots need attention (see worker log).':'Revision saved. Inspect the fitted trace, sky residuals and both extraction methods.');
}
$('extract').onclick=()=>attempt(async()=>{job=await api('/api/jobs',{product:$('exposure').value,recipe});busy(true);$('log').textContent='Starting PypeIt…';status('Extraction started. Saving a new revision.');polling=setInterval(()=>attempt(poll),1500);});
$('cancel').onclick=()=>attempt(async()=>{await api('/api/cancel');await poll();});
async function showResult(){
  const value=$('result').value;$('downloads').replaceChildren();
  if(value==='original'){$('revision-path').textContent='Displaying original reduction. Controls show the current draft recipe.';await show(original);return;}
  const selected=results.get(value);$('revision-path').textContent='Displaying '+selected.job+'. Controls show the current draft recipe.';await show(await api('/api/exposure?id='+encodeURIComponent(selected.product)+'&job='+selected.job));
  for(const [title,path,name] of [['FITS','products/'+selected.product,selected.product],['ASCII','products/'+selected.product.replace(/\.fits$/,'.asci'),selected.product.replace(/\.fits$/,'.asci')],['Recipe','recipe.json','extraction-recipe.json']]){
    $('downloads').append(button(title,()=>downloadFile('/api/file?job='+selected.job+'&path='+encodeURIComponent(path),name)));
  }
  $('downloads').append(button('Report ZIP',()=>downloadFile('/api/report?job='+selected.job,'efospec-report.zip')));
}
$('result').onchange=()=>attempt(showResult);$('exposure').onchange=()=>attempt(loadExposure);
$('method').onchange=drawAll;$('profile-bin').onchange=drawAll;
attempt(async()=>{const session=await api('/api/session');historyRecords=session.revisions;$('exposure').replaceChildren(...session.exposures.map(e=>option(e.id,`${e.object} · ${e.grism} · ${Math.round(e.exptime)} s`)));await loadExposure();const existing=await api('/api/jobs');if(existing){job=existing;if(existing.status==='running'){busy(true);polling=setInterval(()=>attempt(poll),1500);}else if(existing.status==='complete')await poll();}});
