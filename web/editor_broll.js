/* Pexels UI and synchronized, muted stock preview. All network requests use authenticated Cascade APIs. */
window.CascadeBroll = class {
  constructor({get, commit, apiJSON, apiFetch, lock, openTab, seek}) {
    Object.assign(this,{get,commit,apiJSON,apiFetch,lock,openTab,seek});
    this.$=id=>document.getElementById(id); this.results=[]; this.selected=null; this.result=null; this.urls=new Map(); this.generation=0;
    this.main=this.$('editor-video'); this.frame=this.$('footage-layer');
    this.video=document.createElement('video'); this.video.id='broll-live'; this.video.muted=true; this.video.playsInline=true; this.video.preload='auto'; this.video.hidden=true;
    this.cover=document.createElement('div'); this.cover.id='broll-loading'; this.cover.hidden=true; this.frame.append(this.video,this.cover);
    this.video.addEventListener('loadeddata',()=>this.sync()); this.video.addEventListener('seeked',()=>this.sync());
    this.video.addEventListener('error',()=>{this.failed=this.activeAsset; this.status('B-roll playback failed. Replace the footage or retry loading the clip.'); this.sync();});
    for(const event of ['seeking','seeked','pause','play','timeupdate']) this.main.addEventListener(event,()=>this.sync());
    this.$('broll-result-preview').addEventListener('error',()=>this.status('This stock preview cannot be played in the browser. Choose another result.'));
    this.$('broll-search-form').onsubmit=e=>{e.preventDefault();this.search(this.$('broll-query').value,1);};
    this.$('broll-more').onclick=()=>this.search(this.query,this.page+1);
    this.$('broll-add').onclick=()=>this.add(false); this.$('broll-replace').onclick=()=>this.add(true);
    this.$('broll-timing-form').onsubmit=e=>{e.preventDefault();this.update();};
  }
  status(text) { this.$('broll-status').textContent=text; }
  setLocked(value) {
    this.locked=value;
    document.querySelectorAll('#broll-panel input,#broll-panel select,#broll-panel button').forEach(e=>e.disabled=value);
    this.$('broll-add').disabled=value||!this.result;
    this.$('broll-replace').disabled=value||!this.result||!this.selected;
    this.$('broll-update').disabled=value||!this.selected;
  }
  reset() {
    this.generation++; for(const promise of this.urls.values()) promise.then(url=>URL.revokeObjectURL(url)).catch(()=>{});
    this.urls.clear(); this.results=[]; this.result=null; this.selected=null; this.failed=null; this.signature=''; this.activeAsset=null;
    this.video.pause(); this.video.removeAttribute('src'); this.video.load(); this.video.hidden=true; this.cover.hidden=true;
    const preview=this.$('broll-result-preview'); preview.pause(); preview.removeAttribute('src'); preview.load(); preview.hidden=true;
    this.$('broll-results').textContent='Search to find footage for your video.';this.$('broll-preview-empty').hidden=false; this.$('broll-more').hidden=true; this.$('broll-result-credit').replaceChildren(); this.status('');
  }
  media(id,thumbnail=false) {
    const {current}=this.get(); const key=(thumbnail?'image:':'video:')+id;
    if(!this.urls.has(key)) {
      const promise=this.apiFetch(current.url+'/broll/'+encodeURIComponent(id)+(thumbnail?'/thumbnail':'/media'))
        .then(r=>r.blob()).then(blob=>URL.createObjectURL(blob));
      this.urls.set(key,promise); promise.catch(()=>{if(this.urls.get(key)===promise)this.urls.delete(key);});
    }
    return this.urls.get(key);
  }
  async search(query,page) {
    if(this.locked) return; query=query.trim(); if(!query) return;
    const generation=this.generation; this.lock(true); this.status('Searching Pexels…');
    try { const data=await this.apiJSON(this.get().current.url+'/broll/search?'+new URLSearchParams({query,page}));
      if(generation===this.generation) this.showSearch(data,page>1);
    } catch(error) {if(generation===this.generation)this.status(error.message);}
    finally {this.lock(false);}
  }
  showSearch(data,append=false) {
    this.query=data.query; this.page=data.page; this.$('broll-query').value=data.query;
    if(!append) {this.results=[];this.result=null;this.$('broll-results').replaceChildren();this.$('broll-result-preview').pause();this.$('broll-result-preview').hidden=true;this.$('broll-preview-empty').hidden=false;this.$('broll-result-credit').replaceChildren();}
    const generation=this.generation;
    for(const asset of data.results) {
      if(this.results.some(a=>a.id===asset.id) || this.results.length>=120) continue;
      this.results.push(asset); const card=document.createElement('article'); card.className='broll-result';
      const image=document.createElement('img');image.alt='Stock video thumbnail';image.loading='lazy';
      this.media(asset.id,true).then(url=>{if(generation===this.generation)image.src=url;}).catch(()=>{image.alt='Thumbnail unavailable';});
      card.draggable=true;card.dataset.dragAsset=asset.id;
      card.addEventListener('dragstart',event=>{if(this.locked){event.preventDefault();return;}event.dataTransfer.setData('application/x-cascade-broll',asset.id);event.dataTransfer.effectAllowed='copy';window.CascadeBrollDrag={asset};card.classList.add('dragging');});
      card.addEventListener('dragend',()=>{window.CascadeBrollDrag=null;card.classList.remove('dragging');});
      const label=document.createElement('p');label.textContent='Result '+this.results.length+' · '+asset.duration+'s · '+asset.creator;
      const credit=this.credit(asset); const preview=document.createElement('button');preview.type='button';preview.textContent='Select / preview';preview.dataset.asset=asset.id;
      preview.onclick=()=>this.choose(asset);card.append(image,label,credit,preview);this.$('broll-results').append(card);
    }
    this.$('broll-more').hidden=!data.has_more||this.results.length>=120;
    this.status(this.results.length?this.results.length+' results. Preview footage, then add it to your clip.':'No footage found. Try a different search.');
    this.openTab();this.setLocked(this.locked);
  }
  credit(asset) {
    const a=document.createElement('a');a.textContent='Video by '+asset.creator+' on Pexels';a.href=asset.source_url;a.target='_blank';a.rel='noopener noreferrer';return a;
  }
  async choose(asset) {
    if(this.locked) return; const generation=this.generation;this.lock(true);this.status('Loading stock preview…');
    try {const url=await this.media(asset.id);if(generation!==this.generation)return;
      this.result=asset;const preview=this.$('broll-result-preview');preview.src=url;preview.hidden=false;preview.muted=true;
      this.$('broll-result-credit').replaceChildren(this.credit(asset));this.$('broll-preview-empty').hidden=true;
      if(!this.selected) {const {state}=this.get();this.$('broll-start').value=state.start;this.$('broll-duration').value=Math.min(3,asset.duration,state.end-state.start);this.$('broll-offset').value=0;}
      this.status('Footage selected. Set timing and click Add to clip.');
    }catch(error){this.status(error.message);}finally{this.lock(false);}
  }
  values() {return {start:Number(this.$('broll-start').value),duration:Number(this.$('broll-duration').value),offset:Number(this.$('broll-offset').value),mode:this.$('broll-mode').value};}
  async add(replace) {
    if(this.locked||!this.result)return;
    try {const next=window.CascadeEditorState.clone(this.get().state);const values=this.values();
      let id=this.selected;
      if(replace) {const segment=next.broll.find(s=>s.id===id);if(!segment)throw Error('Select a segment to replace.');Object.assign(segment,values,{asset:this.result});}
      else {id=crypto.randomUUID().replaceAll('-','');next.broll.push({id,asset:this.result,...values});}
      window.CascadeEditorState.validateBroll(next.broll,this.get().info.duration);
      this.commit(next);this.select(id);this.seek?.(Math.max(next.start,values.start)+.001);this.status(replace?'B-roll replaced.':'B-roll added. Speaker audio preserved.');
    }catch(error){this.status(error.message);}
  }
  async drop(assetId,start) {
    if(this.locked)return;const asset=this.results.find(a=>a.id===assetId);if(!asset){this.status('Search for this footage again before dragging it into this clip.');return;}
    const {state}=this.get();if(state.broll.some(s=>s.start<=start&&start<s.start+s.duration))return;
    const next=Math.min(state.end,...state.broll.filter(s=>s.start>start).map(s=>s.start));
    const duration=Math.min(3,asset.duration,next-start);if(duration<.05)return;
    const generation=this.generation;this.lock(true);this.status('Preparing B-roll…');
    try{await this.media(asset.id);if(generation!==this.generation)return;
      const edit=window.CascadeEditorState.clone(this.get().state),id=crypto.randomUUID().replaceAll('-','');
      edit.broll.push({id,asset,start,duration,offset:0,mode:'fill'});window.CascadeEditorState.validateBroll(edit.broll,this.get().info.duration);
      this.commit(edit);this.select(id);this.seek?.(start+.001);this.status('B-roll added at '+start.toFixed(2)+'s. Drag its edges to trim.');
    }catch(error){this.status(error.message);}finally{this.lock(false);}
  }
  update() {
    if(this.locked||!this.selected)return;
    try {const next=window.CascadeEditorState.clone(this.get().state);const segment=next.broll.find(s=>s.id===this.selected);if(!segment)throw Error('Select a B-roll segment.');Object.assign(segment,this.values());
      window.CascadeEditorState.validateBroll(next.broll,this.get().info.duration);this.commit(next);this.status('B-roll timing updated.');
    }catch(error){this.status(error.message);}
  }
  select(id) {
    this.selected=id;const segment=this.get().state.broll.find(s=>s.id===id);
    if(segment)for(const field of ['start','duration','offset','mode'])this.$('broll-'+field).value=segment[field];
    this.openTab();this.signature='';this.render();this.setLocked(this.locked);
  }
  render() {
    const {state,info}=this.get();if(!state)return;
    if(this.selected&&!state.broll.some(s=>s.id===this.selected))this.selected=null;
    const signature=JSON.stringify([state.broll,state.start,state.end,this.selected]);
    if(signature!==this.signature) {
      this.signature=signature;
      const selected=state.broll.find(s=>s.id===this.selected);
      if(selected)for(const field of ['start','duration','offset','mode'])this.$('broll-'+field).value=selected[field];
      const list=this.$('broll-segments');list.replaceChildren();
      for(const s of state.broll) {
        const row=document.createElement('article');row.className='broll-segment';const title=document.createElement('p');
        const visible=Math.max(0,Math.min(state.end,s.start+s.duration)-Math.max(state.start,s.start));
        title.textContent='At '+s.start.toFixed(2)+'s · '+s.duration.toFixed(2)+'s long · '+s.asset.creator+(visible===0?' · Hidden by trim':visible<s.duration?' · Partially hidden by trim':'');
        const select=document.createElement('button');select.type='button';select.textContent=s.id===this.selected?'Editing timing above':'Edit timing / replace';select.onclick=()=>{if(!this.locked)this.select(s.id);};
        const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';remove.onclick=()=>{if(this.locked)return;const next=window.CascadeEditorState.clone(this.get().state);next.broll=next.broll.filter(b=>b.id!==s.id);this.commit(next);};
        row.append(title,this.credit(s.asset),select,remove);list.append(row);
        this.media(s.asset.id).catch(error=>this.status(error.message));
      }
      if(!state.broll.length)list.textContent='No B-roll added yet. Find footage above, then use Add or drag it onto the timeline.';
      this.setLocked(this.locked);
    }
    this.$('broll-start').max=info.duration;
  }
  afterChat(previous,state) {
    const added=state.broll.filter(s=>!previous.some(p=>p.id===s.id));
    if(added.length===1)this.select(added[0].id);
  }
  context() {return {result_ids:this.results.map(a=>a.id),selected_segment:this.selected};}
  sync() {
    const {state,comparison}=this.get();if(!state)return;
    const t=this.main.currentTime;
    const segment=comparison==='edited'&&t>=state.start&&t<state.end?state.broll.find(s=>s.start<=t&&t<s.start+s.duration):null;
    if(!segment) {this.video.hidden=true;this.cover.hidden=true;this.video.pause();return;}
    const {compositionGeometry}=window.CascadeEditorState;const {info}=this.get();const g=compositionGeometry(info.width,info.height,state.composition);
    this.video.style.objectFit=segment.mode==='fill'?'cover':'contain';this.video.style.background=state.composition.background;
    this.cover.hidden=false;this.cover.textContent=this.failed===segment.asset.id?'B-roll unavailable':'Loading B-roll…';
    if(this.activeAsset!==segment.asset.id) {
      this.activeAsset=segment.asset.id;this.failed=null;this.video.hidden=true;this.video.pause();this.video.removeAttribute('src');this.video.load();
      const generation=this.generation;
      this.media(segment.asset.id).then(url=>{if(generation===this.generation&&this.activeAsset===segment.asset.id){this.video.src=url;this.sync();}}).catch(error=>{if(generation===this.generation){this.failed=segment.asset.id;this.status(error.message);}});
    }
    if(this.failed===segment.asset.id||this.video.readyState<2||this.main.seeking){this.video.hidden=true;this.video.pause();return;}
    const target=segment.offset+t-segment.start;
    if(Math.abs(this.video.currentTime-target)>(this.main.paused?.025:.12)) {this.video.hidden=true;if(!this.video.seeking)this.video.currentTime=target;return;}
    if(this.video.seeking){this.video.hidden=true;return;}
    this.video.hidden=false;this.cover.hidden=true;
    if(this.main.paused)this.video.pause();else if(this.video.paused)this.video.play().catch(()=>{this.video.hidden=true;this.cover.hidden=false;this.cover.textContent='B-roll playback unavailable';});
    // Output dimensions come from the composition; the device shell is only decoration.
    this.video.style.aspectRatio=g.width+'/'+g.height;
  }
};
