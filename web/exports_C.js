/* Selected clips always use the editor renderer, including caption rasterization. */
window.CascadeExports={async initialize({project,userId,apiJSON,apiFetch,setStatus,stackOptions={}}) {
  const $=id=>document.getElementById(id), query=new URLSearchParams(location.search);
  const base='/api/projects/'+encodeURIComponent(project.id)+'/editor';
  const listing=await apiJSON(base), available=new Map();
  for(const wave of listing.sessions)for(const [i,clip]of wave.clips.entries()) {
    const entry={job_id:clip.job_id||wave.job_id,clip_index:clip.clip_index??i};
    available.set(entry.job_id+':'+entry.clip_index,{...entry,clip,wave,number:i+1});
  }
  let selected=window.CascadeExportSelection.read(userId,project.id);
  if(query.has('job')&&!query.has('selection'))selected=[{job_id:query.get('job'),clip_index:Number(query.get('clip')||0)}];
  const rows=selected.map(e=>available.get(e.job_id+':'+e.clip_index)).filter(Boolean);
  let chosen=new Set(rows.map(row=>row.job_id+':'+row.clip_index));
  const missing=selected.length-rows.length;
  if(!rows.length) { $('export-deck').textContent='No selected clips are available. Select clips in the editor sidebar first.';$('export-prev').disabled=$('export-next').disabled=true;setStatus('Choose clips in the editor to export.');return; }
  let active=0,working=false,ended=false,navigation;
  const deck=$('export-deck');
  const stackConfig={backCards:3,offset:42,rotation:3,scale:.95,...stackOptions};
  stackConfig.backCards=Math.max(0,Math.min(4,Number(stackConfig.backCards)||0));
  stackConfig.offset=Math.max(0,Math.min(56,Number(stackConfig.offset)||0));
  stackConfig.rotation=Math.max(0,Math.min(6,Number(stackConfig.rotation)||0));
  stackConfig.scale=Math.max(.8,Math.min(1,Number(stackConfig.scale)||.95));
  // The export selection is one collection, regardless of source save/session.
  const selectionGroup={rows,label:'Selected clips'};
  const waves=new Map([['selection',selectionGroup]]);
  for(const row of rows)row.group=selectionGroup;
  function expandWave(group,expanded){
    const wasExpanded=group.expanded;
    if(wasExpanded!==expanded&&group.cards){clearTimeout(group.spreadTimer);group.animating=!reducedMotion();group.cards.classList.toggle('is-spreading',group.animating);if(group.animating)group.spreadTimer=setTimeout(()=>finishSpread(group),660);}
    group.expanded=expanded;group.element.dataset.expanded=String(expanded);
    for(const control of [group.stack,group.toggle])control.setAttribute('aria-expanded',String(expanded));
    group.toggle.textContent=expanded?'Collapse clips ↑':'Expand clips ↓';
    group.gallery.inert=!expanded;group.gallery.setAttribute('aria-hidden',String(!expanded));
    group.stackWrap.inert=expanded;
    if(!expanded){group.rows.forEach(row=>row.video?.pause());if(group.cards)group.cards.scrollLeft=0;}
    else requestAnimationFrame(()=>{alignRail(group,group.rows.includes(rows[active])?group.rows.indexOf(rows[active]):0);if(!wasExpanded)group.element.scrollIntoView({block:'nearest',behavior:reducedMotion()?'instant':'smooth'});});
  }
  const reducedMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  function finishSpread(group){
    clearTimeout(group.spreadTimer);group.animating=false;
    group.element.classList.add('finish-spread');
    void group.cards.offsetWidth;
    group.cards.classList.remove('is-spreading');
    requestAnimationFrame(()=>group.element.classList.remove('finish-spread'));
    if(group.expanded)alignRail(group,group.current||0,'instant');
  }
  function cardLeft(group,index){
    const rail=group.cards,card=group.rows[index].card;
    return card.offsetLeft-(parseFloat(getComputedStyle(rail).paddingLeft)||0);
  }
  function nearestCard(group){
    let best=0,distance=Infinity;
    group.rows.forEach((row,index)=>{const d=Math.abs(cardLeft(group,index)-group.cards.scrollLeft);if(d<distance){best=index;distance=d;}});
    return best;
  }
  function railReadout(group,index){
    group.current=index;group.previous.disabled=index===0;group.next.disabled=index===group.rows.length-1;
    group.position.textContent=(index+1)+' of '+group.rows.length;
  }
  function alignRail(group,index,behavior=reducedMotion()?'instant':'smooth'){
    railReadout(group,index);group.railTarget=index;group.railTargetUntil=performance.now()+1500;
    group.cards.scrollTo({left:cardLeft(group,index),behavior});
  }
  function settleRail(group){
    if(!group.expanded||group.drag||group.animating)return;
    const index=nearestCard(group);if(group.railTarget!==undefined&&index!==group.railTarget&&performance.now()<group.railTargetUntil)return;group.railTarget=undefined;railReadout(group,index);
    if(rows[active]!==group.rows[index])show(rows.indexOf(group.rows[index]),{expand:false,rail:false});
  }
  function wireRail(group){
    const rail=group.cards;
    for(const name of ['wheel','touchstart','pointerdown'])rail.addEventListener(name,()=>{group.railTarget=undefined;if(group.animating)finishSpread(group);},{passive:true});
    group.previous.onclick=()=>show(rows.indexOf(group.rows[Math.max(0,(group.current||0)-1)]));
    group.next.onclick=()=>show(rows.indexOf(group.rows[Math.min(group.rows.length-1,(group.current||0)+1)]));
    rail.addEventListener('scroll',()=>{clearTimeout(group.scrollTimer);group.scrollTimer=setTimeout(()=>settleRail(group),160);},{passive:true});
    rail.addEventListener('scrollend',()=>settleRail(group));
    rail.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)||event.target.closest('video,input,button'))return;
      event.preventDefault();event.stopPropagation();
      const index=event.key==='Home'?0:event.key==='End'?group.rows.length-1:Math.max(0,Math.min(group.rows.length-1,(group.current||0)+(event.key==='ArrowRight'?1:-1)));
      show(rows.indexOf(group.rows[index]));
    });
    rail.addEventListener('pointerdown',event=>{
      group.suppressClickUntil=0;
      if(event.pointerType!=='mouse'||event.button!==0||event.target.closest('button,input,label,a'))return;
      const player=event.target.closest('video');if(player?.controls&&event.clientY>player.getBoundingClientRect().bottom-64)return;
      group.drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:rail.scrollLeft,moved:false};
    });
    rail.addEventListener('pointermove',event=>{
      const drag=group.drag;if(!drag)return;
      const dx=event.clientX-drag.x;
      if(!drag.moved&&Math.abs(dx)>6&&Math.abs(dx)>Math.abs(event.clientY-drag.y)){
        drag.moved=true;rail.classList.add('is-dragging');rail.setPointerCapture(drag.id);
      }
      if(drag.moved){event.preventDefault();rail.scrollLeft=drag.left-dx;}
    });
    const finish=()=>{
      const drag=group.drag;if(!drag)return;group.drag=null;rail.classList.remove('is-dragging');
      if(drag.moved){group.suppressClickUntil=performance.now()+250;const index=nearestCard(group);show(rows.indexOf(group.rows[index]));}
    };
    for(const name of ['pointerup','pointercancel','lostpointercapture'])rail.addEventListener(name,finish);
    rail.addEventListener('click',event=>{if(event.detail>0&&performance.now()<(group.suppressClickUntil||0)){group.suppressClickUntil=0;event.preventDefault();event.stopPropagation();}},true);
    rail.addEventListener('dragstart',event=>event.preventDefault());
    railReadout(group,0);
  }
  function applyPoster(row,blob,{edited=false}={}){
    if(ended||row.coverURL||(!edited&&row.editedPoster))return;
    const previous=row.posterURL;
    row.posterURL=URL.createObjectURL(blob);row.video.poster=row.posterURL;
    row.editedPoster=edited;row.thumbnailRetry.hidden=true;
    for(const image of row.stackImages){
      image.onload=()=>{image.parentElement.classList.add('ready');image.parentElement.classList.remove('unavailable');};
      image.onerror=()=>{image.parentElement.classList.add('unavailable');row.thumbnailRetry.hidden=false;};
      image.src=row.posterURL;
    }
    if(previous)URL.revokeObjectURL(previous);
  }
  async function loadThumbnail(row){
    row.thumbnailRetry.hidden=true;
    try{
      const response=await apiFetch(url(row)+'/thumbnail');
      applyPoster(row,await response.blob());
    }catch(error){
      if(!ended&&!row.posterURL){
        row.thumbnailRetry.hidden=false;
        row.thumbnailRetry.title=error.message;
        for(const image of row.stackImages)image.parentElement.classList.add('unavailable');
      }
    }
  }
  async function makePoster(row){
    if(row.posterTask)return row.posterTask;
    row.posterTask=(async()=>{
      const decoder=document.createElement('video');decoder.muted=true;decoder.playsInline=true;decoder.preload='auto';
      const wait=event=>new Promise((resolve,reject)=>{
        const timeout=setTimeout(()=>{cleanup();reject(Error('Thumbnail decoding timed out.'));},15000);
        const cleanup=()=>{clearTimeout(timeout);decoder.removeEventListener(event,done);decoder.removeEventListener('error',failed);};
        const done=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(Error('Thumbnail unavailable.'));};
        decoder.addEventListener(event,done,{once:true});decoder.addEventListener('error',failed,{once:true});
      });
      try{
        const ready=wait('loadeddata');decoder.src=row.objectURL;await ready;if(ended)return;
        const post=await postPreparation.record(row);const sought=wait('seeked');decoder.currentTime=Math.max(.001,Math.min(post.data.cover_time??Math.min(1,decoder.duration/2),decoder.duration-.01));await sought;if(ended)return;
        const canvas=document.createElement('canvas');const ratio=decoder.videoWidth/decoder.videoHeight;canvas.width=Math.round(Math.min(720,400*ratio));canvas.height=Math.round(canvas.width/ratio);
        const ctx=canvas.getContext('2d'),scale=Math.max(canvas.width/decoder.videoWidth,canvas.height/decoder.videoHeight);
        ctx.drawImage(decoder,(canvas.width-decoder.videoWidth*scale)/2,(canvas.height-decoder.videoHeight*scale)/2,decoder.videoWidth*scale,decoder.videoHeight*scale);
        const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.88));if(!blob||ended)return;
        applyPoster(row,blob,{edited:true});
      }finally{decoder.removeAttribute('src');decoder.load();}
    })().catch(()=>{row.posterTask=null;if(!row.posterURL)row.thumbnailRetry.hidden=false;});
    return row.posterTask;
  }
  for(const [index,group]of [...waves.values()].entries()){
    const section=document.createElement('section');section.className='wave-album';group.element=section;
    const heading=document.createElement('div');heading.className='wave-album-heading';
    const identity=document.createElement('div'),title=document.createElement('h3');title.textContent=group.label;title.hidden=true;
    const count=document.createElement('p');count.className='wave-item-count';
    const icon=document.createElement('span');icon.className='album-grid-icon';icon.setAttribute('aria-hidden','true');for(let i=0;i<4;i++)icon.append(document.createElement('i'));
    count.append(icon,document.createTextNode(group.rows.length+' '+(group.rows.length===1?'clip':'clips')));identity.append(title,count);
    const toggle=document.createElement('button');toggle.type='button';toggle.className='wave-toggle';group.toggle=toggle;
    const galleryId='wave-gallery-'+index;toggle.setAttribute('aria-controls',galleryId);toggle.onclick=()=>{if(group.expanded)expandWave(group,false);else show(rows.indexOf(group.rows.includes(rows[active])?rows[active]:group.rows[0]));};heading.append(identity,toggle);
    const stackWrap=document.createElement('div');stackWrap.className='wave-stack-wrap';group.stackWrap=stackWrap;
    const stackInner=document.createElement('div');stackInner.className='wave-stack-inner';stackWrap.append(stackInner);
    const stack=document.createElement('button');stack.type='button';stack.className='wave-stack';group.stack=stack;
    stack.setAttribute('aria-controls',galleryId);stack.setAttribute('aria-label','Expand '+group.label+' to browse '+group.rows.length+' clips');
    const pile=document.createElement('span');pile.className='stack-pile';
    group.rows.slice(0,1+stackConfig.backCards).forEach((row,depth)=>{
      row.stackImages=[];const layer=document.createElement('span');layer.className='stack-layer';layer.dataset.depth=depth;
      const side=depth%2?-1:1,offset=depth<3?stackConfig.offset:stackConfig.offset*.45;
      layer.style.setProperty('--card-x',(depth?side*offset:0)+'px');layer.style.setProperty('--card-y',(depth*13)+'px');
      layer.style.setProperty('--card-rotation',(depth?side*stackConfig.rotation:0)+'deg');layer.style.setProperty('--card-scale',String(stackConfig.scale**depth));
      layer.style.setProperty('--card-opacity',String(1-depth*.11));layer.style.zIndex=String(10-depth);
      const image=document.createElement('img');image.alt='';image.draggable=false;
      const loading=document.createElement('span');loading.className='stack-placeholder';loading.textContent='Clip '+row.number;
      layer.append(image,loading);pile.append(layer);row.stackImages.push(image);
    });
    for(const row of group.rows)row.stackImages=row.stackImages||[];
    const hint=document.createElement('span');hint.className='stack-open-hint';hint.textContent='Open '+group.rows.length+' '+(group.rows.length===1?'clip':'clips')+' →';
    stack.append(pile,hint);stack.onclick=()=>{expandWave(group,true);group.toggle.focus({preventScroll:true});const selectedRow=group.rows.includes(rows[active])?rows[active]:group.rows[0];show(rows.indexOf(selectedRow));};stackInner.append(stack);
    const gallery=document.createElement('div');gallery.id=galleryId;gallery.className='wave-gallery';group.gallery=gallery;
    const body=document.createElement('div');body.className='wave-gallery-body';gallery.append(body);
    const railHeader=document.createElement('div');railHeader.className='wave-rail-toolbar';
    const railHint=document.createElement('p');railHint.textContent='Scroll, swipe, or drag to browse';
    const controls=document.createElement('div');controls.className='wave-rail-controls';
    group.previous=document.createElement('button');group.previous.type='button';group.previous.className='wave-rail-prev';group.previous.textContent='←';group.previous.setAttribute('aria-label','Previous clip in '+group.label);
    group.next=document.createElement('button');group.next.type='button';group.next.className='wave-rail-next';group.next.textContent='→';group.next.setAttribute('aria-label','Next clip in '+group.label);
    group.position=document.createElement('span');group.position.className='wave-rail-position';group.position.setAttribute('aria-live','polite');
    controls.append(group.previous,group.position,group.next);railHeader.append(railHint,controls);body.append(railHeader);
    const cards=document.createElement('div');cards.className='wave-clips';cards.tabIndex=0;cards.setAttribute('role','region');cards.setAttribute('aria-label',group.label+' clips. Scroll horizontally or use arrow keys.');group.cards=cards;body.append(cards);
    const footer=document.createElement('div');footer.className='wave-downloads';
    group.download=document.createElement('button');group.download.type='button';group.download.className='wave-download';
    group.download.textContent=group.rows.length===1?'Download clip':'Download clips ('+group.rows.length+')';
    group.download.onclick=()=>group.rows.length===1?downloadRow(group.rows[0]):downloadSet(group.rows);
    footer.append(group.download);body.append(footer);section.append(heading,stackWrap,gallery);deck.append(section);
    section.addEventListener('keydown',event=>{if(event.key==='Escape'&&group.expanded){event.preventDefault();expandWave(group,false);group.toggle.focus();}});
    expandWave(group,false);
  }
  function progress(message){$('export-progress').textContent=message;}
  function lock(value){working=value;$('download-active').disabled=value||!rows[active].blob||ended;$('export-all').disabled=value||ended||!chosen.size;document.querySelectorAll('#exports-tree input,.export-card-check,.export-card-download,.wave-download').forEach(e=>e.disabled=value||ended);}
  function url(row){return base+'/'+row.job_id+'/'+row.clip_index;}
  async function payload(row) {
    if(row.payload)return row.payload;
    const info=await apiJSON(url(row));let draft=info.draft;
    try{const local=JSON.parse(localStorage.getItem('cascade-editor:v1:'+userId+':'+project.id+':'+row.job_id+':'+row.clip_index));if(local?.updated_at>draft.updated_at)draft=local;}catch{}
    const state=window.CascadeEditorState.normalize(draft.state,info.duration);
    await window.CascadeAutoFrame.prepare(state,{info,url:url(row),apiJSON,status:message=>{row.status.textContent=message;if(row===rows[active])progress(message);},verify:()=>{if(ended)throw Error('Session ended.');}});
    if(state.reframe.enabled){const motion=await apiJSON(url(row)+'/reframe/'+state.reframe.analysis_id+'/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({composition:state.composition,focus:state.reframe.focus,selection:state.reframe.selection})});row.warning=motion.warning;}
    await document.fonts.ready;
    const g=window.CascadeEditorState.compositionGeometry(info.width,info.height,state.composition);
    row.video.style.aspectRatio=g.width+'/'+g.height;
    row.payload={...state,overlays:window.CascadeCaptions.exportFrames(info.cues,state,g.width,g.height)};
    return row.payload;
  }
  async function render(row) {
    if(row.blob)return row.blob;
    if(row.rendering)return row.rendering;
    row.retry.hidden=true;
    row.status.textContent='Rendering edited preview…';
    row.rendering=(async()=>{
      const body=await payload(row);
      const response=await apiFetch(url(row)+'/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const blob=await response.blob();if(ended)throw Error('Session ended.');
      row.blob=blob;row.objectURL=URL.createObjectURL(blob);row.video.src=row.objectURL;row.video.load();makePoster(row);row.retry.hidden=true;row.status.textContent=row.warning||'';
      return blob;
    })().catch(error=>{row.retry.hidden=false;row.status.textContent='Preview failed: '+error.message;throw error;}).finally(()=>{row.rendering=null;});
    return row.rendering;
  }
  function download(blob,name){if(ended)throw Error('Session ended.');const link=document.createElement('a'),objectURL=URL.createObjectURL(blob);link.href=objectURL;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(objectURL),30000);}
  function filename(row){return 'cascade-session-'+(row.wave.session_number||1)+'-wave-'+(row.wave.wave_number||1)+'-clip-'+row.number+'.mp4';}
  async function show(index,{expand=true,scroll=false,rail=true,syncPost=true}={}) {
    if(ended)return;
    rows[active].video.pause(); active=Math.max(0,Math.min(rows.length-1,index));
    rows.forEach((row,i)=>{
      row.card.dataset.active=String(i===active);row.video.controls=i===active;row.video.tabIndex=i===active?0:-1;
      if(i!==active)row.video.pause();
    });
    const row=rows[active];if(syncPost&&postPreparation.openToken&&postPreparation.current?.row!==row)postPreparation.open(row,row.prepare,{scroll:false});railReadout(row.group,row.group.rows.indexOf(row));if(expand)expandWave(row.group,true);
    if(rail&&row.group.expanded)requestAnimationFrame(()=>alignRail(row.group,row.group.rows.indexOf(row)));
    if(scroll)requestAnimationFrame(()=>row.group.element.scrollIntoView({block:'nearest',behavior:reducedMotion()?'instant':'smooth'}));
    navigation?.active(row.job_id+':'+row.clip_index);$('export-position').textContent=(active+1)+' of '+rows.length;
    $('export-prev').disabled=active===0;$('export-next').disabled=active===rows.length-1;
    document.querySelector('.exports-footer a').href='editor_C.html?project='+encodeURIComponent(project.id);
    document.querySelector('.exports-footer a').textContent='← Back to editor';lock(working);
    progress(row.blob?'':'Rendering edited preview…');
    try{await render(row);if(row===rows[active]){progress(missing?missing+' unavailable selection(s) omitted.':'');lock(working);}}
    catch(error){if(row===rows[active])progress(error.message+' Use Download to retry.');}
    // Background cards are real edited videos too. Render only immediate neighbours.
    for(const neighbour of [rows[active-1],rows[active+1]].filter(Boolean))render(neighbour).catch(()=>{});
    if(row===rows[active]&&!working&&!ended)$('download-active').disabled=false;
  }
  const postPreparation=new window.CascadePostPreparation({apiJSON,url,render,payload,filename,download:row=>downloadRow(row,{throwOnError:true}),userId,projectId:project.id});
  rows.forEach((row,i)=>{
    row.card=document.createElement('article');row.card.style.setProperty('--rail-index',row.group.rows.indexOf(row));row.card.style.setProperty('--rail-delay',Math.min(6,row.group.rows.indexOf(row))*25+'ms');row.card.className='export-media-card';row.card.setAttribute('aria-label','Selected clip '+(i+1));
    row.video=document.createElement('video');row.video.playsInline=true;row.video.preload='auto';row.video.setAttribute('aria-label',row.clip.title||'Clip '+row.number);
    row.video.addEventListener('loadedmetadata',()=>{if(Number.isFinite(row.video.duration)&&row.video.duration>0)row.video.currentTime=Math.min(.04,row.video.duration/2);});
    row.video.addEventListener('play',()=>{if(ended)row.video.pause();else{if(rows[active]!==row)show(i);rows.forEach(other=>{if(other!==row)other.video.pause();});}});
    const header=document.createElement('div');header.className='export-card-header';
    const label=document.createElement('label');row.check=document.createElement('input');row.check.type='checkbox';row.check.className='export-card-check';row.check.checked=true;row.check.setAttribute('aria-label','Select Clip '+row.number+' for download');row.check.onchange=()=>navigation.change([row.job_id+':'+row.clip_index],row.check.checked);
    label.append(row.check,document.createTextNode('Clip '+row.number));
    const open=document.createElement('button');open.type='button';open.textContent='Preview';open.onclick=()=>show(i);header.append(label,open);
    const meta=document.createElement('p');meta.className='export-card-meta';meta.textContent='';meta.hidden=true;
    const single=document.createElement('button');single.type='button';single.className='export-card-download';single.textContent='Download clip';single.onclick=()=>downloadRow(row);
    row.retry=document.createElement('button');row.retry.type='button';row.retry.className='export-preview-retry';row.retry.textContent='Retry preview';row.retry.hidden=true;row.retry.onclick=()=>show(i);
    row.status=document.createElement('p');row.status.className='card-render-status';row.status.textContent='Edited preview';
    row.thumbnailRetry=document.createElement('button');row.thumbnailRetry.type='button';row.thumbnailRetry.className='export-thumbnail-retry';row.thumbnailRetry.textContent='Thumbnail unavailable · Retry';row.thumbnailRetry.hidden=true;row.thumbnailRetry.onclick=()=>loadThumbnail(row);
    const prepare=document.createElement('button');row.prepare=prepare;prepare.type='button';prepare.className='prepare-post';prepare.textContent='Prepare post';prepare.setAttribute('aria-controls','prepare-post-section');prepare.setAttribute('aria-expanded','false');prepare.onclick=event=>{event.stopPropagation();show(i,{syncPost:false});postPreparation.open(row,prepare);};
    const delivery=document.createElement('div');delivery.className='export-card-delivery';delivery.append(single,prepare);
    row.card.append(header,row.video,meta,row.status,row.thumbnailRetry,row.retry,delivery);row.group.cards.append(row.card);
  });
  for(const group of waves.values()){
    wireRail(group);
    const layout=()=>{const gap=parseFloat(getComputedStyle(group.cards).columnGap)||20;group.rows.forEach((row,index)=>row.card.style.setProperty('--fold-x',-index*(row.card.offsetWidth+gap)+'px'));if(group.expanded&&!group.drag)alignRail(group,group.current||0,'instant');};
    group.observer=new ResizeObserver(layout);group.observer.observe(group.cards);layout();
  }
  navigation=new window.CascadeClipNavigation({container:$('exports-tree'),selectable:true,selected:[...chosen],onSelection:keys=>{chosen=new Set(keys);for(const row of rows){const checked=chosen.has(row.job_id+':'+row.clip_index);row.check.checked=checked;row.card.classList.toggle('selected',checked);}$('export-all').textContent='Download selected clips ('+chosen.size+')';lock(working);},items:rows.map(row=>({...row,key:row.job_id+':'+row.clip_index,label:'Session '+row.wave.session_number+' Wave '+row.wave.wave_number+' Clip '+row.number})),onOpen:item=>show(rows.findIndex(row=>row.job_id===item.job_id&&row.clip_index===item.clip_index),{scroll:true})});
  $('export-prev').onclick=()=>show(active-1);$('export-next').onclick=()=>show(active+1);
  document.addEventListener('keydown',event=>{if(event.target.closest('input,textarea,select')||event.altKey||event.ctrlKey||event.metaKey)return;if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();show(active+(event.key==='ArrowRight'?1:-1));}});
  async function downloadRow(row,{throwOnError=false}={}){if(working||ended){if(throwOnError)throw Error(ended?'Session ended. Sign in again.':'Another download is in progress. Try again when it finishes.');return;}lock(true);progress('Preparing Clip '+row.number+'…');try{download(await render(row),filename(row));progress('Clip '+row.number+' downloaded.');}catch(error){progress('Download failed: '+error.message+' Click Download clip to retry.');if(throwOnError)throw error;}finally{lock(false);}}
  $('download-active').onclick=()=>downloadRow(rows[active]);
  $('export-all').textContent='Download selected clips ('+chosen.size+')';
  rows.forEach(row=>row.card.classList.add('selected'));
  async function downloadSet(downloadRows){
    if(working||ended||!downloadRows.length)return;lock(true);
    try {
      if(downloadRows.length>100)throw Error('Select at most 100 clips per ZIP.');
      const clips=[];
      for(const [i,row]of downloadRows.entries()){progress('Preparing '+(i+1)+' of '+downloadRows.length+'…');clips.push({job_id:row.job_id,clip_index:row.clip_index,edit:await payload(row)});}
      progress('Rendering '+downloadRows.length+' edited clips and building ZIP…');
      const response=await apiFetch(base+'/export-selected',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clips})});
      download(await response.blob(),'cascade-clips.zip');progress('All '+downloadRows.length+' edited clips are ready in your ZIP.');
    }catch(error){progress('Download failed: '+error.message+' Use the download action to retry.');}finally{lock(false);}
  }
  $('export-all').onclick=()=>downloadSet(rows.filter(row=>chosen.has(row.job_id+':'+row.clip_index)));

  function cleanup(){ended=true;postPreparation.destroy();for(const group of waves.values()){clearTimeout(group.scrollTimer);clearTimeout(group.spreadTimer);group.observer.disconnect();}rows.forEach(row=>{row.video.pause();row.video.removeAttribute('src');row.video.load();if(row.objectURL)URL.revokeObjectURL(row.objectURL);if(row.posterURL)URL.revokeObjectURL(row.posterURL);});lock(true);}
  window.addEventListener('cascade:session-ended',cleanup);
  window.addEventListener('cascade:session-restored',()=>location.reload());
  window.addEventListener('pagehide',cleanup,{once:true});
  // Posters must not wait for edited exports, tracking, captions, or other clips.
  let thumbnailIndex=0;
  for(let worker=0;worker<Math.min(4,rows.length);worker++)(async()=>{
    while(!ended&&thumbnailIndex<rows.length)await loadThumbnail(rows[thumbnailIndex++]);
  })();
  setStatus('');await show(0,{expand:false});
  (async()=>{for(const row of rows){if(ended)return;await render(row).catch(()=>{});}})();
}};
