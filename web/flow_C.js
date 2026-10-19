/*
  Cascade: existing Clerk + FastAPI pipeline.

  Original source + saved prompts -> independent generation groups and editor clips.

  Used by the updated:
  login_C.html
  projects_C.html
  canvas_C.html
  editor_C.html
  exports_C.html
*/

(() => {
  const $ = id => document.getElementById(id);

  const page = document.body.dataset.page;

  const LOGIN_URL = new URL(
    "login_C.html",
    window.location.href
  ).href;

  let project = null;
  let sourceJobId = null, parentClip = null;
  const generationGroups = new Map();
  let canvasJobId = null;
  const query = new URLSearchParams(location.search);
  let userId = null;
  let sourceURL = null;
  let restoredSource = null;
  let processing = false;
  let signedOut = false;

  const mediaURLs = [];

  function setStatus(message) {
    const status = $("status");

    if (status) {
      status.textContent = message;
    }
  }

  function wait(milliseconds) {
    return new Promise(resolve => {
      setTimeout(resolve, milliseconds);
    });
  }

  function loadScript(url, publishableKey) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");

      script.src = url;
      script.crossOrigin = "anonymous";

      if (publishableKey) {
        script.setAttribute(
          "data-clerk-publishable-key",
          publishableKey
        );
      }

      script.onload = resolve;

      script.onerror = () => {
        reject(new Error("Could not load Clerk."));
      };

      document.head.appendChild(script);
    });
  }

  function redirectToLogin() {
    signedOut = true;

    if ($("protected-page")) {
      $("protected-page").hidden = true;
    }

    if ($("account")) {
      $("account").hidden = true;
    }

    window.location.replace(LOGIN_URL);
  }

  // Every protected backend request gets the real
  // Clerk session token. app1.py verifies that token.
  async function apiFetch(url, options = {}) {
    if (signedOut) {
      throw new Error("Please sign in again.");
    }

    const token =
      await window.Clerk.session?.getToken();

    if (!token) {
      redirectToLogin();

      throw new Error("Please sign in again.");
    }

    const headers = new Headers(
      options.headers || {}
    );

    headers.set(
      "Authorization",
      "Bearer " + token
    );

    const response = await fetch(url, {
      ...options,
      headers,
      cache: "no-store"
    });

    if (!response.ok) {
      let message =
        "Request failed (HTTP " +
        response.status +
        ").";

      try {
        const error = await response.json();

        if (typeof error.detail === "string") {
          message = error.detail;
        }
      } catch {
        // Keep the HTTP message if no JSON was returned.
      }

      if (response.status===404 && message==='Project not found.' && page!=='projects') location.replace('projects_C.html');
      if (response.status === 401) {
        redirectToLogin();
      }

      throw new Error(message);
    }

    return response;
  }

  async function apiJSON(url, options) {
    const response = await apiFetch(
      url,
      options
    );

    return response.json();
  }

  // Scope saved prototype references to the real user.
  function jobStorageKey() {
    return "cascade-one-clip-job:" + userId + ":" + project?.id;
  }

  function projectStorageKey() {
    return "cascade-simple-project:" + userId;
  }

  function getSavedJob() {
    try {
      return sessionStorage.getItem(
        jobStorageKey()
      );
    } catch {
      return null;
    }
  }

  function saveJob(jobId) {
    try {
      sessionStorage.setItem(
        jobStorageKey(),
        jobId
      );
    } catch {
      // The editor link also carries the job ID.
    }
  }

  function getProjectName() { return project?.name || "Untitled project"; }

  function projectURL(page, job, index = 0) {
    const params = new URLSearchParams({project: project.id});
    if (job) { params.set("job", job); params.set("clip", index); }
    return page + "?" + params;
  }

  async function loadProject() {
    const id = query.get("project");
    if (!id) throw new Error("Choose a project from the projects page first.");
    try {project = await apiJSON("/api/projects/" + encodeURIComponent(id));}
    catch(error) {if(error.message.includes('Project not found')) location.replace('projects_C.html');throw error;}
    document.querySelectorAll('a[href="canvas_C.html"], a[href="editor_C.html"], a[href="exports_C.html"]')
      .forEach(link => { link.href = projectURL(link.getAttribute("href"), query.get("job"), Number(query.get("clip") || 0)); });
  }

  async function downloadClip(clip, captions = false) {
    const response = await apiFetch(captions ? clip.captions_url : clip.clip_url);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = captions ? "captions.vtt" : "cascade-clip.mp4";
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function waitFeature(jobId) {
    while (!signedOut) {
      const job = await apiJSON("/api/features/" + jobId);
      if (job.state === "error") throw new Error(job.message);
      if (job.state === "done") return job;
      setStatus(job.message); await wait(1500);
    }
    throw new Error("Please sign in again.");
  }

  function showAccount() {
    const user = window.Clerk.user;
    const profile = document.createElement("button");
    profile.type = "button"; profile.textContent = "Profile";
    profile.onclick = () => window.Clerk.openUserProfile();
    $("account")?.appendChild(profile);
    if (page !== "settings") {
      const settings = document.createElement("a"); settings.className = "button";
      settings.href = "settings_C.html"; settings.textContent = "Settings";
      $("account")?.appendChild(settings);
    }

    const name =
      user.fullName ||
      user.username ||
      user.primaryEmailAddress?.emailAddress ||
      "Your account";

    if ($("account-name")) {
      $("account-name").textContent = name;
    }

    if ($("account-id")) {
      $("account-id").textContent =
        "Account ID: " + userId;
    }

    if ($("account")) {
      $("account").hidden = false;
    }

    if ($("sign-out")) {
      $("sign-out").onclick = async () => {
        const button = $("sign-out");

        button.disabled = true;

        try {
          await window.Clerk.signOut({
            redirectUrl: LOGIN_URL
          });
        } catch (error) {
          setStatus(
            error.message ||
            "Could not sign out. Try again."
          );

          button.disabled = false;
        }
      };
    }
  }

  // A video element cannot add an Authorization header.
  // Fetch the protected video first, then play its Blob URL.
  async function attachClip(video, clip) {
    const version=String(Number(video.dataset.load || 0)+1);video.dataset.load=version;
    if(video.src.startsWith('blob:')) URL.revokeObjectURL(video.src);
    video.querySelectorAll('track').forEach(track=>{URL.revokeObjectURL(track.src);track.remove();});
    const clipURL = new URL(
      clip.clip_url,
      window.location.origin
    );

    if (
      clipURL.origin !== window.location.origin ||
      !clipURL.pathname.startsWith("/clips/")
    ) {
      throw new Error(
        "The server returned an invalid clip URL."
      );
    }

    const response = await apiFetch(
      clipURL.href
    );

    const videoBlob = await response.blob();
    if(video.dataset.load!==version)return;

    const videoURL = URL.createObjectURL(
      videoBlob
    );

    mediaURLs.push(videoURL);

    video.src = videoURL;

    if (clip.captions_url) {
      try {
        const captionsURL = new URL(
          clip.captions_url,
          window.location.origin
        );

        if (
          captionsURL.origin !== window.location.origin ||
          !captionsURL.pathname.startsWith("/clips/")
        ) {
          throw new Error(
            "Invalid captions URL."
          );
        }

        const captionsResponse = await apiFetch(
          captionsURL.href
        );

        const captionsText =
          (await captionsResponse.text()).replace(/&#(x[0-9a-f]+|[0-9]+);/gi, (entity,value)=>{
            const code=value[0].toLowerCase()==='x'?parseInt(value.slice(1),16):Number(value);
            if(!Number.isInteger(code)||code<1||code>0x10ffff)return entity;
            // WebVTT only supports named escapes; normalize legacy numeric entities
            // without turning escaped angle brackets into executable cue markup.
            return String.fromCodePoint(code).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
          });

        const captionsBlob = new Blob(
          [captionsText],
          {
            type: "text/vtt"
          }
        );

        const captionsBlobURL =
          URL.createObjectURL(captionsBlob);

        mediaURLs.push(captionsBlobURL);

        const track =
          document.createElement("track");

        track.kind = "captions";
        track.label = "Speech captions";
        track.srclang = "en";
        track.src = captionsBlobURL;
        track.default = true;

        if(video.dataset.load!==version) {URL.revokeObjectURL(captionsBlobURL);return;}
        video.appendChild(track);
      } catch (error) {
        setStatus(
          "Clip ready. Captions could not load: " +
          error.message
        );
      }
    }

    video.hidden = false;
  }

  let contextRequired=false, branchFrame=0, historyPoll;
  const reducedMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  function groupElement(id) {return document.querySelector('[data-job="'+id+'"]');}
  function navigateGeneration(id,highlight=true) {
    const node=groupElement(id),viewport=$('branch-viewport');
    if(!node || !viewport)return;
    if(highlight)node.scrollTop=0;
    const r=node.getBoundingClientRect(),v=viewport.getBoundingClientRect();
    viewport.scrollTo({left:viewport.scrollLeft+r.left-v.left-16,top:0,behavior:reducedMotion()?'instant':'smooth'});
    canvasJobId=id;saveJob(id);$('job-history').value=id;
    if(highlight) {node.classList.remove('branch-highlight');void node.offsetWidth;node.classList.add('branch-highlight');setTimeout(()=>node.classList.remove('branch-highlight'),1800);}
  }
  function branchColor(clipId) {
    const colors=['#8294ef','#dc8db7','#dca264','#79b991','#78bfc9'];
    let hash=0;for(const character of clipId)hash=(hash*31+character.charCodeAt(0))>>>0;
    return colors[hash%colors.length];
  }
  function drawBranchConnectors() {
    const track=$('branch-track');if(!track)return;
    const plane=$('branch-plane');
    let svg=plane.querySelector('.branch-connectors');
    if(!svg) {svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('branch-connectors');svg.setAttribute('aria-hidden','true');}
    svg.replaceChildren();svg.setAttribute('width','0');svg.setAttribute('height','0');plane.append(svg);
    const rect=track.getBoundingClientRect();
    svg.setAttribute('width',String(track.scrollWidth));svg.setAttribute('height',String(track.scrollHeight));
    const groups=[...generationGroups.values()];
    function edge(from,to,key,kind,index=0) {
      if(!from || !to)return;
      const a=from.getBoundingClientRect(),b=to.getBoundingClientRect();
      const x=a.right-rect.left,y=a.top+a.height/2-rect.top;
      const ex=b.left-rect.left,ey=b.top+b.height/2-rect.top;
      const path=document.createElementNS(svg.namespaceURI,'path');
      // Long branches use reserved overhead lanes, never cross an intervening card.
      const rail=12+index*6,mid=(x+ex)/2;
      path.setAttribute('d',ex-x<200 ? `M ${x} ${y} C ${mid} ${y} ${mid} ${ey} ${ex} ${ey}` :
        `M ${x} ${y} H ${x+24} V ${rail} H ${ex-24} V ${ey} H ${ex}`);
      path.dataset.kind=kind;path.dataset.parentClip=key;
      path.style.stroke=branchColor(key);svg.append(path);
    }
    groups.forEach((group,index)=>{
      const prompt=track.querySelector('[data-prompt-job="'+group.job_id+'"]'),child=groupElement(group.job_id);
      const parent=group.parent_clip;
      const origin=parent ? track.querySelector('[data-clip-id="'+parent.clip_id+'"]') :
        (group.source_job && group.source_job===sourceJobId && generationGroups.get(group.source_job)?.has_source ? $('flow-source') : null);
      edge(origin,prompt,parent?.clip_id || group.source_job,'parent-prompt',index);
      edge(prompt,child?.querySelector('h3'),group.job_id,'prompt-generation');
      // Fan out within each scrollable generation. This SVG scrolls with its clips.
      if(!child)return;
      child.querySelector('.clip-connectors')?.remove();
      const fan=document.createElementNS(svg.namespaceURI,'svg');fan.classList.add('clip-connectors');
      const r=child.getBoundingClientRect();
      fan.setAttribute('width',String(child.clientWidth));fan.setAttribute('height',String(child.scrollHeight));
      for(const card of child.querySelectorAll('[data-clip-id]')) {
        const c=card.getBoundingClientRect(),cy=c.top-r.top+child.scrollTop+c.height/2;
        const path=document.createElementNS(svg.namespaceURI,'path');
        path.dataset.clipId=card.dataset.clipId;
        path.setAttribute('d',`M 32 ${child.querySelector('h3').getBoundingClientRect().top-r.top+child.scrollTop+12} H 14 V ${cy} H ${c.left-r.left}`);fan.append(path);
      }
      child.prepend(fan);
    });
    $('branch-left').disabled=$('branch-viewport').scrollLeft<=1;
    $('branch-right').disabled=$('branch-viewport').scrollLeft>=$('branch-viewport').scrollWidth-$('branch-viewport').clientWidth-1;
  }
  function queueConnectors() {cancelAnimationFrame(branchFrame);branchFrame=requestAnimationFrame(drawBranchConnectors);}
  function layoutBranches() {
    $('branch-track').style.paddingTop=Math.max(120,30+generationGroups.size*6)+'px';
    const positions=window.CascadeBranches.layout([...generationGroups.values()]);
    for(const [id,position] of Object.entries(positions)) {const section=groupElement(id);const prompt=$('branch-track').querySelector('[data-prompt-job="'+id+'"]');if(prompt){prompt.style.gridColumn=String(position.promptColumn+1);prompt.style.gridRow='1';}section.style.gridColumn=String(position.column+1);section.style.gridRow='1';section.dataset.column=position.column;section.dataset.depth=position.depth;section.dataset.row='0';}
    drawBranchConnectors();
  }
  function parentLabel(parent) {
    const group=generationGroups.get(parent.job_id);
    return (group?'Generation '+group.order:'Unavailable generation')+' · Clip '+(Number(parent.clip_index)+1)+(parent.title?' · '+parent.title:'');
  }
  async function chooseParent(group,index,clearPrompt=true) {
    const clip=group.clips[index];if(!clip)throw Error('Choose an available parent clip.');
    parentClip={job_id:group.job_id,clip_index:index,source_job:group.source_job || group.job_id};contextRequired=false;
    $('followup-parent').hidden=false;
    $('followup-description').textContent=(clip.title || 'Clip '+(index+1))+' · '+Number(clip.start).toFixed(1)+'–'+Number(clip.end).toFixed(1)+'s · '+group.prompt;
    $('prompt-source-context').textContent='Follow-up on '+parentLabel({job_id:group.job_id,clip_index:index,title:clip.title})+' · original source';
    if(clearPrompt)$('clip-prompt').value='';
    $('clip-prompt').focus();
    const preview=$('followup-video');preview.pause();preview.hidden=true;
    const unavailable=()=>{if(parentClip?.job_id!==group.job_id || parentClip.clip_index!==index)return;contextRequired=true;preview.hidden=true;$('prompt-source-context').textContent='Parent preview unavailable · choose a valid source context';setStatus('Choose another available parent clip or search the full video before submitting.');};
    preview.onerror=unavailable;
    try {await attachClip(preview,clip);} catch(error) {unavailable();}
  }
  async function reusePrompt(group) {
    if(processing){setStatus('Wait for the current generation to finish.');return;}
    $('clip-prompt').value=group.prompt;$('clip-count').value=group.requested_clip_count;
    if(group.parent_clip) {
      const parent=generationGroups.get(group.parent_clip.job_id),index=group.parent_clip.clip_index;
      if(parent?.clips[index])await chooseParent(parent,index,false);
      else {parentClip=null;contextRequired=true;$('followup-parent').hidden=false;$('followup-video').pause();$('followup-video').hidden=true;$('followup-description').textContent='Original parent clip is unavailable. Select a valid clip or choose to search the full video.';$('prompt-source-context').textContent='Source context required before submitting';}
    } else {parentClip=null;contextRequired=false;sourceJobId=group.source_job || group.job_id;$('followup-parent').hidden=true;$('followup-video').pause();$('prompt-source-context').textContent='Full-video search · '+(group.source_name || 'original source');}
    $('clip-prompt').focus();$('clip-prompt').scrollIntoView({block:'nearest',behavior:reducedMotion()?'instant':'smooth'});
    setStatus(contextRequired?'Choose a valid source context before submitting.':'Prompt copied for review. Nothing has been submitted.');
  }
  function setCanvasBusy(value) {
    processing=value;
    for(const id of ['generate-clip','clip-count','source-video','clip-prompt'])$(id).disabled=value;
    document.querySelectorAll('.generation-retry').forEach(button=>button.disabled=value);
  }
  async function retryGeneration(group) {
    if(processing)return;
    setCanvasBusy(true);
    try {
      await apiJSON('/api/projects/'+project.id+'/generations/'+group.job_id+'/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:crypto.randomUUID()})});
      await refreshGenerationGroups();navigateGeneration(group.job_id);await pollJob(group.job_id);
    } catch(error){setStatus(error.message);}
    finally{setCanvasBusy(false);}
  }
  function renderPromptHistory() {
    const list=$('branch-track');list.querySelectorAll('.prompt-node').forEach(node=>node.remove());
    for(const group of generationGroups.values()) {
      const entry=document.createElement('section');entry.className='card prompt-node';entry.dataset.promptJob=group.job_id;entry.dataset.historyId=group.history_id || group.job_id;
      const jump=document.createElement('button');jump.type='button';jump.className='history-jump';jump.textContent='Generation '+group.order+' · '+group.prompt;jump.onclick=()=>{navigateGeneration(group.job_id);$('branch-viewport').scrollIntoView({block:'nearest',behavior:reducedMotion()?'instant':'smooth'});};
      const detail=document.createElement('p');detail.className='muted';detail.textContent=new Date(group.created_at*1000).toLocaleString()+' · '+group.requested_clip_count+' requested / '+group.clips.length+' found · '+group.state+' · '+(group.parent_clip?'Follow-up on '+parentLabel(group.parent_clip):'Full-video search');
      const reuse=document.createElement('button');reuse.type='button';reuse.className='history-reuse';reuse.textContent='Reuse prompt';reuse.onclick=()=>reusePrompt(group).catch(error=>setStatus(error.message));entry.append(jump,detail,reuse);
      if(group.state==='error') {const error=document.createElement('p');error.textContent=group.message || 'Generation failed.';error.className='history-error';entry.append(error,makeRetryButton(group));}
      list.append(entry);
    }
    layoutBranches();
  }
  function makeRetryButton(group) {const retry=document.createElement('button');retry.type='button';retry.className='generation-retry';retry.textContent='Retry request';retry.disabled=processing;retry.onclick=()=>retryGeneration(group);return retry;}

  async function showCanvasClip(jobId, job) {
    canvasJobId = jobId;
    const list = document.querySelector('.clip-group');
    const metadata = generationGroups.get(jobId) || {job_id:jobId,prompt:job.prompt || '',requested_clip_count:4};
    let section = list.querySelector('[data-job="'+jobId+'"]');
    if (!section) { section=document.createElement('section'); section.dataset.job=jobId; section.className='generation-group';section.tabIndex=0;section.setAttribute('aria-label','Generation '+metadata.order);section.addEventListener('scroll',queueConnectors,{passive:true}); list.append(section); }
    section.querySelectorAll('video').forEach(video=>{video.pause();if(video.src.startsWith('blob:'))URL.revokeObjectURL(video.src);video.querySelectorAll('track').forEach(track=>URL.revokeObjectURL(track.src));});
    section.replaceChildren();
    const heading=document.createElement('h3'); heading.textContent='Generation '+(metadata.order || generationGroups.size);
    const summary=document.createElement('p'); summary.className='muted';
    summary.textContent=(job.state || 'done')+' · '+(job.clips || []).length+' of '+metadata.requested_clip_count+' requested clips'+(job.selection_note?' · '+job.selection_note:'')+(job.message?' · '+job.message:'');
    section.append(heading,summary);
    if(job.state==='error') section.append(makeRetryButton(metadata));
    if(metadata.parent_clip) {
      const parent=document.createElement('p');parent.className='muted';parent.textContent='Builds on '+parentLabel(metadata.parent_clip)+' · '+metadata.parent_clip.start+'–'+metadata.parent_clip.end+'s';
      const reveal=document.createElement('button');reveal.type='button';reveal.className='parent-reveal';reveal.textContent='Reveal parent clip';reveal.onclick=()=>{navigateGeneration(metadata.parent_clip.job_id);const card=document.querySelector('[data-clip-id="'+metadata.parent_clip.clip_id+'"]');if(card) {const container=groupElement(metadata.parent_clip.job_id);container.scrollTop+=card.getBoundingClientRect().top-container.getBoundingClientRect().top-16;queueConnectors();} else setStatus('Parent clip is unavailable.');};section.append(parent,reveal);
    }
    const cards=document.createElement('div');cards.className='generation-clips';section.append(cards);
    for (const [index,clip] of (job.clips || []).entries()) {
      const card=document.createElement('article');card.className='clip-placeholder';card.dataset.clipId=jobId+':'+index;
      const title=document.createElement('h3');title.textContent='Clip '+(index+1)+' · '+(clip.title || 'Generated clip');
      const detail=document.createElement('p');detail.className='muted';detail.textContent=Number(clip.start).toFixed(1)+'–'+Number(clip.end).toFixed(1)+'s in original source · '+(clip.explanation || '');
      const video=document.createElement('video');video.controls=true;video.playsInline=true;video.addEventListener('loadedmetadata',queueConnectors);video.addEventListener('resize',queueConnectors);
      const edit=document.createElement('a');edit.className='button';edit.textContent='Open in editor';edit.href=projectURL('editor_C.html',jobId,index);
      const build=document.createElement('button');build.type='button';build.textContent='Build on this clip';
      build.onclick=async()=>{
        if(processing) {setStatus('Wait for the current generation to finish.');return;}
        await chooseParent({...metadata,clips:job.clips},index,!contextRequired);
      };
      card.append(title,video,detail,edit,build);cards.append(card);
      try {await attachClip(video,clip);} catch(error) {const warning=document.createElement('p');warning.textContent='Preview unavailable: '+error.message;card.append(warning);}
    }
    if(job.clips?.length) {const link=$('open-editor');link.href=projectURL('editor_C.html',jobId,0);link.classList.remove('disabled-link');link.removeAttribute('aria-disabled');link.onclick=null;}
  }

  async function refreshGenerationGroups() {
    const data=await apiJSON('/api/projects/'+project.id+'/generations');
    const list=document.querySelector('.clip-group');
    const active=canvasJobId;
    list.querySelectorAll(':scope > .muted').forEach(node=>node.remove());
    generationGroups.clear();
    for(const group of data.groups) {
      generationGroups.set(group.job_id,group);
      const section=list.querySelector('[data-job="'+group.job_id+'"]');
      const revision=JSON.stringify([group.state,group.message,group.selection_note,group.clips,group.requested_clip_count,group.parent_clip]);
      if(section?.dataset.revision===revision) continue;
      await showCanvasClip(group.job_id,group);
      list.querySelector('[data-job="'+group.job_id+'"]').dataset.revision=revision;
    }
    const current=data.groups.find(group=>group.job_id===active) || data.groups.at(-1);
    canvasJobId=current?.job_id || null;
    if(current?.clips.length) $('open-editor').href=projectURL('editor_C.html',current.job_id,0);
    renderPromptHistory();
    if(!data.groups.length) {const note=document.createElement('p');note.className='muted';note.textContent='No generation groups yet.';list.append(note);}
  }

  function showProcessingTimings(job) {
    let panel = $("processing-timings");
    if (!panel) {
      const status = $("status");
      if (!status) return;
      panel = document.createElement("details");
      panel.id = "processing-timings";
      panel.open = true;
      const summary = document.createElement("summary");
      summary.textContent = "Processing timings";
      const list = document.createElement("ul"); list.id = "processing-timing-list";
      const note = document.createElement("p"); note.className = "muted";
      note.textContent = "Server processing only; excludes browser upload and playback downloads. Model loading can be slower on the first run.";
      panel.append(summary, list, note); status.after(panel);
    }
    panel.hidden = !job.timings && !job.timing_stage;
    const list = $("processing-timing-list"); list.replaceChildren();
    for (const [label, seconds] of Object.entries(job.timings || {})) {
      const row = document.createElement("li");
      row.textContent = label + ": " + Number(seconds).toFixed(2) + "s";
      list.append(row);
    }
    if (job.timing_stage) {
      const row = document.createElement("li");
      const active = !["done", "error"].includes(job.state);
      const end = active ? Date.now() / 1000 : job.updated_at;
      const seconds = Math.max(0, (end || Date.now() / 1000) - job.timing_stage_started_at);
      row.textContent = job.timing_stage + ": " + seconds.toFixed(1) + "s (" + (active ? "running" : "interrupted") + ")";
      list.append(row);
    }
  }

  // The agent's steps (indexing, each model turn, each tool call), so a long job is never a silent wait.
  // Text only is ever shown (textContent): tool arguments can contain the user's own prompt text.
  function showAgentSteps(job, jobId) {
    const steps = Array.isArray(job.steps_log) ? job.steps_log : [];
    let panel = $("agent-steps");
    if (!panel) {
      const anchor = $("processing-timings") || $("status");
      if (!anchor) return;
      panel = document.createElement("details");
      panel.id = "agent-steps";
      const summary = document.createElement("summary");
      summary.textContent = "What the agent is doing";
      const list = document.createElement("ol"); list.id = "agent-steps-list";
      list.style.maxHeight = "14rem"; list.style.overflowY = "auto"; list.style.fontSize = "0.85em";
      panel.append(summary, list); anchor.after(panel);
    }
    if (panel.dataset.job !== jobId) { panel.dataset.job = jobId; panel.open = true; delete panel.dataset.collapsed; }
    panel.hidden = steps.length === 0;
    const list = $("agent-steps-list");
    const followBottom = list.scrollTop + list.clientHeight >= list.scrollHeight - 24;
    const times = Array.isArray(job.steps_elapsed) ? job.steps_elapsed : [];
    list.replaceChildren(...steps.map((step, i) => {
      const row = document.createElement("li");
      row.textContent = typeof times[i] === "number" ? "[" + times[i].toFixed(1) + "s] " + step : step;
      return row;
    }));
    if (followBottom) list.scrollTop = list.scrollHeight;
    if (["done", "error"].includes(job.state) && !panel.dataset.collapsed) { panel.dataset.collapsed = "1"; panel.open = false; }
  }

  async function pollJob(jobId) {
    const stop = $("stop-generation");
    if (stop) {
      stop.hidden = false;
      stop.disabled = false;
      stop.onclick = async () => {
        stop.disabled = true;
        try {
          const result = await apiJSON("/api/features/" + encodeURIComponent(jobId) + "/cancel", { method: "POST" });
          setStatus(result.message);
        } catch (error) { setStatus(error.message); stop.disabled = false; }
      };
    }
    try {
      while (!signedOut) {
      const job = await apiJSON(
        "/api/features/" + encodeURIComponent(jobId)
      );
      showProcessingTimings(job);
      showAgentSteps(job, jobId);

      if (job.state === "error") {
        await refreshGenerationGroups();
        throw new Error(
          job.message ||
          "Video processing failed."
        );
      }

      if (job.state === "done") {
        if (signedOut) return;
        if (!job.clips?.length) await refreshGenerationGroups();

        if (job.clips?.length) {
          setStatus(job.clips.length + " clip(s) ready." + (job.selection_note ? " " + job.selection_note : ""));

          await refreshGenerationGroups();
        } else {
          setStatus(
            job.selection_note || "No matching clip was found. Try a different prompt."
          );
        }

        return;
      }

      const groupStatus=document.querySelector('[data-job="'+jobId+'"] > p');
      if(groupStatus) groupStatus.textContent=job.state+' · '+(generationGroups.get(jobId)?.requested_clip_count || 4)+' clips requested · '+(job.message || 'Processing…');
      const pending=generationGroups.get(jobId);if(pending){pending.state=job.state;pending.message=job.message;renderPromptHistory();}
      const now = Date.now() / 1000;
      const elapsed = job.started_at ? Math.max(0, Math.floor(now - job.started_at)) : 0;
      const stageElapsed = job.stage_started_at ? Math.max(0, Math.floor(now - job.stage_started_at)) : 0;
      const timing = job.started_at ? " · " + elapsed + "s elapsed · " + stageElapsed + "s in this step" : "";
      setStatus((job.message || "Processing video…") + timing);

      await wait(1500);
      }
    } finally {
      if (stop) stop.hidden = true;
    }
  }

  function resetClipCard() {
    $("open-editor").classList.add("disabled-link");
    $("open-editor").setAttribute("aria-disabled", "true");
    $("open-editor").onclick = event => event.preventDefault();
  }

  // Projects are persisted by the backend and scoped to the verified Clerk user.
  async function initializeProjects() {
    const data = await apiJSON("/api/projects");
    const tiles = $("project-tiles");
    if (!data.projects.length) tiles.textContent = "No saved projects yet.";
    data.projects.forEach(item => {
      const card=document.createElement('article');card.className='project-card';
      const tile = document.createElement("a"); tile.className = "button project-tile";
      tile.textContent = item.name; tile.href = "canvas_C.html?project=" + item.id;
      const remove=document.createElement('button');remove.type='button';remove.className='project-delete';remove.textContent='Delete';remove.setAttribute('aria-label','Delete project '+item.name);
      remove.onclick=async()=>{
        if(remove.disabled || !confirm('Delete “'+item.name+'”? Its saved prompts, generated clips and editor drafts will be removed from this project. This cannot be undone.')) return;
        remove.disabled=true;
        try {const deleted=await apiJSON('/api/projects/'+item.id,{method:'DELETE'});card.remove();
          document.querySelectorAll('#clip-library [data-job]').forEach(button=>{if(deleted.job_ids.includes(button.dataset.job))button.remove();});
          for(const storage of [localStorage,sessionStorage]) for(let i=storage.length-1;i>=0;i--) {const key=storage.key(i);if(key?.startsWith('cascade-') && (key.includes(item.id) || storage.getItem(key)===item.id)) storage.removeItem(key);}
          localStorage.setItem('cascade-deleted-project:'+userId,JSON.stringify({id:item.id,at:Date.now()}));
          setStatus('Project deleted.');if(!tiles.children.length)tiles.textContent='No saved projects yet.';
        } catch(error) {setStatus('Could not delete '+item.name+': '+error.message);remove.disabled=false;}
      };
      card.append(tile,remove);tiles.appendChild(card);
    });
    const library = await apiJSON("/api/my-clips");
    for (const clip of library.clips) {
      const button = document.createElement("button"); button.type = "button";
      button.textContent = "Download · " + (clip.title || "Previously generated clip");
      button.dataset.job=new URL(clip.clip_url,location.origin).pathname.split("/")[2];
      button.onclick = () => downloadClip(clip).catch(error => setStatus(error.message));
      $("clip-library").appendChild(button);
    }
    if (!library.clips.length) $("clip-library").textContent = "No previously generated clips.";
    $("project-form").onsubmit = async event => {
      event.preventDefault(); const button = event.submitter; button.disabled = true;
      try {
        const item = await apiJSON("/api/projects", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name: $("project-name").value.trim()})});
        location.href = "canvas_C.html?project=" + item.id;
      } catch (error) { setStatus(error.message); button.disabled = false; }
    };
  }

  // Canvas page
  async function initializeCanvas() {
    $("project-title").textContent =
      getProjectName();

    $("open-editor").onclick = event => {
      event.preventDefault();

      setStatus(
        "Generate Clip 1 first, then open the editor."
      );
    };

    $('cancel-followup').onclick=()=>{parentClip=null;contextRequired=false;$('prompt-source-context').textContent='Searching the full original video';$('followup-parent').hidden=true;$('followup-video').pause();setStatus('New prompts will search the full original video.');};
    $("source-video").onchange = () => {
      sourceJobId=null;parentClip=null;contextRequired=false;$('prompt-source-context').textContent='Searching the selected full video';$('followup-parent').hidden=true;
      restoredSource = null;
      const file =
        $("source-video").files[0];

      $("file-name").textContent =
        file?.name ||
        "No video selected";

      if (sourceURL) {
        URL.revokeObjectURL(sourceURL);
      }

      if (file) {
        sourceURL =
          URL.createObjectURL(file);

        $("source-player").src =
          sourceURL;

        $("source-player").hidden = false;

        $("source-empty").hidden = true;
      } else {
        $("source-player")
          .removeAttribute("src");

        $("source-player").hidden = true;

        $("source-empty").hidden = false;
      }
    };

    $("generate-clip").onclick = async () => {
      if (processing) return;
      if(contextRequired){setStatus('Choose a valid parent clip or search the full video before submitting.');return;}

      const file =
        $("source-video").files[0] || restoredSource;

      const prompt =
        $("clip-prompt").value.trim();

      if (!file && !sourceJobId && !parentClip) {
        setStatus("Choose a video first.");
        return;
      }

      if (!prompt) {
        setStatus(
          "Enter the moment you want to find."
        );
        return;
      }

      const count=Number($('clip-count').value);
      if(!Number.isInteger(count) || count<1 || count>12) {setStatus('Choose a whole number of clips from 1 to 12.');$('clip-count').focus();return;}
      setCanvasBusy(true);

      try {
        const formData = new FormData();

        formData.append("project_id", project.id);
        formData.append("clip_count",String(count));
        formData.append("engine", "agent");
        formData.append(
          "video",
          file
        );

        formData.append(
          "search",
          prompt
        );

        formData.append(
          "mode",
          "both"
        );

        formData.append(
          "clip_length",
          "30"
        );

        setStatus("Uploading video…");

        const reuse=parentClip?.source_job || sourceJobId;
        const upload = reuse ? await apiJSON('/api/projects/'+project.id+'/generations', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt,clip_count:count,source_job:reuse,engine:'agent',request_id:crypto.randomUUID(),...(parentClip?{parent_job:parentClip.job_id,parent_clip_index:parentClip.clip_index}:{})})}) : await apiJSON('/upload',{method:'POST',body:formData});
        if(!sourceJobId) sourceJobId=upload.job_id;
        generationGroups.set(upload.job_id,{job_id:upload.job_id,prompt,requested_clip_count:count,source_job:reuse || upload.job_id});
        await refreshGenerationGroups();
        navigateGeneration(upload.job_id);

        if (!upload.job_id) {
          throw new Error(
            "The server did not return a job ID."
          );
        }

        saveJob(upload.job_id);
        canvasJobId = upload.job_id;
        const option = document.createElement("option"); option.value = upload.job_id; option.textContent = prompt + " · " + (file?.name || "Original source");
        $("job-history").prepend(option); $("job-history").value = upload.job_id;

        resetClipCard();

        await pollJob(
          upload.job_id
        );
      } catch (error) {
        setStatus(
          error.message ||
          "Could not create the clip."
        );
      } finally {
        setCanvasBusy(false);
      }
    };

    // Restore the most recent job when returning
    // from the editor within this browser tab.
    const history = $("job-history");
    project.jobs.filter(job => job.kind !== "research").forEach(job => {
      const option = document.createElement("option"); option.value = job.job_id;
      option.textContent = (job.kind === "caption-styles" ? "Caption styles" : job.prompt || "Upload") + " · " + job.source_name;
      history.appendChild(option);
    });
    history.onchange = () => {
      if(history.value)navigateGeneration(history.value);
    };
    $('branch-left').onclick=()=>$('branch-viewport').scrollBy({left:-400,behavior:reducedMotion()?'instant':'smooth'});
    $('branch-right').onclick=()=>$('branch-viewport').scrollBy({left:400,behavior:reducedMotion()?'instant':'smooth'});
    $('branch-viewport').addEventListener('scroll',queueConnectors,{passive:true});
    $('branch-viewport').addEventListener('keydown',event=>{if(event.target!==$('branch-viewport'))return;if(event.key==='ArrowLeft' || event.key==='ArrowRight'){event.preventDefault();$('branch-viewport').scrollBy({left:event.key==='ArrowRight'?340:-340,behavior:reducedMotion()?'instant':'smooth'});}});
    const branchResize=new ResizeObserver(queueConnectors);
    branchResize.observe($('branch-viewport'));branchResize.observe($('source-player'));
    $('source-player').addEventListener('loadedmetadata',queueConnectors);
    historyPoll=setInterval(()=>{if(!processing && !document.hidden && [...generationGroups.values()].some(group=>['queued','processing'].includes(group.state)))refreshGenerationGroups().catch(error=>setStatus(error.message));},1800);
    const jobId = query.get("job") || getSavedJob() || project.jobs.find(job => job.kind !== "research")?.job_id;
    const original = [...project.jobs].reverse().find(job => job.has_source && job.kind==='generation');
    sourceJobId=original?.source_job || original?.job_id || null;
    await refreshGenerationGroups();
    canvasJobId = jobId || original?.job_id;
    await initializeResearch(() => canvasJobId, () => $("source-video").files[0] || (!canvasJobId ? restoredSource : null));
    if (original) {
      try {
        const response = await apiFetch("/api/projects/" + project.id + "/source/" + original.job_id);
        restoredSource = new File([await response.blob()], original.source_name || "video.mp4");
        sourceURL = URL.createObjectURL(restoredSource);
        $("source-player").src = sourceURL; $("source-player").hidden = false; $("source-empty").hidden = true;
        $("file-name").textContent = restoredSource.name + " (saved upload)";
        $("clip-prompt").value = original.prompt;
      } catch (error) { setStatus(error.message); }
    }

    if(jobId && generationGroups.has(jobId))navigateGeneration(jobId,false);
    if (jobId && ['queued','processing'].includes(generationGroups.get(jobId)?.state)) {
      if (!project.jobs.some(item => item.job_id === jobId)) {saveJob('');setStatus("The previously selected generation is unavailable. Choose a saved group.");return;}
      processing = true;

      $("generate-clip").disabled = true;

      try {
        await pollJob(jobId);
      } catch (error) {
        setStatus(error.message);
      } finally {
        setCanvasBusy(false);
      }
    }
  }

  // Editor page
  async function initializeEditor() {
    return window.CascadeEditor.initialize({project, userId, apiJSON, apiFetch, setStatus, initializeResearch});
  }

  function renderResearch(result) {
    const container = $("research-result"); container.replaceChildren();
    const comparison = result.comparison || {};
    const summary = document.createElement("p"); summary.textContent = comparison.narrative || "Research results";
    container.appendChild(summary);
    for (const [title, items] of [["Matching traits", comparison.matching_traits], ["Traits to consider", comparison.missing_traits]]) {
      const heading = document.createElement("h4"); heading.textContent = title; container.appendChild(heading);
      const list = document.createElement("ul");
      for (const item of items || []) { const row = document.createElement("li"); row.textContent = item; list.appendChild(row); }
      if (!list.children.length) { const row = document.createElement("li"); row.textContent = "None found"; list.appendChild(row); }
      container.appendChild(list);
    }
    const heading = document.createElement("h4"); heading.textContent = "Videos analyzed"; container.appendChild(heading);
    for (const video of result.trending_summary || []) {
      const row = document.createElement("p"); row.textContent = video.title + " · " + video.channel;
      try {
        const url = new URL(video.url);
        if (url.protocol === "https:" && ["www.youtube.com", "youtube.com"].includes(url.hostname)) {
          const link = document.createElement("a"); link.textContent = "Watch video"; link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
          row.append(document.createTextNode(" · "), link);
        }
      } catch { /* Keep plain text for invalid external URLs. */ }
      container.appendChild(row);
    }
  }

  async function initializeResearch(getJob, getFile = () => null) {
    const form = $("research-form"); if (!form) return;
    form.onsubmit = async event => {
      event.preventDefault(); const button = event.submitter; button.disabled = true;
      try {
        const file = getFile(); const jobId = getJob(); const topic = $("research-topic").value.trim();
        if (!file && !jobId) throw new Error("Choose a video or open a saved generation first.");
        setStatus(file ? "Uploading video for research…" : "Starting research…");
        let response;
        if (file) {
          const body = new FormData(); body.append("video", file); body.append("topic", topic);
          response = await apiJSON("/api/projects/" + project.id + "/research-upload", {method: "POST", body});
        } else {
          response = await apiJSON("/api/projects/" + project.id + "/research", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: jobId, topic})});
        }
        const result = await waitFeature(response.job_id); renderResearch(result.research);
        setStatus("Research complete.");
      } catch (error) { setStatus(error.message); } finally { button.disabled = false; }
    };
    const researchJob = project.jobs.find(item => item.kind === "research");
    if (researchJob) {
      const result = await apiJSON("/api/features/" + researchJob.job_id);
      if (result.research) renderResearch(result.research);
      else if (["queued", "processing"].includes(result.state)) {
        waitFeature(researchJob.job_id).then(job => renderResearch(job.research)).catch(error => setStatus(error.message));
      } else if (result.state === "error") setStatus(result.message);
    }
  }

  async function initializeSettings() {
    const preferences = await apiJSON("/api/settings");
    for (const field of ["video_type", "audience", "tone", "goal"]) {
      $("settings-" + field.replace("_", "-")).value = preferences[field] || "";
    }
    document.querySelectorAll('[name="platforms"]').forEach(input => { input.checked = (preferences.platforms || []).includes(input.value); });
    $("settings-form").onsubmit = async event => {
      event.preventDefault(); const button = event.submitter; button.disabled = true;
      try {
        const data = {};
        for (const field of ["video_type", "audience", "tone", "goal"]) data[field] = $("settings-" + field.replace("_", "-")).value.trim();
        data.platforms = [...document.querySelectorAll('[name="platforms"]:checked')].map(input => input.value);
        await apiJSON("/api/settings", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
        setStatus("Your preferences were saved.");
      } catch (error) { setStatus(error.message); } finally { button.disabled = false; }
    };
  }

  async function initializeExports() {
    const list = $("saved-clips"); list.replaceChildren();
    const entries = [...project.saved_clips];
    if (query.get("job")) entries.unshift({job_id: query.get("job"), clip_index: Number(query.get("clip") || 0)});
    const seen = new Set();
    for (const entry of entries) {
      const key = entry.job_id + ":" + entry.clip_index; if (seen.has(key)) continue; seen.add(key);
      if (!project.jobs.some(item => item.job_id === entry.job_id)) { setStatus("This clip does not belong to the selected project."); continue; }
      try {
        const job = await apiJSON("/api/features/" + entry.job_id);
        const clip = job.clips?.[entry.clip_index]; if (!clip) continue;
        const card = document.createElement("section"); card.className = "card";
        const title = document.createElement("h3"); title.textContent = clip.title || "Saved clip";
        const video = document.createElement("video"); video.controls = true; video.playsInline = true;
        const download = document.createElement("button"); download.textContent = "Download original MP4";
        download.onclick = () => downloadClip(clip).catch(error => setStatus(error.message));
        const captions = document.createElement("button"); captions.textContent = "Download captions (VTT)";
        captions.onclick = () => downloadClip(clip, true).catch(error => setStatus(error.message));
        const edit = document.createElement("a"); edit.className = "button"; edit.textContent = "Open editor";
        edit.href = projectURL("editor_C.html", entry.job_id, entry.clip_index);
        card.append(title, video, download, captions, edit); list.appendChild(card); await attachClip(video, clip);
      } catch (error) { setStatus(error.message); }
    }
    if (!list.children.length) list.textContent = "No saved clips. Save a generated clip from the editor first.";
  }

  // Load Clerk and verify the session with FastAPI.
  async function start() {
    if (
      window.location.protocol === "file:"
    ) {
      setStatus(
        "Run Uvicorn and open http://127.0.0.1:8000."
      );

      return;
    }

    try {
      const configResponse = await fetch(
        "/api/auth-config",
        {
          cache: "no-store"
        }
      );

      if (!configResponse.ok) {
        throw new Error(
          "Could not load the backend Clerk configuration. Run app1.py with Uvicorn on port 8000."
        );
      }

      const config =
        await configResponse.json();

      if (
        !/^[a-zA-Z0-9.-]+$/.test(
          config.domain
        )
      ) {
        throw new Error(
          "Invalid Clerk domain."
        );
      }

      await loadScript(
        "https://" +
        config.domain +
        "/npm/@clerk/ui@1/dist/ui.browser.js"
      );

      await loadScript(
        "https://" +
        config.domain +
        "/npm/@clerk/clerk-js@6/dist/clerk.browser.js",
        config.publishable_key
      );

      await window.Clerk.load({
        ui: {
          ClerkUI:
            window.__internal_ClerkUICtor
        }
      });

      if (page === "login") {
        if (window.Clerk.session) {
          await apiJSON(
            "/api/session"
          );

          window.location.replace(
            "projects_C.html"
          );

          return;
        }

        const projectsURL = new URL(
          "projects_C.html",
          window.location.href
        ).href;

        window.Clerk.mountSignIn(
          $("sign-in"),
          {
            routing: "hash",

            forceRedirectUrl:
              projectsURL,

            signUpForceRedirectUrl:
              projectsURL,

            appearance: {
              variables: {
                colorPrimary: "#2c705b",
                borderRadius: "12px"
              }
            }
          }
        );

        setStatus("");

        return;
      }

      if (
        !window.Clerk.session ||
        !window.Clerk.user
      ) {
        redirectToLogin();
        return;
      }

      // Server-side authentication check.
      const session = await apiJSON(
        "/api/session"
      );

      if (
        session.user_id !==
        window.Clerk.user.id
      ) {
        throw new Error(
          "Your account could not be verified. Please sign in again."
        );
      }

      userId = session.user_id;

      window.Clerk.addListener(
        ({ user, session: clerkSession }) => {
          if (
            !user ||
            !clerkSession ||
            user.id !== userId
          ) {
            redirectToLogin();
          }
        }
      );

      showAccount();

      $("protected-page").hidden = false;

      setStatus("");

      if (page === "projects") {
        await initializeProjects();
      }

      if (page === "settings") await initializeSettings();

      if (!["projects", "settings"].includes(page)) await loadProject();

      if (page === "exports") await initializeExports();

      if (page === "canvas") {
        await initializeCanvas();
      }

      if (page === "editor") {
        await initializeEditor();
      }
    } catch (error) {
      setStatus(
        error.message ||
        "Could not load the page."
      );

      console.error(error);
    }
  }

  window.addEventListener('storage',event=>{
    if(event.key!=='cascade-deleted-project:'+userId || !project) return;
    try {if(JSON.parse(event.newValue)?.id===project.id) location.replace('projects_C.html');} catch {}
  });

  // Back/Forward retains the existing view and its listeners, never remounts it.
  window.addEventListener('pageshow',event=>{if(event.persisted && page==='canvas')refreshGenerationGroups().catch(error=>setStatus(error.message));});
  window.addEventListener(
    "pagehide",
    event => {
      document.querySelectorAll('video,audio').forEach(media=>media.pause());
      // A cached document needs its Blob URLs and frozen timer when restored.
      if(event.persisted)return;
      clearInterval(historyPoll);
      mediaURLs.forEach(url => {
        URL.revokeObjectURL(url);
      });

      if (sourceURL) {
        URL.revokeObjectURL(sourceURL);
      }
    }
  );

  start();
})();
