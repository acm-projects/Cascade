import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ReactFlow, ReactFlowProvider, Handle, Position, Background, BackgroundVariant,
  Controls, ControlButton, MiniMap, applyNodeChanges, useReactFlow} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './studio.css';
import {buildGraph,displayClips,clipKey,sameRef} from './graph.js';

const Play = ()=><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>;
const Film = ()=><svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3" fill="none" stroke="currentColor" strokeWidth="1.6"/><path d="M8 4v16M16 4v16M3 9h5m8 0h5M3 15h5m8 0h5" fill="none" stroke="currentColor" strokeWidth="1.4"/></svg>;
const keyOf = (group,index)=>({job_id:group.job_id,clip_index:index});
const seconds = n => `${Math.floor((n||0)/60)}:${String(Math.floor((n||0)%60)).padStart(2,'0')}`;
const JSONOptions = (method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});

function SourceNode({data}) {
  return <article className="studio-node studio-source">
    <div className="node-drag-handle"><Film/><span>ORIGINAL SOURCE</span></div>
    <button className="studio-poster source-poster nodrag nopan" onClick={data.previewSource} disabled={!data.session.source_job&&!data.file}>
      <span className="poster-play"><Play/></span><span>{data.session.source_job||data.file?'Preview original':'Your story starts here'}</span>
    </button>
    <div className="node-content"><strong>{data.sourceName||data.file?.name||'Upload a video'}</strong>
      <p>One source. Endless directions.</p>
      {!data.session.source_job&&<button className="studio-quiet nodrag" onClick={data.chooseFile}>Choose video ↗</button>}
    </div><Handle type="source" position={Position.Right}/>
  </article>;
}

function ClipNode({data}) {
  const selected = data.editorClips.some(r=>sameRef(r,data.ref));
  return <article className={'studio-node studio-clip'+(selected?' is-selected':'')}>
    <Handle type="target" position={Position.Left}/>
    <div className="node-drag-handle"><span>G{data.number} · CLIP {data.label||data.ref.clip_index+1}</span><span>{seconds(data.clip.end-data.clip.start)}</span></div>
    <button className="studio-poster nodrag nopan" onClick={()=>data.preview(data.clip)} aria-label={'Preview '+data.clip.title}>
      <span className="poster-play"><Play/></span><span>{seconds(data.clip.start)} — {seconds(data.clip.end)}</span>
    </button>
    <div className="node-content"><strong title={data.clip.title}>{data.clip.title||'Selected moment'}</strong>
      {data.revision&&<p className="clip-revision-status" role="status">{['queued','processing'].includes(data.revision.state)?'Finding similar moments…':data.revision.state==='error'?'Update failed. Your previous clip is kept.':'No new matches. Try another request.'}
        {data.revision.state==='error'&&<button className="studio-quiet" onClick={()=>data.retry(data.revision.job_id)}>Retry update</button>}</p>}
      <p title={data.clip.explanation}>{data.clip.explanation||'A moment from your original source.'}</p>
      <div className="clip-actions nodrag nopan">
        <label className="clip-select" title="Select this clip for the AI assistant and Editor">
          <input type="checkbox" checked={selected} onChange={()=>data.toggleSelection(data.ref)}
            aria-label={'Select G'+data.number+' clip '+(data.label||data.ref.clip_index+1)+': '+data.clip.title}/>
          {selected?'Selected':'Select clip'}
        </label>
      </div>
    </div><Handle type="source" position={Position.Right}/>
  </article>;
}

