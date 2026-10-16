/* Editor-only timeline. All coordinates are generated-media seconds. */
window.CascadeTimeline = class {
  constructor({onSeek, onBeginTrim, onTrim, onEndTrim, onCue}) {
    this.onSeek=onSeek; this.onBeginTrim=onBeginTrim; this.onTrim=onTrim; this.onEndTrim=onEndTrim; this.onCue=onCue;
    this.view=document.getElementById('timeline-scroll'); this.content=document.getElementById('timeline-content');
    this.ruler=document.getElementById('timeline-ruler'); this.strip=document.getElementById('thumbnail-strip');
    this.captions=document.getElementById('timeline-captions'); this.playhead=document.getElementById('timeline-playhead');
    this.handles=[document.getElementById('handle-start'),document.getElementById('handle-end')];
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
    document.getElementById('zoom-fit').onclick=()=>this.setZoom(1);
    this.observer=new ResizeObserver(()=>this.layout()); this.observer.observe(this.view);
  }
  setDisabled(value) { this.disabled=value; this.content.setAttribute('aria-disabled',String(value)); this.handles.forEach(h=>h.setAttribute('aria-disabled',String(value))); }
  setZoom(value) {
    const anchor=(this.view.scrollLeft+this.view.clientWidth/2)/(this.pps||1);
    this.zoom=Math.max(1,Math.min(12,value)); this.layout();
    this.view.scrollLeft=Math.max(0,anchor*this.pps-this.view.clientWidth/2);
  }
  layout() {
    if(!this.duration) return;
    const width=Math.max(240,this.view.clientWidth-24)*this.zoom;
    this.pps=width/this.duration; this.content.style.width=width+'px';
    document.getElementById('timeline-zoom').value=this.zoom;
    document.getElementById('zoom-label').textContent=this.zoom.toFixed(1)+'×';
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
    if(playing && !this.drag) { const x=time*this.pps; if(x<this.view.scrollLeft+12 || x>this.view.scrollLeft+this.view.clientWidth-36) this.view.scrollLeft=Math.max(0,x-this.view.clientWidth*.25); }
    this.playhead.setAttribute('aria-valuenow',time.toFixed(2)); this.playhead.setAttribute('aria-valuemax',this.duration);
    this.handles.forEach((h,i)=>{ const name=i?'end':'start'; h.setAttribute('aria-valuenow',state[name].toFixed(2)); h.setAttribute('aria-valuemin',i?state.start+.05:0); h.setAttribute('aria-valuemax',i?this.duration:state.end-.05); h.setAttribute('aria-valuetext',window.CascadeEditorState.formatTime(state[name])); });
    if(this.texts!==JSON.stringify(state.texts||{}) || this.captionEnabled!==state.captions.enabled) {
      this.texts=JSON.stringify(state.texts||{}); this.captionEnabled=state.captions.enabled; this.renderCues();
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
    if(this.drag.kind==='seek') this.onSeek(t); else this.onTrim(this.drag.kind,t);
  }
  end() { if(!this.drag) return; const kind=this.drag.kind; this.drag=null; cancelAnimationFrame(this.scrollFrame); if(kind!=='seek') this.onEndTrim(); }
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
