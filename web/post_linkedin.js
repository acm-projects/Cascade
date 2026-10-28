/* Personal-profile LinkedIn controls. Preview and editable post copy remain shared. */
window.CascadeLinkedInPanel=class {
  constructor({container,apiJSON,url,payload,row,record,projectId,notify,isCurrent}){
    Object.assign(this,{apiJSON,url,payload,row,record,projectId,notify,isCurrent});this.connected=false;this.configured=false;this.ended=false;this.active=false;
    const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text)node.textContent=text;return node;};
    const button=(text,fn)=>{const node=el('button','',text);node.type='button';node.onclick=fn;return node;};
    this.root=el('div','post-linkedin');this.root.hidden=true;container.append(this.root);
    const account=el('div','post-account');this.identity=el('span','','Checking LinkedIn connection…');this.connect=button('Connect LinkedIn',()=>this.connectAccount());this.refresh=button('Refresh connection',()=>this.loadAccount());this.refresh.className='post-text-action';account.append(this.identity,this.connect,this.refresh);
    const note=el('p','post-note','Posts publicly to your connected personal LinkedIn profile. Company Pages and scheduling are not supported.');
    this.publish=button('Publish to LinkedIn',()=>this.submit());this.publish.className='post-linkedin-publish';
    this.status=el('p','post-note');this.status.setAttribute('role','status');this.link=el('a','','View on LinkedIn');this.link.target='_blank';this.link.rel='noopener';this.link.hidden=true;
    this.root.append(account,note,this.publish,this.status,this.link);this.draw();
  }
  current(){return !this.ended&&this.isCurrent();}
  setActive(active){this.active=active;this.root.hidden=!active;if(active&&!this.loaded){this.loaded=true;this.loadAccount();this.poll();}this.draw();}
  draw(){
    const rec=this.record,data=rec.linkedin,busy=!!rec.localBusy||['Rendering','Uploading','Processing','Publishing'].includes(data?.status);
    const reconnect=/reconnect|expired|revoked|profile changed/i.test(data?.error||'');
    this.connect.hidden=this.connected&&!reconnect;this.connect.disabled=!!rec.localBusy||!!this.connecting||!this.configured;
    this.connect.textContent=reconnect?'Reconnect LinkedIn':'Connect LinkedIn';this.refresh.disabled=!!rec.localBusy;
    this.publish.disabled=!this.connected||!this.configured||!!rec.loadFailed||busy||data?.status==='Published'||!!data?.video||!!data?.post_attempted;
    this.status.textContent=(data?.status&&data.status!=='Ready'?data.status:'')+(data?.error?': '+data.error:'');this.link.hidden=!data?.url;if(data?.url)this.link.href=data.url;
  }
  async loadAccount(){
    if(this.loading)return;this.loading=true;this.refresh.disabled=true;
    try{const data=await this.apiJSON('/api/projects/'+encodeURIComponent(this.projectId)+'/social/linkedin');if(!this.current())return;this.connected=!!data.connected;this.configured=!!data.configured;this.identity.textContent=data.connected?'Connected: '+data.profile:data.error||'Connect your personal LinkedIn profile.';}
    catch(error){if(this.current()){this.connected=false;this.identity.textContent=error.message;}}
    finally{this.loading=false;if(this.current())this.draw();}
  }
  async connectAccount(){
    if(this.connect.disabled)return;const popup=window.open('about:blank','_blank');if(!popup){this.identity.textContent='Popup blocked. Allow popups for Cascade, then connect LinkedIn again.';return;}popup.opener=null;this.connecting=true;this.connect.disabled=true;
    try{const data=await this.apiJSON('/api/projects/'+encodeURIComponent(this.projectId)+'/social/linkedin/connect',{method:'POST'});popup.location.href=data.url;}
    catch(error){popup.close();if(this.current())this.identity.textContent=error.message;}
    finally{this.connecting=false;if(this.current())this.draw();}
  }
  async poll(){
    clearTimeout(this.timer);const revision=this.revision||0;try{const data=await this.apiJSON(this.url(this.row)+'/publish/linkedin');if(!this.current()||revision!==(this.revision||0))return;this.record.linkedin=data;this.draw();if(['Rendering','Uploading','Processing','Publishing'].includes(data.status))this.timer=setTimeout(()=>this.poll(),2500);}
    catch(error){if(!this.current())return;this.status.textContent='Status unavailable: '+error.message;this.timer=setTimeout(()=>this.poll(),5000);}
  }
  async submit(){
    if(this.publish.disabled)return;this.revision=(this.revision||0)+1;const rec=this.record;rec.localBusy=true;this.notify();this.draw();clearTimeout(this.timer);
    try{
      const snapshot={title:rec.data.name,caption:rec.data.caption,hashtags:[...rec.data.hashtags]};
      if(!snapshot.title.trim())throw Error('Enter a title for the LinkedIn video.');
      const combined=[snapshot.caption,snapshot.hashtags.join(' ')].filter(Boolean).join('\n\n');if(combined.length>3000)throw Error('LinkedIn caption and hashtags together must be at most 3,000 characters.');
      const edit=await this.payload(this.row);if(!this.current())return;
      rec.linkedinSubmission ||= crypto.randomUUID();
      const data=await this.apiJSON(this.url(this.row)+'/publish/linkedin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...snapshot,edit,submission_id:rec.linkedinSubmission})});rec.linkedin=data;
      if(data.status==='Failed'&&!data.video&&!data.post_attempted)rec.linkedinSubmission=null;
      if(this.current()&&['Rendering','Uploading','Processing','Publishing'].includes(data.status))this.timer=setTimeout(()=>this.poll(),2000);
    }catch(error){rec.linkedin={...rec.linkedin,error:error.message};}
    finally{rec.localBusy=false;this.notify();if(this.current())this.draw();}
  }
  destroy(){this.ended=true;clearTimeout(this.timer);}
};