function GenerationNode({data}) {
  const active = ['queued','processing'].includes(data.group.state);
  return <article className={'request-node '+data.group.state}>
    <Handle type="target" position={Position.Left}/>
    <div className="request-kicker"><span className={active?'status-dot pulsing':'status-dot'}/><span>GENERATION {data.number}</span></div>
    <strong>{data.group.prompt}</strong>
    <p>{active?(data.group.message||'Finding moments…'):data.group.state==='error'?(data.group.message||'Generation failed'):
      data.group.is_updated?`${data.group.displayed_clip_count} clips · updated`:`${data.group.clips.length} of ${data.group.requested_clip_count||4} clips ready`}</p>
    {data.group.selection_note&&!data.group.is_updated&&<p className="selection-note">{data.group.selection_note}</p>}
    <div className="nodrag nopan">
      {active&&<button className="studio-quiet" onClick={()=>data.stop(data.group.job_id)}>Stop request</button>}
      {data.group.state==='error'&&<button className="studio-quiet" onClick={()=>data.retry(data.group.job_id)}>Retry request</button>}
      <button className="studio-quiet" onClick={()=>data.reuse(data.group.prompt)}>Reuse prompt</button>
    </div><Handle type="source" position={Position.Right}/>
  </article>;
}
const nodeTypes = {source:SourceNode,clip:ClipNode,generation:GenerationNode};

function Preview({item,apiFetch,onClose}) {
  const [url,setURL]=useState(''),[error,setError]=useState('');
  useEffect(()=>{
    let active=true,objectURL;
    (async()=>{
      try {
        if(item.file) objectURL=URL.createObjectURL(item.file);
        else {
          if(!item.url.startsWith('/clips/')&&!item.url.startsWith('/api/projects/'))throw Error('Invalid media URL.');
          const response=await apiFetch(item.url); objectURL=URL.createObjectURL(await response.blob());
        }
        if(active)setURL(objectURL);else URL.revokeObjectURL(objectURL);
      } catch(e){if(active)setError(e.message);}
    })();
    const escape=e=>{if(e.key==='Escape')onClose();}; window.addEventListener('keydown',escape);
    return ()=>{active=false;if(objectURL)URL.revokeObjectURL(objectURL);window.removeEventListener('keydown',escape);};
  },[item,apiFetch,onClose]);
  const close=useRef(null);useEffect(()=>{close.current?.focus();},[]);
  return <div className="studio-modal-backdrop" onClick={onClose}><section className="studio-modal preview-modal" role="dialog" aria-modal="true" aria-label={item.title} onClick={e=>e.stopPropagation()}>
    <header><strong>{item.title}</strong><button ref={close} onClick={onClose} aria-label="Close preview">×</button></header>
    {error?<p role="alert">{error}</p>:url?<video src={url} controls autoPlay playsInline/>:<p>Loading preview…</p>}
  </section></div>;
}

