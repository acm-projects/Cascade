/* Editor-only timeline. All coordinates are generated-media seconds. */
window.CascadeTimeline = class {
  constructor({onSeek, onBeginTrim, onTrim, onEndTrim, onCue, onBroll, onDropBroll, onBeginBroll, onMoveBroll, onEndBroll}) {
    this.onSeek=onSeek; this.onBeginTrim=onBeginTrim; this.onTrim=onTrim; this.onEndTrim=onEndTrim; this.onCue=onCue; this.onBroll=onBroll;
    Object.assign(this,{onDropBroll,onBeginBroll,onMoveBroll,onEndBroll});
    this.view=document.getElementById('timeline-scroll'); this.content=document.getElementById('timeline-content');
    this.ruler=document.getElementById('timeline-ruler'); this.strip=document.getElementById('thumbnail-strip');
    this.captions=document.getElementById('timeline-captions'); this.playhead=document.getElementById('timeline-playhead');
    this.handles=[document.getElementById('handle-start'),document.getElementById('handle-end')];
    this.root=document.getElementById('timeline-controls');this.expanded=false;
    document.getElementById('timeline-toggle').onclick=()=>this.setExpanded(!this.expanded);
    this.setExpanded(false);
    this.dropMarker=document.createElement('div');this.dropMarker.className='broll-drop-marker';this.dropMarker.hidden=true;this.content.append(this.dropMarker);
    this.root.addEventListener('dragover',e=>this.dragOver(e));
    this.root.addEventListener('dragleave',e=>{if(!this.root.contains(e.relatedTarget))this.clearDrop();});
    this.root.addEventListener('drop',e=>this.drop(e));
    document.addEventListener('dragend',()=>this.clearDrop());
    this.zoom=1; this.duration=0; this.cues=[]; this.frames=[]; this.token=0; this.disabled=true;
    this.content.addEventListener('pointerdown',event=>this.begin(event));
    this.content.addEventListener('pointermove',event=>{ if(this.drag) { this.drag.x=event.clientX; this.move(); } });
    for(const name of ['pointerup','pointercancel','lostpointercapture']) this.content.addEventListener(name,()=>this.end());
    this.playhead.addEventListener('keydown',event=>this.keySeek(event));
    this.handles.forEach((handle,index)=>{
      handle.addEventListener('keydown',event=>{
        if(this.disabled || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault(); if(!this.keyboardTrim) { this.keyboardTrim=true; this.onBeginTrim(); }
        const name=index?'end':'start', value=event.key==='Home'?0:event.key==='End'?this.duration:this.state[name]+(event.key==='ArrowRight'?1:-1)*(event.shiftKey?1:.05);
        this.onTrim(name,value);
      });
      for(const name of ['keyup','blur']) handle.addEventListener(name,()=>{ if(this.keyboardTrim) { this.keyboardTrim=false; this.onEndTrim(); } });
    });
    document.getElementById('timeline-zoom').addEventListener('input',event=>this.setZoom(Number(event.target.value)));
    document.getElementById('zoom-in').onclick=()=>this.setZoom(this.zoom+.5);
    document.getElementById('zoom-out').onclick=()=>this.setZoom(this.zoom-.5);
    document.getElementById('zoom-fit').onclick=()=>{this.flushZoom();this.setZoom(1);this.view.scrollLeft=0;};
    // Chromium exposes trackpad pinch as Ctrl+wheel; ordinary wheel stays native.
    this.view.addEventListener('wheel',event=>{
      this.interactingUntil=performance.now()+700;
      if(!event.ctrlKey || !this.duration)return;
      event.preventDefault();
      if(this.gestureZoom)return;
      const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?this.view.clientHeight:1);
      this.queueZoom((this.pendingZoom?.value??this.zoom)*Math.exp(-delta*.01),event.clientX);
    },{passive:false});
    // Safari trackpads expose cumulative gesture scale instead.
    this.view.addEventListener('gesturestart',event=>{if(!this.duration)return;event.preventDefault();this.flushZoom();this.gestureZoom=this.zoom;});
    this.view.addEventListener('gesturechange',event=>{if(!this.gestureZoom)return;event.preventDefault();this.queueZoom(this.gestureZoom*event.scale,event.clientX);});
    this.view.addEventListener('gestureend',event=>{if(!this.gestureZoom)return;event.preventDefault();this.flushZoom();this.gestureZoom=null;});
    this.observer=new ResizeObserver(()=>this.layout()); this.observer.observe(this.view);
  }
  setDisabled(value) { this.disabled=value; this.content.setAttribute('aria-disabled',String(value)); this.handles.forEach(h=>h.setAttribute('aria-disabled',String(value))); }
  queueZoom(value,clientX) {
    this.pendingZoom={value:Math.max(1,Math.min(12,value)),clientX};
    this.interactingUntil=performance.now()+700;
    if(!this.zoomFrame)this.zoomFrame=requestAnimationFrame(()=>this.flushZoom());
  }
  flushZoom() {
    cancelAnimationFrame(this.zoomFrame);this.zoomFrame=null;
    const pending=this.pendingZoom;this.pendingZoom=null;
    if(pending)this.setZoom(pending.value,pending.clientX);
  }
  setZoom(value,clientX) {
    const bounds=this.view.getBoundingClientRect();
    const cursor=Number.isFinite(clientX)?clientX:bounds.left+this.view.clientWidth/2;
    const anchor=(cursor-this.content.getBoundingClientRect().left)/(this.pps||1);
    this.zoom=Math.max(1,Math.min(12,value)); this.layout();
    this.view.scrollLeft+=this.content.getBoundingClientRect().left+anchor*this.pps-cursor;
  }
  layout() {
    if(!this.duration) return;
    const width=Math.max(240,this.view.clientWidth-24)*this.zoom;
    this.pps=width/this.duration; this.content.style.width=width+'px';
    document.getElementById('timeline-zoom').value=this.zoom;
    document.getElementById('zoom-label').textContent=Math.round(this.zoom*100)+'%';
    this.ruler.replaceChildren();
    const step=[.1,.25,.5,1,2,5,10,15,30,60,120,300,600,1800,3600].find(n=>n*this.pps>=72)||3600;
    const times=[];
    for(let t=0;t<this.duration;t+=step) if(t===0 || (this.duration-t)*this.pps>=105) times.push(t);
    times.push(this.duration);
    for(const t of times) {
      const tick=document.createElement('span'); tick.className='ruler-tick'; tick.style.left=t*this.pps+'px';
      const label=document.createElement('span'); label.textContent=window.CascadeEditorState.formatTime(t); tick.append(label);
      if(t===this.duration) tick.classList.add('at-end');
      this.ruler.append(tick);
    }
    this.renderFrames(); this.renderCues(); if(this.state) this.update(this.state,this.time||0);
  }
  update(state,time,playing=false) {
    this.state=state; this.time=time;
    this.content.style.setProperty('--trim-start',state.start*this.pps+'px');
    this.content.style.setProperty('--trim-end',state.end*this.pps+'px');
    this.content.style.setProperty('--playhead',time*this.pps+'px');
    if(playing && !this.drag && performance.now()>(this.interactingUntil||0)) { const x=time*this.pps; if(x<this.view.scrollLeft+12 || x>this.view.scrollLeft+this.view.clientWidth-36) this.view.scrollLeft=Math.max(0,x-this.view.clientWidth*.25); }
    this.playhead.setAttribute('aria-valuenow',time.toFixed(2)); this.playhead.setAttribute('aria-valuemax',this.duration);
    this.handles.forEach((h,i)=>{ const name=i?'end':'start'; h.setAttribute('aria-valuenow',state[name].toFixed(2)); h.setAttribute('aria-valuemin',i?state.start+.05:0); h.setAttribute('aria-valuemax',i?this.duration:state.end-.05); h.setAttribute('aria-valuetext',window.CascadeEditorState.formatTime(state[name])); });
    if(this.texts!==JSON.stringify(state.texts||{}) || this.captionEnabled!==state.captions.enabled) {
      this.texts=JSON.stringify(state.texts||{}); this.captionEnabled=state.captions.enabled; this.renderCues();
    }
    const stockSignature=JSON.stringify([state.broll,this.pps,state.start,state.end]);
    if(stockSignature!==this.stockSignature) {
      this.stockSignature=stockSignature;const track=document.getElementById('timeline-broll');track.replaceChildren();
      for(const s of state.broll||[]) {
        const button=document.createElement('button');button.type='button';button.className='broll-track-segment';button.dataset.broll=s.id;
        button.style.left=s.start*this.pps+'px';button.style.width=Math.max(2,s.duration*this.pps)+'px';
        const name=document.createElement('span');name.textContent=s.asset.creator;button.append(name);
        for(const edge of ['start','end']){const grip=document.createElement('span');grip.className='broll-edge broll-edge-'+edge;grip.dataset.brollEdge=edge;grip.textContent='⋮';grip.setAttribute('aria-hidden','true');button.append(grip);}
        button.setAttribute('aria-label',`B-roll by ${s.asset.creator}. Use the B-roll panel for precise timing.`);button.title=`B-roll ${s.start.toFixed(2)}–${(s.start+s.duration).toFixed(2)} seconds · ${s.asset.creator}`;
        button.classList.toggle('outside-trim',s.start+s.duration<=state.start||s.start>=state.end);
        button.onclick=e=>{if(e.detail===0&&!this.disabled)this.onBroll?.(s.id);};track.append(button);
      }
    }
    this.captions.classList.toggle('captions-muted',!state.captions.enabled);
    for(const el of this.captions.children) el.classList.toggle('outside-trim',Number(el.dataset.end)<=state.start || Number(el.dataset.start)>=state.end);
  }
  renderCues() {
    this.captions.replaceChildren();
    this.cues.forEach((cue,index)=>{
      const start=Math.max(0,cue.start), end=Math.min(this.duration,cue.end); if(end<=start) return;
      const segment=document.createElement('button'); segment.type='button'; segment.className='caption-segment';
      segment.style.left=start*this.pps+'px'; segment.style.width=Math.max(2,(end-start)*this.pps)+'px';
      segment.dataset.start=start; segment.dataset.end=end; segment.dataset.cue=index;
      const text=this.state?.texts?.[index]??cue.text;
      segment.textContent=text||'(empty caption)'; segment.title=window.CascadeEditorState.formatTime(start)+' – '+window.CascadeEditorState.formatTime(end)+' · '+text;
      segment.setAttribute('aria-label',segment.title);
      segment.onclick=event=>{ if(event.detail===0 && !this.disabled) { this.onCue(index); this.onSeek(start+.001); } };
      this.captions.append(segment);
    });
    document.getElementById('timeline-caption-empty').hidden=this.cues.length>0;
  }
  renderFrames() {
    this.strip.replaceChildren(); if(!this.frames.length || !this.pps) return;
    const width=this.duration*this.pps, count=Math.ceil(width/92);
    for(let i=0;i<count;i++) {
      const img=document.createElement('img'); img.alt=''; img.draggable=false;
      const t=(i+.5)/count*this.duration;
      const frame=this.frames.reduce((best,f)=>Math.abs(f.time-t)<Math.abs(best.time-t)?f:best,this.frames[0]);
      img.src=frame.url; img.style.width=width/count+'px'; img.dataset.time=frame.time;
      this.strip.append(img);
    }
  }
  position(clientX) { return Math.max(0,Math.min(this.duration,(clientX-this.content.getBoundingClientRect().left)/this.pps)); }
  begin(event) {
    if(this.disabled || event.button!==0 || !this.duration) return;
    event.preventDefault();
    const stock=event.target.closest('[data-broll]');
    if(stock){
      const segment=this.state.broll.find(s=>s.id===stock.dataset.broll);if(!segment)return;
      this.onBroll?.(segment.id);this.onSeek(Math.max(this.state.start,segment.start)+.001);
      this.onBeginBroll?.();this.drag={kind:'broll',id:segment.id,original:{...segment},edge:event.target.closest('[data-broll-edge]')?.dataset.brollEdge,originX:event.clientX,x:event.clientX};
      this.content.setPointerCapture(event.pointerId);return;
    }
    const handle=event.target.closest('[data-trim]'), cue=event.target.closest('[data-cue]');
    this.drag={kind:handle?.dataset.trim||'seek',x:event.clientX};
    if(handle) this.onBeginTrim(); else if(cue) this.onCue(Number(cue.dataset.cue));
    this.content.setPointerCapture(event.pointerId); this.move();
    const autoScroll=()=>{
      if(!this.drag) return;
      const rect=this.view.getBoundingClientRect(), delta=this.drag.x<rect.left+24?-12:this.drag.x>rect.right-24?12:0;
      if(delta) { this.view.scrollLeft+=delta; this.move(); }
      this.scrollFrame=requestAnimationFrame(autoScroll);
    }; this.scrollFrame=requestAnimationFrame(autoScroll);
  }
  move() {
    const t=this.position(this.drag.x);
    if(this.drag.kind==='broll'){
      const {original:o,id,edge}=this.drag,delta=(this.drag.x-this.drag.originX)/this.pps;
      const others=this.state.broll.filter(s=>s.id!==id),previous=Math.max(0,...others.filter(s=>s.start<o.start).map(s=>s.start+s.duration)),next=Math.min(this.duration,...others.filter(s=>s.start>o.start).map(s=>s.start));
      const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));let patch;
      if(edge==='start'){const start=clamp(o.start+delta,Math.max(previous,o.start-o.offset),o.start+o.duration-.05);patch={start,duration:o.start+o.duration-start,offset:o.offset+start-o.start};}
      else if(edge==='end'){patch={duration:clamp(o.duration+delta,.05,Math.min(next-o.start,o.asset.duration-o.offset))};}
      else patch={start:clamp(o.start+delta,previous,next-o.duration)};
      this.onMoveBroll?.(id,patch);return;
    }
    if(this.drag.kind==='seek') this.onSeek(t); else this.onTrim(this.drag.kind,t);
  }
  end() { if(!this.drag) return; const kind=this.drag.kind; this.drag=null; cancelAnimationFrame(this.scrollFrame); if(kind==='broll')this.onEndBroll?.();else if(kind!=='seek') this.onEndTrim(); }
  setExpanded(value){
    this.expanded=value;this.root.dataset.expanded=String(value);
    const button=document.getElementById('timeline-toggle');button.textContent=value?'Collapse tracks':'Expand tracks';button.setAttribute('aria-expanded',String(value));
  }
  placement(time,assetDuration=3){
    const start=Math.max(this.state.start,Math.min(this.state.end-.05,time));
    if(this.state.broll.some(s=>s.start<=start&&start<s.start+s.duration))return null;
    const next=Math.min(this.state.end,...this.state.broll.filter(s=>s.start>start).map(s=>s.start));
    const duration=Math.min(3,assetDuration,next-start);return duration>=.05?{start,duration}:null;
  }
  dragOver(event){
    if(this.disabled||!this.duration||!Array.from(event.dataTransfer.types).includes('application/x-cascade-broll'))return;
    event.preventDefault();this.setExpanded(true);
    const r=this.content.getBoundingClientRect(),validY=event.clientY>=r.top+34&&event.clientY<=r.bottom;
    const placement=this.placement(this.position(event.clientX),window.CascadeBrollDrag?.asset.duration||3);
    this.dropTarget=validY?placement:null;event.dataTransfer.dropEffect=this.dropTarget?'copy':'none';
    this.dropMarker.hidden=false;this.dropMarker.classList.toggle('invalid',!this.dropTarget);
    this.dropMarker.style.left=(placement?.start??this.position(event.clientX))*this.pps+'px';
    this.dropMarker.style.width=(placement?.duration||.1)*this.pps+'px';
    this.dropMarker.textContent=this.dropTarget?'Add B-roll at '+window.CascadeEditorState.formatTime(placement.start):'Drop on an empty part of the timeline';
  }
  drop(event){
    if(this.disabled||!Array.from(event.dataTransfer.types).includes('application/x-cascade-broll'))return;
    event.preventDefault();const id=event.dataTransfer.getData('application/x-cascade-broll'),placement=this.dropTarget;this.clearDrop();
    if(placement)this.onDropBroll?.(id,placement.start,placement.duration);
  }
  clearDrop(){this.dropTarget=null;this.dropMarker.hidden=true;}
  keySeek(event) {
    if(this.disabled || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault(); this.onSeek(event.key==='Home'?0:event.key==='End'?this.duration:(this.time||0)+(event.key==='ArrowRight'?1:-1)*(event.shiftKey?1:.1));
  }
  async setClip(url,info,state) {
    this.end(); this.token++; const token=this.token;
    if(this.decoder) { this.decoder.src=''; this.decoder.load(); }
    for(const frame of this.frames) URL.revokeObjectURL(frame.url);
    this.frames=[]; this.duration=info.duration; this.cues=info.cues; this.state=state; this.texts=null; this.view.scrollLeft=0; this.layout();
    const status=document.getElementById('thumbnail-status'); status.textContent='Loading clip frames…';
    const decoder=document.createElement('video'); this.decoder=decoder; decoder.muted=true; decoder.preload='auto'; decoder.playsInline=true;
    const wait=name=>new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>{cleanup(); reject(Error('Frame extraction timed out'));},10000);
      const cleanup=()=>{clearTimeout(timeout); decoder.removeEventListener(name,done); decoder.removeEventListener('error',failed);};
      const done=()=>{cleanup(); resolve();}, failed=()=>{cleanup(); reject(Error('Cannot decode clip frames'));};
      decoder.addEventListener(name,done,{once:true}); decoder.addEventListener('error',failed,{once:true});
    });
    try {
      const ready=wait('loadeddata'); decoder.src=url; await ready;
      const canvas=document.createElement('canvas'); canvas.width=160; canvas.height=90; const ctx=canvas.getContext('2d');
      const count=Math.min(24,Math.max(4,Math.ceil(info.duration/2)));
      for(let i=0;i<count && token===this.token;i++) {
        const time=Math.min(info.duration-.01,(i+.5)/count*info.duration);
        const sought=wait('seeked'); decoder.currentTime=time; await sought; if(token!==this.token) return;
        ctx.fillStyle='#06110d'; ctx.fillRect(0,0,160,90);
        const scale=Math.min(160/decoder.videoWidth,90/decoder.videoHeight),w=decoder.videoWidth*scale,h=decoder.videoHeight*scale;
        ctx.drawImage(decoder,(160-w)/2,(90-h)/2,w,h);
        const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.75));
        if(token!==this.token) return;
        if(blob) this.frames.push({time,url:URL.createObjectURL(blob)});
        this.renderFrames(); status.textContent='Loading clip frames… '+(i+1)+'/'+count;
      }
      if(token===this.token) status.textContent=this.frames.length?'Frames from selected clip':'Clip frames unavailable.';
    } catch { if(token===this.token) status.textContent='Thumbnails unavailable. Seeking and trimming still work.'; }
    finally { if(token===this.token) { decoder.src=''; decoder.load(); this.decoder=null; } }
  }
};
