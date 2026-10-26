/* Loaded only on editor_C.html. Authentication remains in flow_C.js. */
window.CascadeEditor = {async initialize({project, userId, apiJSON, apiFetch, setStatus, initializeResearch}) {
  const $ = id => document.getElementById(id);
  const {clone, normalize, History, cueAt, defaultComposition, compositionGeometry} = window.CascadeEditorState;
  const base = '/api/projects/' + encodeURIComponent(project.id) + '/editor';
  const video = $('editor-video'), overlay = $('caption-overlay');
  let current = null, info = null, history = null, chat = [], updated = 0;
  let timer, textTimer, mediaURL, pending = Promise.resolve(), revision = 0, savedRevision = -1;
  let busy = false, loading = false, gesture = null;
  let comparison = 'edited', editedTime = 0, selectedCue = 0, previewSignature = '';
  const timeline = new window.CascadeTimeline({
    onSeek: seconds => seek(seconds),
    onBeginTrim: () => { useEdited(); video.pause(); beginGesture(); },
    onTrim: (name, seconds) => previewTrim(name,seconds),
    onEndTrim: () => endGesture(),
    onBroll: id => broll?.select(id),
    onCue: index => { selectedCue=index; renderCaptionText(); }
  });
  const broll=window.CascadeBroll ? new window.CascadeBroll({
    get:()=>({state:history?.state,info,current,comparison}), commit,apiJSON,apiFetch,
    lock:setLocked,openTab:()=>document.querySelector('[data-tab="broll"]')?.click()
  }) : null;
  function geometry() { return compositionGeometry(info.width,info.height,comparison==='original'?defaultComposition:history.state.composition); }
  function renderFraming() {
    const f=history.state.composition;
    document.querySelectorAll('[data-ratio]').forEach(button=>{ button.setAttribute('aria-pressed',String(button.dataset.ratio===f.ratio)); if(button.dataset.ratio==='original') button.firstElementChild?.style.setProperty('--ratio',info.width+'/'+info.height); });
    $('framing').value=f.mode; $('frame-background').value=f.background;
    $('fit-options').hidden=f.mode!=='fit'; $('crop-options').hidden=f.mode!=='fill';
    $('crop-x').value=f.x; $('crop-y').value=f.y;
    $('crop-x-label').textContent=Math.round(f.x*100)+'%'; $('crop-y-label').textContent=Math.round(f.y*100)+'%';
    const g=compositionGeometry(info.width,info.height,f);
    $('crop-x').disabled=busy || g.scaledWidth<=g.width; $('crop-y').disabled=busy || g.scaledHeight<=g.height;
    $('composition-summary').textContent=(f.ratio==='original'?'Original ratio':f.ratio)+' · '+f.mode+' · export '+g.width+' × '+g.height;
  }
  function range() { return comparison==='original' ? {start:0,end:info.duration} : history.state; }
  function useEdited() { if(comparison!=='edited') compare('edited'); }
  function compare(mode) {
    if(!history || busy) return;
    endGesture(); video.pause();
    if(comparison==='edited') editedTime=video.currentTime;
    comparison=mode; previewSignature='';
    if(mode==='edited' && video.readyState) { const target=Math.max(history.state.start,Math.min(history.state.end,editedTime)); if(Math.abs(video.currentTime-target)>.001) video.currentTime=target; }
    render();
  }
  $('preview-original').onclick=()=>compare('original'); $('preview-edited').onclick=()=>compare('edited');
  function seek(seconds) { if(!history || busy) return; video.pause(); const r=range(); video.currentTime=Math.max(r.start,Math.min(r.end,seconds)); tick(); }
  function focusCaption() {
    if(!history || !video.paused || !history.state.captions.enabled) return;
    const s=history.state;
    if(cueAt(info.cues,video.currentTime,s)) return;
    const cue=info.cues.find(c=>c.end>s.start && c.start<s.end);
    if(cue && video.readyState) video.currentTime=Math.min(s.end-.001,Math.max(s.start,cue.start)+.001);
  }
  function renderCaptionText() {
    const cue=info?.cues[selectedCue]; $('caption-cue').value=selectedCue;
    const text=cue ? history.state.texts?.[selectedCue]??cue.text : '';
    if($('cap-text').value!==text) $('cap-text').value=text;
    $('cap-text').disabled=busy || !cue;
  }
  function previewTrim(name,value) {
    if(!history || busy || !Number.isFinite(value)) return;
    useEdited(); beginGesture(); video.pause();
    const next=clone(history.state);
    next[name]=name==='start'?Math.max(0,Math.min(value,next.end-.05)):Math.min(info.duration,Math.max(value,next.start+.05));
    history.state=normalize(next,info.duration); if(video.readyState) video.currentTime=history.state.start; render();
  }
  const histories = new Map();
  const localKey = key => 'cascade-editor:v1:' + userId + ':' + project.id + ':' + key;
  const selectionKey = localKey('selection');
  const time = seconds => { const s = Math.max(0, seconds || 0); return Math.floor(s/60) + ':' + (s%60).toFixed(2).padStart(5, '0'); };
  function recoveryKey() { return localKey(current.key); }
  function snapshot() { return {state: clone(history.state), chat: clone(chat).slice(-200), updated_at: updated}; }
  function recover() {
    if (!current || !history) return;
    try { localStorage.setItem(recoveryKey(), JSON.stringify(snapshot())); localStorage.setItem(selectionKey, JSON.stringify({job_id:current.job, clip_index:current.index})); }
    catch { $('save-status').textContent = 'Local recovery unavailable'; }
  }
  function save() {
    clearTimeout(timer);
    if (!current || !history) return pending;
    const url = current.url, key = current.key, payload = snapshot(), version = revision;
    recover();
    $('save-status').textContent = 'Saving…';
    pending = pending.catch(() => {}).then(async () => {
      await apiJSON(url, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      if (current?.key === key) {
        savedRevision = version;
        $('save-status').textContent = revision === version ? 'Saved' : 'Saving…';
        $('retry-save').hidden = true;
      }
    }).catch(error => {
      if (current?.key === key) { $('save-status').textContent = 'Could not save — retry'; $('retry-save').hidden = false; }
      throw error;
    });
    return pending;
  }
  function changed() {
    revision++; updated = Date.now(); recover();
    $('save-status').textContent = 'Saving…';
    clearTimeout(timer); timer = setTimeout(() => save().catch(() => {}), 650);
  }
  function commit(state) {
    const next=normalize(state,info.duration), previous=history.state;
    const trimmed=next.start!==previous.start || next.end!==previous.end;
    if (history.commit(next)) {
      comparison='edited'; previewSignature='';
      if(trimmed && video.readyState) { video.pause(); video.currentTime=next.start; }
      changed();
    }
    render();
  }
  function setLocked(value) {
    busy = value && (loading || !!history);
    document.querySelectorAll('#timeline-controls input, #timeline-controls button, #caption-controls input, #caption-controls select, #caption-controls textarea, #preview-original, #preview-edited, #preview-play, #ratio-controls input, #ratio-controls select, #ratio-controls button, #caption-preset, #chat-send, #export-edit, #save-clip')
      .forEach(el => el.disabled = value);
    document.querySelectorAll('#editor-sessions button').forEach(el => el.disabled = busy);
    timeline.setDisabled(value);
    broll?.setLocked(value);
    $('undo').disabled = value || !history?.undoStack.length;
    $('redo').disabled = value || !history?.redoStack.length;
    if(history) { renderCaptionText(); renderFraming(); }
  }
  function renderChat() {
    $('chat-history').replaceChildren();
    for (const message of chat) { const p = document.createElement('p'); p.textContent = (message.role === 'user' ? 'You: ' : 'Cascade: ') + message.text; $('chat-history').append(p); }
    $('chat-history').scrollTop = $('chat-history').scrollHeight;
  }
  const fields = ['enabled','font','size','bold','color','stroke','thickness','background','opacity','position'];
  function render() {
    if (!history) return;
    const state = history.state;
    renderFraming();
    broll?.render();
    $('preview-label').textContent=comparison==='edited'?'Edited preview':'Original preview';
    $('preview-description').textContent=comparison==='edited'?'Live trim and captions · original media preserved':'Full generated clip · your edits are preserved';
    $('preview-original').setAttribute('aria-pressed',String(comparison==='original'));
    $('preview-edited').setAttribute('aria-pressed',String(comparison==='edited'));
    $('preview-wrap').dataset.mode=comparison;
    $('caption-preview-note').textContent=!state.captions.enabled?'Captions are off. Turn them on to preview additional text.':info.cues.length?'Text appears at its timed segment. Select a segment to preview it.':'This clip has no timed caption data.';
    renderCaptionText();
    for (const field of fields) { const el = $('cap-'+field); if (el.type === 'checkbox') el.checked = state.captions[field]; else el.value = state.captions[field]; }
    $('trim-start').value = state.start; $('trim-end').value = state.end;
    $('start-label').textContent = time(state.start); $('end-label').textContent = time(state.end);
    $('trim-summary').textContent = 'Edited duration ' + time(state.end-state.start) + ' · trim times are relative to this generated clip.';
    $('undo').disabled = busy || !history.undoStack.length; $('redo').disabled = busy || !history.redoStack.length;
    const r=range();
    if (video.readyState && (video.currentTime < r.start || video.currentTime > r.end)) video.currentTime = r.start;
    tick();
  }
  function tick() {
    if (!history || !info) return;
    const state = history.state, r=range();
    if (video.readyState && (video.currentTime > r.end || (!video.paused && video.currentTime >= r.end))) { video.pause(); if (video.currentTime !== r.end) video.currentTime = r.end; }
    if (video.currentTime < r.start && video.readyState) video.currentTime = r.start;
    $('seek').value = video.currentTime;
    $('time-label').textContent = 'Clip '+time(video.currentTime) + ' / ' + time(info.duration);
    $('preview-time').textContent=(comparison==='edited'?'Edited ':'Original ')+time(Math.max(0,Math.min(r.end-r.start,video.currentTime-r.start)))+' / '+time(r.end-r.start);
    $('preview-play').textContent=video.paused?'▶ Play':'❚❚ Pause';
    $('preview-play').setAttribute('aria-label',video.paused?'Play preview':'Pause preview');
    $('preview-play').setAttribute('aria-pressed',String(!video.paused));
    $('play-toggle').textContent = video.paused ? 'Play' : 'Pause';
    timeline.update(state,video.currentTime,!video.paused);
    broll?.sync();
    const text=comparison==='edited'?cueAt(info.cues,video.currentTime,state):'';
    const g=geometry();
    const signature=JSON.stringify([text,state.captions,g.width,g.height]);
    if(signature!==previewSignature) {
      window.CascadeCaptions.draw(overlay,text,state.captions,g.width,g.height); previewSignature=signature;
    }
    const stage=$('preview-wrap'),frame=$('composition-frame');
    // Device screen and encoded output are independent rectangles. Never pass
    // device geometry into compositionGeometry, caption rasterization, or export.
    const shell=$('device-shell'),screen=$('device-screen');
    const choice=$('preview-device').value;
    const ratio=comparison==='original'?'original':state.composition.ratio;
    const device=comparison==='original'?'clean':choice==='auto'?({'9:16':'phone','4:3':'tablet','16:9':'desktop'}[ratio] || 'clean'):choice;
    shell.dataset.device=device;
    const screenRatio=({phone:9/19.5,tablet:4/3,desktop:16/9,tv:16/9})[device] || g.width/g.height;
    const bezel=device==='clean'?3:device==='phone'?10:14;
    const foot=device==='desktop'?34:device==='tv'?20:0;
    const availableWidth=Math.max(1,stage.clientWidth-48-bezel*2);
    const availableHeight=Math.max(1,stage.clientHeight-36-bezel*2-foot);
    const screenWidth=Math.min(availableWidth,availableHeight*screenRatio),screenHeight=screenWidth/screenRatio;
    shell.style.width=screenWidth+'px'; shell.style.height=screenHeight+'px';
    shell.style.padding=bezel+'px'; shell.style.marginBottom=foot+'px';
    screen.style.width=screenWidth+'px'; screen.style.height=screenHeight+'px';
    const scale=Math.min(screenWidth/g.width,screenHeight/g.height);
    frame.style.width=g.width*scale+'px'; frame.style.height=g.height*scale+'px';
    frame.style.background=comparison==='original'?defaultComposition.background:state.composition.background;
    const fill=comparison==='edited' && state.composition.mode==='fill';
    video.style.width=g.scaledWidth*scale+'px'; video.style.height=g.scaledHeight*scale+'px';
    video.style.left=(fill?-g.x:g.x)*scale+'px'; video.style.top=(fill?-g.y:g.y)*scale+'px';
    overlay.style.width='100%'; overlay.style.height='100%'; overlay.style.left='0'; overlay.style.top='0';
    overlay.hidden=comparison==='original';
  }

  let frame;
  function animate() { tick(); if (!video.paused) frame = requestAnimationFrame(animate); }
  video.addEventListener('play', () => { if (history && video.currentTime >= range().end-.01) video.currentTime = range().start; cancelAnimationFrame(frame); animate(); });
  for (const event of ['pause','timeupdate','seeked','seeking','loadedmetadata']) video.addEventListener(event, tick);
  new ResizeObserver(tick).observe($('preview-wrap'));
  $('play-toggle').onclick = async () => {
    if (!history || busy) return;
    if (!video.paused) { video.pause(); tick(); return; }
    try {
      if(video.readyState<2) $('playback-status').textContent='Loading video…';
      const r=range();
      if(video.currentTime<r.start || video.currentTime>=r.end-.01) video.currentTime=r.start;
      const playback=video.play(); tick(); await playback;
    } catch(error) {
      if(error.name==='AbortError' && video.paused) { $('playback-status').textContent=''; return; }
      $('playback-status').textContent='Playback failed — reload the clip and retry.';
      setStatus('Playback failed. Reload the clip and retry.');
    }
  };
  for(const event of ['waiting','loadstart']) video.addEventListener(event,()=>{ $('playback-status').textContent='Loading video…'; });
  for(const event of ['canplay','playing','seeked']) video.addEventListener(event,()=>{ $('playback-status').textContent=''; });
  $('preview-play').onclick=()=>{ if(!busy && history) $('play-toggle').click(); };
  video.addEventListener('click',()=>{ if(!busy && history) $('play-toggle').click(); });
  $('seek').oninput = event => seek(Number(event.target.value));
  function beginGesture() { if (history && !gesture) gesture = clone(history.state); }
  function endGesture() {
    clearTimeout(textTimer);
    if (!gesture || !history) return;
    const next = clone(history.state); history.state = gesture; gesture = null; commit(next);
  }
  for (const name of ['start','end']) {
    const el = $('trim-'+name);
    el.addEventListener('input', () => {
      if(!el.checkValidity()) return;
      previewTrim(name,Number(el.value));
    });
    el.addEventListener('change', endGesture); el.addEventListener('pointercancel', endGesture); el.addEventListener('blur', endGesture);
  }
  document.querySelectorAll('[data-ratio]').forEach(button=>button.onclick=()=>{
    if(!history || busy) return; endGesture(); useEdited();
    const next=clone(history.state); next.composition.ratio=button.dataset.ratio; commit(next);
  });
  $('preview-device').onchange=()=>tick();
  $('framing').onchange=event=>{
    if(!history || busy) return; const value=event.target.value; endGesture(); useEdited();
    const next=clone(history.state); next.composition.mode=value; commit(next);
  };
  for(const [id,field] of [['frame-background','background'],['crop-x','x'],['crop-y','y']]) {
    const input=$(id);
    input.addEventListener('input',()=>{
      if(!history || busy) return; const value=field==='background'?input.value:Number(input.value); useEdited(); beginGesture();
      const next=clone(history.state); next.composition[field]=value;
      history.state=normalize(next,info.duration); render();
    });
    for(const event of ['change','blur','pointercancel']) input.addEventListener(event,endGesture);
  }
  $('crop-center').onclick=()=>{ if(!history || busy) return; endGesture(); const next=clone(history.state); next.composition.x=.5; next.composition.y=.5; commit(next); };
  $('reset-trim').onclick = () => commit({...history.state, start:0, end:info.duration});
  for (const field of fields) {
    const el = $('cap-'+field);
    el.addEventListener('input', () => {
      if (!history || busy || !el.checkValidity()) return;
      const value=el.type === 'checkbox' ? el.checked : ['size','thickness','opacity'].includes(field) ? Number(el.value) : el.value;
      useEdited(); beginGesture();
      const next = clone(history.state);
      next.captions[field] = value;
      if(field!=='enabled') next.captions.enabled=true;
      history.state = next; $('caption-preset').value = 'custom'; focusCaption(); render();
    });
    el.addEventListener('change', endGesture); el.addEventListener('blur', endGesture); el.addEventListener('pointercancel', endGesture);
  }
  $('caption-preset').onchange = event => {
    if (!history || event.target.value === 'custom') return;
    const next = clone(history.state);
    Object.assign(next.captions, {enabled:true, font:'Arial', size:32, color:'#ffffff', stroke:'#000000', thickness:2, background:'#000000', opacity:0, bold:false, position:'bottom'});
    if (event.target.value === 'bold') Object.assign(next.captions, {bold:true,size:46,thickness:3});
    if (event.target.value === 'yellow') Object.assign(next.captions, {bold:true,color:'#ffff00',size:42});
    commit(next); focusCaption(); render();
  };
  $('caption-cue').onchange=event=>{ selectedCue=Number(event.target.value); renderCaptionText(); const cue=info.cues[selectedCue]; if(cue) seek(Math.max(history.state.start,cue.start)+.001); };
  $('cap-text').addEventListener('input',()=>{
    if(!history || busy || !info.cues[selectedCue]) return;
    const value=$('cap-text').value; useEdited(); beginGesture();
    history.state.texts={...history.state.texts,[selectedCue]:value};
    history.state.captions.enabled=true;
    updated=Date.now(); recover(); clearTimeout(textTimer); textTimer=setTimeout(endGesture,650);
    const cue=info.cues[selectedCue];
    if(video.paused && video.readyState && cue.end>history.state.start && cue.start<history.state.end && !(video.currentTime>=cue.start && video.currentTime<cue.end)) video.currentTime=Math.min(history.state.end-.001,Math.max(history.state.start,cue.start)+.001);
    render();
  });
  $('cap-text').addEventListener('change',endGesture); $('cap-text').addEventListener('blur',endGesture);
  function travel(direction) { if (history && !busy) { endGesture(); if (history[direction]()) { comparison='edited'; previewSignature=''; changed(); } render(); } }
  $('undo').onclick = () => travel('undo'); $('redo').onclick = () => travel('redo');
  document.addEventListener('keydown', event => {
    const typing = event.target.closest('textarea,select,[contenteditable="true"]') || (event.target.tagName === 'INPUT' && !['range','checkbox','radio','button','color'].includes(event.target.type));
    if (typing || busy || !(event.ctrlKey || event.metaKey) || event.altKey) return;
    if (event.key.toLowerCase() === 'z') { event.preventDefault(); travel(event.shiftKey ? 'redo' : 'undo'); }
    else if (event.ctrlKey && event.key.toLowerCase() === 'y') { event.preventDefault(); travel('redo'); }
  });
  document.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => {
    document.querySelectorAll('[data-tab]').forEach(tab => { const active = tab === button; tab.classList.toggle('active',active); tab.setAttribute('aria-selected',String(active)); });
    document.querySelectorAll('.tab-panel').forEach(panel => panel.hidden = panel.id !== button.dataset.tab+'-panel');
  });
  $('retry-save').onclick = () => save().catch(() => {});
  $('chat-form').onsubmit = async event => {
    event.preventDefault(); if (!history || busy) return;
    endGesture(); const message = $('chat-input').value.trim(); if (!message) return;
    const prior = clone(chat); chat.push({role:'user',text:message}); chat = chat.slice(-199); changed(); renderChat();
    setLocked(true); $('chat-status').textContent = 'Thinking…'; $('chat-input').value = '';
    try {
      const result = await apiJSON(current.url+'/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({state:history.state, chat:prior.slice(-20), message,...(broll?.context()||{})})});
      // One validated AI response is one undoable transaction.
      const previousBroll=history.state.broll; commit(result.state); broll?.afterChat(previousBroll,history.state); if(result.broll_search)broll?.showSearch(result.broll_search); comparison='edited'; focusCaption(); render(); chat.push({role:'assistant',text:result.message}); changed(); renderChat();
      $('chat-status').textContent = '';
    } catch (error) { $('chat-status').textContent = error.message; chat.push({role:'assistant',text:'No edit applied: '+error.message}); changed(); renderChat(); }
    finally { setLocked(false); render(); }
  };
  async function download(response) {
    const url = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href=url; a.download='cascade-edited.mp4'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('export-edit').onclick = async () => {
    if (!history || busy) return;
    endGesture(); setLocked(true); setStatus('Rendering edited download…');
    try { await save();
      await document.fonts.ready;
      const output=compositionGeometry(info.width,info.height,history.state.composition);
      const overlays=window.CascadeCaptions.exportFrames(info.cues,history.state,output.width,output.height);
      await download(await apiFetch(current.url+'/export', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...history.state,overlays})})); setStatus('Edited download ready. Original clip preserved.'); }
    catch (error) { setStatus(error.message); }
    finally { setLocked(false); }
  };
  $('save-clip').onclick = async () => {
    if (!current) return;
    try {
      await save();
      await apiJSON(current.url+'/save-clip', {method:'POST'});
      setStatus('Editing settings saved. Use Download edited MP4 to render these edits.');
    } catch(error) { setStatus(error.message); }
  };
  async function select(item) {
    if (loading || busy) return;
    loading = true; endGesture(); video.pause(); setLocked(true); setStatus('Loading '+item.label+'…');
    try {
      if (current && history) { histories.set(current.key, history); await save(); }
      const nextInfo = await apiJSON(item.url);
      let draft = nextInfo.draft;
      try { const local = JSON.parse(localStorage.getItem(localKey(item.key))); if (local?.updated_at > draft.updated_at && local.state?.captions) { draft = {...local, state: normalize(local.state, nextInfo.duration)}; } } catch {}
      const response = await apiFetch(item.url+'/media');
      const blobURL = URL.createObjectURL(await response.blob());
      if (mediaURL) URL.revokeObjectURL(mediaURL); mediaURL = blobURL;
      broll?.reset();
      current = item; info = nextInfo; chat = Array.isArray(draft.chat) ? draft.chat.slice(-200) : []; updated = draft.updated_at;
      history = histories.get(item.key) || new History(normalize(draft.state, info.duration));
      histories.set(item.key, history); revision = 0; savedRevision = -1;
      comparison='edited'; editedTime=history.state.start; selectedCue=0; previewSignature='';
      $('caption-cue').replaceChildren(); info.cues.forEach((cue,index)=>{ const option=document.createElement('option'); option.value=index; option.textContent=time(cue.start)+' · '+cue.text.slice(0,45); $('caption-cue').append(option); });
      timeline.setClip(mediaURL,info,history.state);
      video.src = mediaURL; video.hidden = false; video.onloadedmetadata = () => { video.currentTime = history.state.start; render(); };
      video.onerror = () => { $('playback-status').textContent='Video unavailable — select the clip again to retry.'; setStatus('Clip media could not be played. It may be missing or unsupported.'); };
      $('editor-empty').hidden = true; $('editor-clip-title').textContent = item.label;
      $('preview-warning').textContent=info.warning; $('preview-warning').hidden=!info.warning;
      $('caption-warning').textContent = info.warning || (info.cues.length ? '' : 'No timed captions are available for this clip.');
      for (const id of ['seek','trim-start','trim-end']) $(id).max = info.duration;
      document.querySelectorAll('#editor-sessions button').forEach(button => { const active = button.dataset.key === item.key; button.classList.toggle('active',active); button.setAttribute('aria-pressed',String(active)); });
      const url = new URL(location.href); url.searchParams.set('job',item.job); url.searchParams.set('clip',item.index); window.history.replaceState(null,'',url);
      document.querySelectorAll('a[href^="exports_C.html"], a[href^="canvas_C.html"]').forEach(link => { const dest = new URL(link.href); dest.searchParams.set('job',item.job); dest.searchParams.set('clip',item.index); link.href=dest; });
      renderChat(); render(); changed(); setStatus('');
    } catch(error) { setStatus(error.message + ' Select a clip to retry. Pending edits are kept locally.'); }
    finally { loading = false; setLocked(!history); }
  }
  document.addEventListener('visibilitychange', () => { if (document.hidden) { endGesture(); recover(); if (history) save().catch(() => {}); } });
  window.addEventListener('pagehide', recover);
  window.addEventListener('beforeunload', event => { endGesture(); recover(); if (history && savedRevision !== revision) { event.preventDefault(); event.returnValue=''; } });
  document.addEventListener('click', async event => {
    const link = event.target.closest('a[href]');
    if (!link || !history || event.metaKey || event.ctrlKey || link.target === '_blank' || (link && new URL(link.href,location.href).origin!==location.origin)) return;
    event.preventDefault();
    if (busy) { setStatus('Wait for the current editor operation to finish before leaving.'); return; }
    endGesture();
    try { await save(); location.assign(link.href); } catch { setStatus('Could not save before leaving. Retry save, then follow the link again.'); }
  });
  $('project-title').textContent = project.name;
  setLocked(true);
  const selectedOnly = new URLSearchParams(location.search).get('selection') === 'canvas';
  const listing = await apiJSON(base + (selectedOnly ? '?selected_only=true' : '')), available = [];
  listing.sessions.forEach((session, s) => {
    const section = document.createElement('section'), heading = document.createElement('h4'); heading.textContent=session.session_name || 'Session '+(s+1); section.append(heading);
    session.clips.forEach((clip,index) => {
      const job = clip.job_id || session.job_id, clipIndex = clip.clip_index ?? index;
      const item = {job,index:clipIndex,key:job+':'+clipIndex,url:base+'/'+job+'/'+clipIndex,label:(session.session_name || 'Session '+(s+1))+' · Clip '+(clipIndex+1)};
      available.push(item); const button = document.createElement('button'); button.type='button'; button.className='mini-clip'; button.textContent='Clip '+(clipIndex+1); button.dataset.key=item.key; button.onclick=()=>select(item); section.append(button);
    }); $('editor-sessions').append(section);
  });
  if (!available.length) { setStatus('No generated clips are available in this project. Return to the canvas to generate a clip.'); return; }
  const query = new URLSearchParams(location.search);
  let selection = listing.selection;
  try { selection = JSON.parse(localStorage.getItem(selectionKey)) || selection; } catch {}
  const explicit = query.has('job');
  const job = explicit ? query.get('job') : selection?.job_id;
  const index = explicit ? Number(query.get('clip') || 0) : selection?.clip_index;
  const chosen = available.find(item => item.job === job && item.index === index);
  initializeResearch(() => current?.job).catch(error => setStatus(error.message));
  if (explicit && !chosen) { setStatus('Selected clip is missing. Choose an available clip from the sidebar.'); setLocked(true); return; }
  setLocked(false); await select(chosen || available[0]);
}};