function Studio({project,apiJSON,apiFetch}) {
  const base='/api/projects/'+project.id, studioURL=base+'/studio';
  const [document,setDocument]=useState(null),[sessionId,setSessionId]=useState(null),[groups,setGroups]=useState([]);
  const [nodes,setNodes]=useState([]),[edges,setEdges]=useState([]),[editorClips,setEditorClips]=useState([]);
  const [prompt,setPrompt]=useState(''),[count,setCount]=useState(4),[mode,setMode]=useState('generate');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[saveState,setSaveState]=useState('Saved');
  const [file,setFile]=useState(null),[preview,setPreview]=useState(null),[newSession,setNewSession]=useState(false),[sessionName,setSessionName]=useState('');
  const fileInput=useRef(null),textarea=useRef(null),messagesEnd=useRef(null),flow=useReactFlow();
  const documentRef=useRef(null),sessionRef=useRef(null),queue=useRef(Promise.resolve()),polling=useRef(null),fitted=useRef(null),alive=useRef(true);
  const groupsRef=useRef([]),dirty=useRef(false),submission=useRef(null),viewportSnapshots=useRef(new Map());
  const session=document?.sessions.find(s=>s.id===sessionId);
  const references=useMemo(()=>editorClips.filter(ref=>session?.job_ids.includes(ref.job_id)),[editorClips,session]);
  documentRef.current=document;sessionRef.current=session;groupsRef.current=groups;

  const fail=useCallback(e=>{setError(e?.message||String(e));},[]);
  const persist=useCallback((url,method,body)=>{
    dirty.current=true;setSaveState('Saving…');
    const promise=queue.current.catch(()=>{}).then(()=>apiJSON(url,JSONOptions(method,body)));
    queue.current=promise;
    promise.then(()=>{if(alive.current&&queue.current===promise){dirty.current=false;setSaveState('Saved');}},e=>{if(alive.current){setSaveState('Not saved');fail(e);}});
    return promise;
  },[apiJSON,fail]);
  const saveSession=useCallback((sid,patch)=>{
    setDocument(current=>current?{...current,active_session_id:sid,sessions:current.sessions.map(s=>s.id===sid?
      {...s,...patch,positions:{...s.positions,...(patch.positions||{})}}:s)}:current);
    return persist(studioURL+'/sessions/'+sid+'/state','PATCH',patch);
  },[persist,studioURL]);
  const refresh=useCallback(async(full=true)=>{
    if(polling.current){await polling.current;if(!full)return;}
    const task=(async()=>{
    try {
      const listing=await apiJSON(base+'/generations');
      if(!alive.current)return;
      setGroups(listing.groups);
      if(full&&!dirty.current){const data=await apiJSON(studioURL);if(!alive.current)return;
        setDocument(data);setSessionId(id=>id&&data.sessions.some(s=>s.id===id)?id:data.active_session_id);
        setEditorClips(data.editor_clips||[]);if(!dirty.current)setError('');}
    } finally {polling.current=null;}
    })();polling.current=task;return task;
  },[apiJSON,base,studioURL]);
  useEffect(()=>{
    alive.current=true;refresh().catch(fail);
    const timer=setInterval(()=>{if(!window.document.hidden&&groupsRef.current.some(g=>['queued','processing'].includes(g.state)))refresh().catch(fail);},2400);
    const onFocus=()=>{if(!dirty.current)refresh().catch(fail);};window.addEventListener('focus',onFocus);
    return()=>{alive.current=false;clearInterval(timer);window.removeEventListener('focus',onFocus);};
  },[refresh,fail]);
  useEffect(()=>{
    if(!session)return;
    setFile(null);setPrompt('');setError('');
    fitted.current=null;
    if(session.viewport)setTimeout(()=>flow.setViewport(session.viewport),30);
  },[sessionId]);
  const activeGroups=useMemo(()=>session?session.job_ids.map(id=>groups.find(g=>g.job_id===id)).filter(Boolean):[],[groups,session]);
  const sourceName=groups.find(g=>g.job_id===session?.source_job)?.source_name || project.jobs?.find(j=>j.job_id===session?.source_job)?.source_name;

  const selectClips=useCallback(next=>{
    if(next.length>100){setError('Choose up to 100 clips.');return;}
    setEditorClips(next);persist(studioURL+'/editor-selection','PUT',{clips:next}).catch(()=>{});
  },[persist,studioURL]);
  const toggleSelection=useCallback(ref=>{
    selectClips(editorClips.some(item=>sameRef(item,ref))?editorClips.filter(item=>!sameRef(item,ref)):[...editorClips,ref]);
  },[editorClips,selectClips]);
  const previewClip=useCallback(clip=>setPreview({url:clip.clip_url,title:clip.title||'Clip preview'}),[]);
  const previewSource=useCallback(()=>{
    const s=sessionRef.current;
    if(file)setPreview({file,title:file.name});
    else if(s?.source_job)setPreview({url:base+'/source/'+s.source_job,title:sourceName||'Original source'});
  },[file,base,sourceName]);
  const stop=useCallback(jid=>apiJSON('/api/features/'+jid+'/cancel',{method:'POST'}).then(()=>refresh(false)).catch(fail),[apiJSON,refresh,fail]);
  const retry=useCallback(jid=>apiJSON(base+'/generations/'+jid+'/retry',JSONOptions('POST',{request_id:crypto.randomUUID()})).then(()=>refresh()).catch(fail),[apiJSON,base,refresh,fail]);
  const reuse=useCallback(text=>{setPrompt(text);textarea.current?.focus();},[]);
  const actions=useMemo(()=>({editorClips,file,sourceName,toggleSelection,preview:previewClip,
    previewSource,stop,retry,reuse,chooseFile:()=>fileInput.current?.click()}),
    [editorClips,file,sourceName,toggleSelection,previewClip,previewSource,stop,retry,reuse]);
  useEffect(()=>{
    if(!session)return;
    const graph=buildGraph(session,groups,actions);setNodes(graph.nodes);setEdges(graph.edges);
    if(fitted.current!==session.id){fitted.current=session.id;setTimeout(()=>{if(!session.viewport)flow.setViewport({x:35,y:25,zoom:.75});},100);}
  },[session,groups,actions,flow]);
  const switchSession=async id=>{try{await queue.current;setSessionId(id);await saveSession(id,{});}catch(e){fail(e);}};
  const saveViewport=useCallback(viewport=>{
    const current=sessionRef.current;
    if(!current)return;
    const prior=viewportSnapshots.current.get(current.id)||current.viewport;
    if(prior&&Math.abs(prior.x-viewport.x)<.5&&Math.abs(prior.y-viewport.y)<.5&&Math.abs(prior.zoom-viewport.zoom)<.001)return;
    viewportSnapshots.current.set(current.id,{...viewport});
    saveSession(current.id,{viewport}).catch(()=>{});
  },[saveSession]);
  const changeViewport=useCallback(async action=>{
    const sid=sessionRef.current?.id;
    if(action==='fit')await flow.fitView({padding:.2,duration:0});
    else if(action==='in')await flow.zoomIn({duration:0});
    else await flow.zoomOut({duration:0});
    if(sessionRef.current?.id===sid)saveViewport(flow.getViewport());
  },[flow,saveViewport]);
  const createSession=async event=>{
    event.preventDefault();setBusy(true);setError('');
    try {await queue.current;const created=await apiJSON(studioURL+'/sessions',JSONOptions('POST',{
      name:sessionName.trim()}));
      setDocument(d=>({...d,sessions:[...d.sessions,created]}));setSessionId(created.id);setNewSession(false);setSessionName('');}
    catch(e){fail(e);}finally{setBusy(false);}
  };
  const renameSession=async()=>{
    const name=window.prompt('Session name',session.name);if(name===null||name.trim()===session.name)return;
    try{await persist(studioURL+'/sessions/'+session.id,'PATCH',{name:name.trim()});await refresh();}catch(e){fail(e);}
  };
  const send=async event=>{
    event.preventDefault();if(!prompt.trim()||busy)return;
    if(references.length>12){setError('Use up to 12 checked clips for an AI request. You can keep up to 100 for the Editor.');return;}
    const sid=session.id,text=prompt.trim();
    // A network failure may happen after the server queued a paid request.
    // Resubmitting unchanged input must reuse that request instead of charging again.
    const signature=JSON.stringify({sid,text,mode,count,references,
      file:file?{name:file.name,size:file.size,lastModified:file.lastModified}:null});
    if(submission.current?.signature!==signature)submission.current={signature,id:crypto.randomUUID()};
    const request_id=submission.current.id;setBusy(true);setError('');
    try {
      await queue.current;
      if(mode==='discuss'){
        await apiJSON(studioURL+'/sessions/'+sid+'/chat',JSONOptions('POST',{message:text,references,request_id}));
      }else if(session.source_job){
        await apiJSON(studioURL+'/sessions/'+sid+'/generate',JSONOptions('POST',{prompt:text,clip_count:count,references,operation:references.length?'branch':'generate',request_id}));
      }else {
        if(!file)throw Error('Choose a source video first.');
        const form=new FormData();form.append('video',file);form.append('prompt',text);form.append('clip_count',String(count));form.append('request_id',request_id);
        await apiJSON(studioURL+'/sessions/'+sid+'/upload',{method:'POST',body:form});
      }
      submission.current=null;
      setPrompt(current=>current.trim()===text?'':current);await refresh();
    } catch(e){fail(e);}finally{setBusy(false);}
  };
  const openEditor=useCallback(async event=>{
    event?.preventDefault();if(!editorClips.length){setError('Check the clips you want to edit.');return;}
    try{await queue.current;window.location.assign('editor_C.html?project='+project.id+'&selection=canvas');}catch(e){fail(e);}
  },[editorClips,project.id,fail]);
  useEffect(()=>{
    const link=window.document.querySelector('.studio-nav a[href*="editor_C.html"]');
    link?.addEventListener('click',openEditor);return()=>link?.removeEventListener('click',openEditor);
  },[openEditor]);
  const progressSignature=groups.map(g=>g.state).join(',');
  useEffect(()=>{messagesEnd.current?.scrollIntoView({block:'nearest'});},[sessionId,session?.messages?.length,progressSignature]);
  const closePreview=useCallback(()=>setPreview(null),[]);
  const revealGeneration=jid=>flow.fitView({nodes:[{id:'generation:'+jid},{id:'clip:'+jid+':0'},{id:'clip:'+jid+':1'}],padding:.15,maxZoom:.85,duration:250});
  const retrySave=async()=>{
    try{await saveSession(session.id,{positions:Object.fromEntries(nodes.map(n=>[n.id,n.position])),
      viewport:flow.getViewport()});await persist(studioURL+'/editor-selection','PUT',{clips:editorClips});setError('');}
    catch(e){fail(e);}
  };
  if(!document||!session)return <div className="studio-loading"><span className="status-dot pulsing"/>{error||'Opening your studio…'}</div>;
  const refLabel=ref=>{for(const [index,group] of activeGroups.entries()){
    const entry=displayClips(session,groups,group).find(entry=>sameRef(entry.ref,ref));
    if(entry)return 'G'+(index+1)+' · Clip '+entry.label+' — '+(entry.clip.title||'Selected moment');
  }return 'Selected clip';};
  const allMessages=[...session.messages];
  for(const jid of session.job_ids){
    const group=groups.find(g=>g.job_id===jid);if(!group)continue;
    if(!allMessages.some(m=>m.job_id===jid))allMessages.push({id:jid,role:'user',text:group.prompt,job_id:jid,created_at:group.created_at});
  }
  return <div className="studio-shell">
    <div className="session-bar"><div className="session-picker"><span className="session-icon">▱</span><label htmlFor="studio-session">Session</label>
      <select id="studio-session" value={session.id} onChange={e=>switchSession(e.target.value)}>{document.sessions.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select>
      <button className="studio-quiet" onClick={renameSession} aria-label="Rename session">✎</button>
      <button className="new-session" onClick={()=>setNewSession(true)}>+ New session</button></div>
      <span className={'save-indicator '+(saveState==='Not saved'?'unsaved':'')} role="status">{saveState==='Saved'?'✓ ':''}{saveState}</span>
    </div>
    {error&&<div className="studio-error" role="alert"><span>{error}</span>{saveState==='Not saved'?<button onClick={retrySave}>Retry save</button>:!/API_KEY|\.env|configuration|configured/i.test(error)&&<button onClick={()=>refresh().catch(fail)}>Retry connection</button>}<button onClick={()=>setError('')} aria-label="Dismiss error">×</button></div>}
    <div className="studio-workspace">
      <aside className="studio-chat" aria-label="AI assistant">
        <header><div className="assistant-mark">✳</div><div><h1>Creative assistant</h1><p>Find your next great moment.</p></div></header>
        <div className="chat-history" aria-live="polite">
          <div className="assistant-intro"><span className="chat-eyebrow">YOUR VIDEO, REIMAGINED</span><h2>Where should<br/>we take the story?</h2>
            <p>Find moments in your video, then branch from the clips you love.</p></div>
          {!allMessages.length&&<div className="starter-prompts">{['Find the funniest moments','Find emotional turning points','Find surprising reactions'].map(text=><button key={text} onClick={()=>setPrompt(text)}>{text} ↗</button>)}</div>}
          {allMessages.map(message=>{
            const group=message.job_id&&groups.find(g=>g.job_id===message.job_id);
            return <React.Fragment key={message.id}><div className={'chat-message '+message.role}><span>{message.role==='user'?'YOU':'CASCADE'}</span><p>{message.text}</p></div>
              {group&&<div className="chat-message assistant"><span>CASCADE</span><p>{['queued','processing'].includes(group.state)?group.message||'Finding your moments…':group.state==='error'?group.message:group.parent_clips?.length&&!group.clips.length?'No new matches. Try another request.':
                `${group.parent_clips?.length?'Added similar clips:':'Found'} ${group.clips.length} ${group.clips.length===1?'clip':'clips'}. Check clips to use them with the assistant or take them to the Editor.`}</p>
                {group.selection_note&&<small>{group.selection_note}</small>}
                <button className="studio-quiet" onClick={()=>revealGeneration(group.job_id)}>View generation ↗</button></div>}</React.Fragment>;
          })}<div ref={messagesEnd}/>
        </div>
        <div className="composer-wrap">
          {references.length>0&&<div className="reference-context"><div><b>{references.length>1?references.length+' selected clips':'Selected clip'}</b><button onClick={()=>selectClips(editorClips.filter(ref=>!session.job_ids.includes(ref.job_id)))}>Clear</button></div>
            <div className="reference-chips">{references.slice(0,12).map(ref=><button key={clipKey(ref)} onClick={()=>toggleSelection(ref)}><span>{refLabel(ref)}</span> ×</button>)}</div></div>}
          <form className="chat-composer" onSubmit={send}>
            <label className="sr-only" htmlFor="studio-prompt">Message to the creative assistant</label>
            <textarea id="studio-prompt" ref={textarea} value={prompt} onChange={e=>setPrompt(e.target.value)} maxLength={2000}
              placeholder={references.length===1?'More funny moments like this clip…':references.length?'More funny moments like these clips…':'Describe the moments you’re looking for…'} rows={3}
              onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();e.currentTarget.form.requestSubmit();}}}/>
            <div className="composer-controls"><select aria-label="Assistant action" value={mode} onChange={e=>setMode(e.target.value)}><option value="generate">{references.length>1?'Combine selected inspirations':references.length?'Make more like selected':'Find clips'}</option><option value="discuss">Discuss clips</option></select>
              {mode==='generate'&&<label className="count-input"><input aria-label="Number of clips" type="number" min="1" max="12" value={count} onChange={e=>setCount(Number(e.target.value))}/> clips</label>}
              <button className="send-button" type="submit" disabled={busy||!prompt.trim()||mode==='generate'&&(!Number.isInteger(count)||count<1||count>12)} aria-label={mode==='discuss'?'Send discussion':references.length?'Generate similar clips':'Generate clips'}>{busy?'…':'↑'}</button></div>
          </form><p className="composer-note">{busy?'Saving your request…':mode==='discuss'?'Discuss the context and ideas behind your clips.':references.length>1?'Blend the qualities of your selected clips. Each new clip connects to all selected parents.':references.length?'Find different footage with the same feel. New clips branch from your selection; the originals stay.':'Check clips to guide the AI, or continue to the Editor with the same selection.'}</p>
        </div>
      </aside>
      <section className="studio-graph" aria-label="Video branching canvas">
        <div className="graph-heading"><span className="graph-kicker">AI STUDIO</span><strong>{session.name}</strong><span>{activeGroups.reduce((n,g)=>n+displayClips(session,groups,g).length,0)} clips · {activeGroups.length} generations</span></div>
        <input ref={fileInput} className="sr-only" type="file" accept="video/*" onChange={e=>setFile(e.target.files?.[0]||null)}/>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes}
          onNodesChange={changes=>setNodes(current=>applyNodeChanges(changes,current))}
          onNodeDragStop={(_,node)=>{saveSession(session.id,{positions:{[node.id]:node.position}}).catch(()=>{});}}
          onMoveEnd={(event,viewport)=>{if(event)saveViewport(viewport);}}
          minZoom={.1} maxZoom={2} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
          panOnScroll selectionOnDrag={false} onlyRenderVisibleElements
          defaultViewport={session.viewport||{x:35,y:25,zoom:.75}}>
          <Background variant={BackgroundVariant.Dots} color="#b4c1b7" gap={23} size={1}/>
          <Controls showInteractive={false} showZoom={false} showFitView={false}>
            <ControlButton aria-label="Zoom In" title="Zoom In" onClick={()=>changeViewport('in')}>+</ControlButton>
            <ControlButton aria-label="Zoom Out" title="Zoom Out" onClick={()=>changeViewport('out')}>−</ControlButton>
            <ControlButton aria-label="Fit View" title="Fit View" onClick={()=>changeViewport('fit')}>⛶</ControlButton>
          </Controls><MiniMap pannable zoomable nodeColor={n=>n.type==='source'?'#42765d':n.type==='generation'?'#b9aaa0':'#c1d6c8'} maskColor="rgba(242,245,240,.7)"/>
        </ReactFlow>
        {!session.source_job&&<div className="upload-hint"><Film/><span>{file?file.name:'Upload your source video to get started'}</span><button onClick={()=>fileInput.current?.click()}>{file?'Change video':'Choose video'}</button></div>}
        <div className="graph-legend"><span><i className="legend-editor"/> Selected for AI & Editor</span><span>Drag nodes · Scroll to pan · Pinch to zoom</span></div>
      </section>
    </div>
    <footer className="editor-tray"><div><span className="tray-icon">✓</span><strong>{editorClips.length} {editorClips.length===1?'clip':'clips'} selected</strong><span className="tray-subtitle">One selection for the AI assistant and Editor.</span></div>
      <div>{editorClips.length>0&&<button className="studio-quiet" onClick={()=>selectClips([])}>Clear selection</button>}
        <button className="continue-editor" onClick={openEditor} disabled={!editorClips.length}>Continue to Editor <span>→</span></button></div></footer>
    {newSession&&<div className="studio-modal-backdrop"><form className="studio-modal session-modal" role="dialog" aria-modal="true" aria-labelledby="new-session-title" onSubmit={createSession}>
      <h2 id="new-session-title">A new direction</h2><p>Explore another mood with the same original video. Your existing clips stay in their session.</p>
      <label htmlFor="new-session-name">Session name</label><input id="new-session-name" autoFocus maxLength={80} value={sessionName} onChange={e=>setSessionName(e.target.value)} placeholder="Funny moments, Emotional, Highlights…" required/>
      <div><button type="button" onClick={()=>setNewSession(false)}>Cancel</button><button className="continue-editor" disabled={busy||!sessionName.trim()}>Create session</button></div>
    </form></div>}
    {preview&&<Preview item={preview} apiFetch={apiFetch} onClose={closePreview}/>} 
  </div>;
}

export async function mountStudio(element,options) {
  window.document.getElementById('studio-project-name').textContent=options.project.name;
  const root=createRoot(element);root.render(<ReactFlowProvider><Studio {...options}/></ReactFlowProvider>);
  return {destroy:()=>root.unmount()};
}
