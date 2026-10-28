/* File support says nothing about installed Instagram targets or retained captions. */
window.CascadeInstagramShare={
  available(env=window){return !!env.isSecureContext&&typeof env.navigator?.share==='function'&&typeof env.navigator?.canShare==='function'&&typeof env.File==='function';},
  prepare(blob,filename,env=window){
    if(!this.available(env))return null;
    try{const file=new env.File([blob],filename,{type:'video/mp4'});return env.navigator.canShare({files:[file]})?file:null;}catch{return null;}
  },
  share(file,text,env=window){
    if(!file||!this.available(env)||!env.navigator.canShare({files:[file]}))throw new Error('File sharing is unavailable. Use Download & Open Instagram.');
    let data={files:[file]};
    if(text){try{if(env.navigator.canShare({...data,text}))data.text=text;}catch{}}
    // Called synchronously from the click: rendering must have finished beforehand.
    return env.navigator.share(data);
  },
  async downloadAndOpen({download,open}){
    let popup=null;try{popup=open('about:blank');if(popup)popup.opener=null;}catch{}
    try{
      await download();
      if(popup&&!popup.closed){popup.location.href='https://www.instagram.com/';return {ready:true,message:'MP4 download started. Click Create and select your downloaded clip.'};}
      return {ready:true,message:'MP4 download started. Instagram popup was blocked or closed. Allow popups and try again, or use Open Instagram below.'};
    }catch(error){popup?.close();throw error;}
  },
  message(error){return error?.name==='AbortError'?'Sharing canceled or no share target was available. Try again, or use Download & Open Instagram.':error?.name==='NotAllowedError'?'Sharing was blocked. Tap Share video again, or use Download & Open Instagram.':'Could not share the video. Try again, or use Download & Open Instagram.';}
};
/* One in-flow preparation section shares posting state across gallery clips. */
window.CascadePostPreparation=class {
  constructor({apiJSON,url,render,payload,download,filename,userId,projectId}) {
    Object.assign(this,{apiJSON,url,render,payload,download,filename,userId,projectId});this.records=new Map();this.current=null;
    this.section=document.createElement('section');this.section.className='post-section';this.section.hidden=true;this.section.setAttribute('role','region');this.section.setAttribute('aria-label','Prepare post');this.section.id='prepare-post-section';
    this.section.addEventListener('keydown',event=>{event.stopPropagation();if(event.key==='Escape'){event.preventDefault();this.close();}});
    document.getElementById('export-deck').after(this.section);
    this.playHandler=event=>{if(!this.current)return;if(event.target===this.preview)document.querySelectorAll('.export-media-card video').forEach(video=>video.pause());else this.preview?.pause();};
    document.addEventListener('play',this.playHandler,true);
  }
  key(row){return this.userId+':'+this.projectId+':'+row.job_id+':'+row.clip_index;}
  async record(row){
    const key=this.key(row);if(this.records.has(key)){const existing=this.records.get(key);await existing.ready;return existing;}
    const rec={row,data:{name:row.clip.title||'Clip '+row.number,caption:'',hashtags:[],cover_time:null},revision:0,saved:0,status:'Loading…'};this.records.set(key,rec);
    try{const local=JSON.parse(localStorage.getItem('cascade-post-pending:v1:'+key));if(local){rec.data=local;rec.revision=1;}}catch{}
    rec.ready=this.apiJSON(this.url(row)+'/post').then(data=>{if(!rec.revision)rec.data=data;rec.status=rec.revision?'Unsaved changes':'Saved';}).catch(()=>{rec.status='Could not load saved post. Retry before editing.';rec.loadFailed=true;});
    await rec.ready;if(rec.revision&&!rec.loadFailed)this.save(rec);return rec;
  }
  changed(rec){rec.revision++;rec.status='Saving…';try{localStorage.setItem('cascade-post-pending:v1:'+this.key(rec.row),JSON.stringify(rec.data));}catch{}this.status(rec);clearTimeout(rec.timer);rec.timer=setTimeout(()=>this.save(rec),400);}
  async save(rec){
    if(rec.saving||rec.loadFailed)return;rec.saving=true;rec.status='Saving…';this.status(rec);const version=rec.revision;
    try{await this.apiJSON(this.url(rec.row)+'/post',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(rec.data)});rec.saved=version;rec.status='Saved';if(version===rec.revision)localStorage.removeItem('cascade-post-pending:v1:'+this.key(rec.row));}
    catch(error){rec.status='Not saved: '+error.message;}
    finally{rec.saving=false;this.status(rec);if(rec.revision>version)this.save(rec);}
  }
  status(rec){if(this.current===rec){this.saveLabel.textContent=rec.status;this.retry.hidden=rec.status==='Saved'||rec.status==='Saving…';}}
  async open(row,anchor,{scroll=true}={}){
    this.close(false);const token={};this.openToken=token;const rec=await this.record(row);if(this.openToken!==token)return;
    this.current=rec;this.anchor=anchor;anchor.setAttribute('aria-expanded','true');this.section.replaceChildren();
    const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e;};
    const button=(text,fn)=>{const b=el('button','',text);b.type='button';b.onclick=fn;return b;};
    const header=el('div','post-header');const thumb=el('img','post-thumb');thumb.alt='Clip thumbnail';thumb.src=row.coverURL||row.posterURL||'';const title=el('strong','',rec.data.name||'Clip '+row.number);
    const identity=el('div','post-identity'),heading=el('h2','','Prepare post');heading.tabIndex=-1;
    const source=el('p','post-note','Session '+(row.wave.session_number||1)+' · Wave '+(row.wave.wave_number||1)+' · Clip '+row.number);
    identity.append(heading,title,source);header.append(thumb,identity,button('Collapse ↑',()=>this.close()));header.lastChild.setAttribute('aria-label','Collapse Prepare post');this.section.append(header);
    const layout=el('div','post-layout'),previewWrap=el('div','post-preview'),controls=el('div','post-controls');
    const preview=el('video');this.preview=preview;preview.controls=true;preview.playsInline=true;preview.preload='auto';preview.poster=row.coverURL||row.posterURL||'';preview.setAttribute('aria-label','Edited preview: '+(rec.data.name||'Clip '+row.number));
    const previewStatus=el('p','post-note','Loading edited preview…');previewStatus.setAttribute('role','status');
    const loadPreview=async()=>{previewRetry.hidden=true;try{await this.render(row);if(this.openToken!==token)return;preview.src=row.objectURL;previewStatus.textContent='';prepareShare();}catch(error){if(this.openToken!==token)return;previewStatus.textContent='Preview unavailable: '+error.message;previewRetry.hidden=false;rec.shareFile=null;rec.shareChecked=true;rec.refreshUI?.();}};
    const previewRetry=button('Retry preview',loadPreview);previewRetry.hidden=true;previewWrap.append(preview,previewStatus,previewRetry);layout.append(previewWrap,controls);this.section.append(layout);
    const field=(label,tag,value,max)=>{const wrap=el('label','post-field',label),input=el(tag);input.value=value;input.maxLength=max;wrap.append(input);controls.append(wrap);input.disabled=!!rec.loadFailed;return input;};
    const name=field('Title','input',rec.data.name,160);name.oninput=()=>{rec.data.name=name.value;title.textContent=name.value||'Clip '+row.number;this.changed(rec);};
    const caption=field('Post caption','textarea',rec.data.caption,5000);caption.rows=3;caption.placeholder='Write a caption for your post…';caption.oninput=()=>{rec.data.caption=caption.value;this.changed(rec);};
    const note=el('p','post-note','Post copy is separate from video subtitles.');controls.append(note);
    const tagsLabel=el('div','post-field','Hashtags'),tags=el('div','post-tags');tagsLabel.append(tags);controls.append(tagsLabel);
    const clean=value=>'#'+value.replace(/^#+/,'').replace(/[^\p{L}\p{N}_]/gu,'').slice(0,99);
    const drawTags=()=>{tags.replaceChildren();rec.data.hashtags.forEach((tag,index)=>{const chip=el('span','post-chip'),input=el('input');input.value=tag;input.maxLength=100;input.setAttribute('aria-label','Edit hashtag '+(index+1));input.disabled=!!rec.loadFailed;input.onchange=()=>{const value=clean(input.value);rec.data.hashtags[index]=value;rec.data.hashtags=[...new Set(rec.data.hashtags.filter(t=>t!=='#'))];this.changed(rec);drawTags();};const remove=button('×',()=>{rec.data.hashtags.splice(index,1);this.changed(rec);drawTags();});remove.setAttribute('aria-label','Remove '+tag);remove.disabled=!!rec.loadFailed;chip.append(input,remove);tags.append(chip);});};drawTags();
    const addRow=el('div','post-actions'),tagInput=el('input');tagInput.placeholder='Add hashtag';tagInput.maxLength=100;tagInput.setAttribute('aria-label','New hashtag');const add=()=>{const tag=clean(tagInput.value);if(tag!=='#'&&!rec.data.hashtags.includes(tag)&&rec.data.hashtags.length<30){rec.data.hashtags.push(tag);tagInput.value='';this.changed(rec);drawTags();}};tagInput.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add();}};addRow.append(tagInput,button('Add',add));controls.append(addRow);
    const coverStatus=el('p','post-note');coverStatus.setAttribute('role','status');controls.append(coverStatus);
    const cover=el('div','post-cover');cover.hidden=true;const video=el('video');video.muted=true;video.playsInline=true;video.preload='auto';const slider=el('input');slider.type='range';slider.min=0;slider.step=.04;slider.setAttribute('aria-label','Cover frame time in edited clip');const coverTime=el('span','post-note');let coverTask;
    const seek=()=>{video.currentTime=Number(slider.value);coverTime.textContent=Number(slider.value).toFixed(2)+'s in edited clip';};slider.oninput=seek;video.onloadedmetadata=()=>{slider.max=Math.max(0,video.duration-.05);slider.value=Math.min(rec.data.cover_time||0,Number(slider.max));seek();};
    const choose=button(rec.data.cover_time===null?'Choose cover':'Choose cover · '+rec.data.cover_time.toFixed(2)+'s',async()=>{cover.hidden=!cover.hidden;choose.setAttribute('aria-expanded',String(!cover.hidden));if(cover.hidden)return;coverStatus.textContent='Loading edited clip…';try{await this.render(row);if(this.openToken!==token)return;video.src=row.objectURL;coverTask=true;coverStatus.textContent='';}catch(error){coverStatus.textContent='Cover unavailable: '+error.message;}});
    const use=button('Use this frame',()=>{if(!coverTask||video.readyState<2||video.seeking)return;const canvas=document.createElement('canvas');canvas.width=video.videoWidth;canvas.height=video.videoHeight;canvas.getContext('2d').drawImage(video,0,0);if(row.coverURL)URL.revokeObjectURL(row.coverURL);canvas.toBlob(blob=>{if(!blob)return;row.coverURL=URL.createObjectURL(blob);thumb.src=row.coverURL;row.video.poster=row.coverURL;row.stackImages.forEach(img=>img.src=row.coverURL);},'image/jpeg',.9);rec.data.cover_time=Number(slider.value);choose.textContent='Choose cover · '+rec.data.cover_time.toFixed(2)+'s';this.changed(rec);cover.hidden=true;choose.setAttribute('aria-expanded','false');});cover.append(video,slider,coverTime,use);choose.className='post-cover-toggle';choose.setAttribute('aria-expanded','false');controls.append(choose,cover);
    const destinationSection=el('div','post-destination');controls.append(destinationSection);
    destinationSection.append(el('h3','','Destination'));
    const platforms=el('div','post-platforms');platforms.setAttribute('role','group');platforms.setAttribute('aria-label','Destination');destinationSection.append(platforms);
    const icons={download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',youtube:'<rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 6 3-6 3z"/>',instagram:'<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><path d="M17 7h.01"/>',linkedin:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 10v7m0-10h.01M11 17v-7m0 3c0-4 6-4 6 0v4"/>'};
    rec.deliveryStatus ||= {};let destination=rec.destination||'download';const platformButtons=new Map();
    for(const [value,label] of [['download','Download'],['youtube','YouTube'],['instagram','Instagram'],['linkedin','LinkedIn']]){
      const b=button('',()=>{destination=value;rec.destination=value;updateAction();});b.className='post-platform';b.dataset.destination=value;b.setAttribute('aria-label',label);
      const icon=el('span','post-platform-icon');icon.setAttribute('aria-hidden','true');icon.innerHTML='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+icons[value]+'</svg>';
      b.append(icon,el('span','',label));platformButtons.set(value,b);platforms.append(b);
    }
    rec.timing ||= 'now';rec.scheduleDraft ||= {};let editingSchedule=false;
    const timing=el('div','post-timing');timing.setAttribute('role','group');timing.setAttribute('aria-label','YouTube timing');
    const now=button('Post now',()=>{rec.timing='now';editingSchedule=false;updateAction();});const later=button('Schedule',()=>{rec.timing='schedule';editingSchedule=true;picker.setOpen(true);picker.validate(false);updateAction();});timing.append(el('span','','Timing'),now,later);destinationSection.append(timing);
    const scheduleWrap=el('div','post-schedule');destinationSection.append(scheduleWrap);
    const picker=new window.CascadeSchedulePicker({container:scheduleWrap,draft:rec.scheduleDraft,onChange:()=>updateAction()});
    const scheduleNote=el('p','post-note','Your video uploads now and becomes public on YouTube at the selected time.');const scheduleHelp=el('p','post-note');scheduleWrap.append(scheduleNote,scheduleHelp);
    const account=el('div','post-account'),accountStatus=el('span','','Checking YouTube connection…');
    const socialBase='/api/projects/'+encodeURIComponent(this.projectId)+'/social/youtube';let connected=false,canSchedule=false,checking=false;
    const isCurrent=()=>this.openToken===token;
    const refresh=async()=>{if(checking)return;checking=true;refreshButton.disabled=true;try{const data=await this.apiJSON(socialBase);if(!isCurrent())return;connected=data.connected;canSchedule=!!data.can_schedule;accountStatus.textContent=connected?'Connected: '+data.channel:'Connect your YouTube channel.';if(connected&&!canSchedule)accountStatus.textContent+=' Reconnect to enable scheduling.';}catch(error){if(!isCurrent())return;accountStatus.textContent=error.message;}finally{checking=false;if(isCurrent()){refreshButton.disabled=false;updateAction();}}};
    const connect=button('Connect YouTube',async()=>{
      // Reserve a tab during the click, before awaiting the authenticated request.
      const popup=window.open('about:blank','_blank');if(!popup){accountStatus.textContent='Popup blocked. Allow popups for Cascade, then connect again.';return;}popup.opener=null;connect.disabled=true;
      try{const data=await this.apiJSON(socialBase+'/connect',{method:'POST'});popup.location.href=data.url;}catch(error){popup.close();if(isCurrent())accountStatus.textContent=error.message;}finally{if(isCurrent())connect.disabled=false;}
    });
    const refreshButton=button('Refresh connection',refresh);refreshButton.className='post-text-action';account.append(accountStatus,connect,refreshButton);destinationSection.append(account);
    const privacy=field('YouTube privacy','select','',100);for(const value of ['private','unlisted','public']){const option=el('option','',value[0].toUpperCase()+value.slice(1));option.value=value;privacy.append(option);}privacy.value=rec.privacy||'private';privacy.onchange=()=>{rec.privacy=privacy.value;};destinationSection.append(privacy.parentElement);
    const instagram=el('div','post-instagram'),instagramNote=el('p','post-note');instagram.append(instagramNote);
    const shareAPI=window.CascadeInstagramShare;
    const prepareShare=()=>{rec.shareFile=shareAPI.prepare(row.blob,this.filename(row));rec.shareChecked=true;rec.refreshUI?.();};
    // Preview rendering already uses the final export. Reuse that exact Blob before any share click.
    if(row.blob)prepareShare();
    const shareVideo=async()=>{
      if(rec.localBusy||!rec.shareFile)return;rec.localBusy=true;rec.deliveryStatus.instagram='Opening device share sheet…';updateAction();
      try{await shareAPI.share(rec.shareFile,[rec.data.caption,rec.data.hashtags.join(' ')].filter(Boolean).join('\n\n'));rec.deliveryStatus.instagram='Share request completed. Finish in your chosen app; Cascade cannot confirm Instagram attachment or publication.';}
      catch(error){rec.deliveryStatus.instagram=shareAPI.message(error);}
      finally{rec.localBusy=false;rec.refreshUI?.();}
    };
    const manualInstagram=button('Download & Open Instagram',()=>downloadInstagram());manualInstagram.className='post-text-action';
    const downloadInstagram=async()=>{
      if(rec.localBusy)return;rec.localBusy=true;rec.deliveryStatus.instagram='Rendering…';updateAction();
      try{const result=await shareAPI.downloadAndOpen({download:()=>this.download(row),open:url=>window.open(url,'_blank')});rec.deliveryStatus.instagram=result.message;rec.instagramReady=result.ready;}
      catch(error){rec.deliveryStatus.instagram='Download failed: '+error.message;}
      finally{rec.localBusy=false;rec.refreshUI?.();}
    };
    const copyStatus=el('p','post-note');copyStatus.setAttribute('role','status');instagram.append(button('Copy caption & hashtags',async()=>{try{await navigator.clipboard.writeText([rec.data.caption,rec.data.hashtags.join(' ')].filter(Boolean).join('\n\n'));copyStatus.textContent='Caption & hashtags copied.';}catch{copyStatus.textContent='Copy unavailable. Select and copy your caption and hashtags above.';}}),copyStatus,manualInstagram);destinationSection.append(instagram);
    const publishStatus=el('p','post-note');publishStatus.setAttribute('role','status');const view=el('a','','View on YouTube');view.target='_blank';view.rel='noopener';
    const management=el('div','post-schedule-management');
    const change=button('Change schedule',()=>{rec.timing='schedule';editingSchedule=true;if(rec.youtube?.schedule)picker.load(rec.youtube.schedule);picker.setOpen(true);updateAction();});
    const cancel=button('Cancel schedule',()=>{cancelPrompt.hidden=false;});
    const cancelPrompt=el('div','schedule-cancel-confirm');cancelPrompt.hidden=true;cancelPrompt.append(el('p','post-note','Cancel scheduled publication? The uploaded video will stay Private.'));
    const keep=button('Keep schedule',()=>{cancelPrompt.hidden=true;});
    const confirmCancel=button('Cancel & keep Private',async()=>{rec.youtubeRevision=(rec.youtubeRevision||0)+1;clearTimeout(this.pollTimer);rec.localBusy=true;updateAction();try{const data=await this.apiJSON(this.url(row)+'/publish/youtube/schedule',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({schedule:null,revision:rec.youtube.revision||0})});cancelPrompt.hidden=true;editingSchedule=false;applyStatus(data);if(data.status==='Verifying')rec.schedulePoll?.();}catch(error){rec.youtube={...rec.youtube,error:error.message};}finally{rec.localBusy=false;rec.refreshUI?.();}});
    cancelPrompt.append(keep,confirmCancel);management.append(change,cancel,cancelPrompt);destinationSection.append(management);
    const linkedinPanel=new window.CascadeLinkedInPanel({container:destinationSection,apiJSON:this.apiJSON,url:this.url,payload:this.payload,row,record:rec,projectId:this.projectId,notify:()=>rec.refreshUI?.(),isCurrent});this.linkedinPanel=linkedinPanel;
    const updateAction=()=>{
      const youtube=destination==='youtube',scheduled=rec.timing==='schedule',data=youtube?rec.youtube:null,hasVideo=!!data?.video_id;
      const needsReconnect=/reconnect|authorization expired|revoked/i.test(data?.error||'');
      const busy=!!rec.localBusy||(youtube&&['Rendering','Uploading','Processing','Verifying'].includes(data?.status));
      for(const [value,b] of platformButtons){b.setAttribute('aria-pressed',String(value===destination));b.disabled=!!rec.localBusy||!!rec.loadFailed;}
      timing.hidden=!youtube;now.setAttribute('aria-pressed',String(!scheduled));later.setAttribute('aria-pressed',String(scheduled));now.disabled=later.disabled=busy;
      scheduleWrap.hidden=!youtube||!scheduled||(hasVideo&&!editingSchedule);picker.setDisabled(busy);scheduleNote.textContent=hasVideo?'Your existing upload becomes public on YouTube at the selected time.':'Your video uploads now and becomes public on YouTube at the selected time.';scheduleHelp.textContent=hasVideo?'Changing the schedule keeps the uploaded video and post text. Choose a time at least 30 minutes from now.':'Uploads stay Private until processing finishes and YouTube confirms the schedule. Allow at least 30 minutes; long videos may need more time.';
      account.hidden=!youtube;connect.hidden=connected&&!needsReconnect&&(!scheduled||canSchedule);connect.textContent=needsReconnect?'Reconnect YouTube':connected&&scheduled&&!canSchedule?'Reconnect for scheduling':'Connect YouTube';privacy.parentElement.hidden=!youtube||scheduled;privacy.disabled=busy||!!rec.loadFailed;instagram.hidden=destination!=='instagram';
      manualInstagram.hidden=!rec.shareFile;manualInstagram.disabled=busy||!!rec.loadFailed;instagramNote.textContent=rec.shareFile?'Choose Instagram in your device’s share sheet, then Reels if offered. Finish posting in Instagram. The caption may not carry over; use Copy caption & hashtags.':'Click Create and select your downloaded clip.';
      submit.textContent=youtube?(scheduled?(hasVideo?'Save schedule':'Schedule on YouTube'):'Publish'):destination==='instagram'?(rec.shareFile?'Share video…':shareAPI.available()&&!rec.shareChecked?'Preparing video…':'Download & Open Instagram'):'Download MP4';
      linkedinPanel.setActive(destination==='linkedin');publishStatus.hidden=destination==='linkedin';
      submit.hidden=destination==='linkedin'||(youtube&&hasVideo&&!editingSchedule);
      submit.disabled=busy||!!rec.loadFailed||(destination==='instagram'&&shareAPI.available()&&!rec.shareChecked)||(youtube&&(!connected||(data?.upload_attempted&&!hasVideo)||(scheduled&&(!canSchedule||!picker.valid))||(!scheduled&&(hasVideo||data?.status==='Published'))));
      const confirmed=data?.status==='Scheduled'&&data.schedule;
      publishStatus.textContent=youtube?(confirmed?'Scheduled for '+window.CascadeScheduleTime.format(data.schedule)+'.':data?.status==='Ready'?'':data?.status||'')+(data?.error?': '+data.error:'')+(data?.message?' '+data.message:''):(rec.deliveryStatus[destination]||'');
      view.hidden=!youtube||!data?.url;if(data?.url)view.href=data.url;
      management.hidden=!youtube||!hasVideo;change.hidden=!!data?.ever_public||data?.status==='Published';change.textContent=data?.schedule?'Change schedule':'Schedule this upload';change.disabled=cancel.disabled=busy||!canSchedule;cancel.hidden=!data?.schedule&&!data?.pending_change;keep.disabled=confirmCancel.disabled=!!rec.localBusy;
    };
    const applyStatus=data=>{rec.youtube=data;if(data.schedule&&!rec.scheduleHydrated){picker.load(data.schedule);rec.scheduleHydrated=true;rec.timing='schedule';}if(['Scheduled','Private','Processing'].includes(data.status))editingSchedule=false;if(data.status==='Failed')rec.submissionId=null;rec.refreshUI?.();};
    const poll=async()=>{const revision=rec.youtubeRevision||0;try{const data=await this.apiJSON(this.url(row)+'/publish/youtube');if(!isCurrent()||revision!==(rec.youtubeRevision||0))return;applyStatus(data);if(['Rendering','Uploading','Processing','Verifying'].includes(data.status))this.pollTimer=setTimeout(poll,3000);}catch(error){if(!isCurrent()||revision!==(rec.youtubeRevision||0))return;rec.youtube={...rec.youtube,error:'Status unavailable: '+error.message};updateAction();this.pollTimer=setTimeout(poll,5000);}};
    const submit=button('Download MP4',async()=>{
      if(submit.disabled)return;if(destination==='instagram'){if(rec.shareFile)return shareVideo();return downloadInstagram();}const target=destination;
      rec.localBusy=true;rec.deliveryStatus[target]='Rendering…';updateAction();
      try{
        if(target!=='youtube'){
          await this.download(row);rec.deliveryStatus[target]='MP4 download started.';

        }else{
          const scheduled=rec.timing==='schedule';let schedule=null;
          if(scheduled){if(!picker.validate(false)){updateAction();return;}schedule=structuredClone(picker.value);}
          const description=[rec.data.caption,rec.data.hashtags.join(' ')].filter(Boolean).join('\n\n');if(!name.value.trim()||name.value.length>100||description.length>5000)throw Error('YouTube requires a title of 1–100 characters and a description of at most 5,000 characters including hashtags.');
          rec.youtubeRevision=(rec.youtubeRevision||0)+1;
          if(rec.youtube?.video_id){
            if(!scheduled)throw Error('This clip is already uploaded. Use Change schedule or Cancel schedule.');
            const data=await this.apiJSON(this.url(row)+'/publish/youtube/schedule',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({schedule,revision:rec.youtube.revision||0})});applyStatus(data);if(data.status==='Verifying')rec.schedulePoll?.();
          }else{
            // Snapshot post copy and settings at the explicit click, before waiting for edit preparation.
            const snapshot={title:rec.data.name,description,hashtags:[...rec.data.hashtags],privacy:scheduled?'private':privacy.value,schedule};
            const edit=await this.payload(row);if(!isCurrent())return;
            rec.submissionId ||= crypto.randomUUID();rec.youtube={status:'Rendering'};updateAction();
            const data=await this.apiJSON(this.url(row)+'/publish/youtube',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...snapshot,submission_id:rec.submissionId,edit})});applyStatus(data);
            if(['Rendering','Uploading','Processing','Verifying'].includes(data.status))rec.schedulePoll?.();
          }
        }
      }catch(error){if(target==='youtube')rec.youtube={...rec.youtube,status:rec.youtube?.video_id?rec.youtube.status:'Failed',error:error.message};else rec.deliveryStatus[target]='Download failed: '+error.message;if(target==='youtube'&&rec.timing==='schedule'&&/time|timezone|clocks|minutes|buffer/i.test(error.message)){editingSchedule=true;picker.timeError.textContent=error.message;}}
      finally{rec.localBusy=false;rec.refreshUI?.();}
    });
    const openInstagram=el('a','post-instagram-link','Open Instagram');openInstagram.href='https://www.instagram.com/';openInstagram.target='_blank';openInstagram.rel='noopener';openInstagram.hidden=!rec.instagramReady;instagram.append(openInstagram);
    rec.refreshUI=()=>{if(isCurrent()){openInstagram.hidden=!rec.instagramReady;updateAction();}};rec.schedulePoll=()=>{if(isCurrent()){clearTimeout(this.pollTimer);this.pollTimer=setTimeout(poll,2000);}};
    destinationSection.append(submit,publishStatus,view);updateAction();refresh();poll();
    const saving=el('div','post-saving');this.saveLabel=el('span');this.saveLabel.setAttribute('role','status');this.retry=button('Retry',async()=>{if(rec.loadFailed){this.records.delete(this.key(row));this.open(row,anchor);}else this.save(rec);});saving.append(this.saveLabel,this.retry);controls.append(saving);this.status(rec);
    if(rec.loadFailed)this.section.querySelectorAll('button').forEach(b=>{if(![header.lastChild,this.retry].includes(b))b.disabled=true;});
    this.section.hidden=false;this.section.classList.remove('post-enter');void this.section.offsetWidth;this.section.classList.add('post-enter');heading.focus({preventScroll:true});loadPreview();requestAnimationFrame(()=>{if(scroll&&this.openToken===token)this.section.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});});
  }
  close(focus=true){this.linkedinPanel?.destroy();clearTimeout(this.pollTimer);this.openToken=null;if(!this.current)return;clearTimeout(this.current.timer);if(this.current.saved<this.current.revision)this.save(this.current);this.section.querySelectorAll('video').forEach(v=>{v.pause();v.removeAttribute('src');v.load();});this.section.hidden=true;this.anchor?.setAttribute('aria-expanded','false');this.current=null;if(focus)this.anchor?.focus({preventScroll:true});}
  destroy(){this.close(false);document.removeEventListener('play',this.playHandler,true);this.section.remove();for(const rec of this.records.values())if(rec.row.coverURL)URL.revokeObjectURL(rec.row.coverURL);}
};
