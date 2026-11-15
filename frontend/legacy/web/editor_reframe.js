/* Shared automatic framing preparation for editor previews and Exports. */
window.CascadeAutoFrame={
  needed(state,info){const g=window.CascadeEditorState.compositionGeometry(info.width,info.height,state.composition);return state.composition.mode==='fill'&&(g.scaledWidth>g.width||g.scaledHeight>g.height);},
  async prepare(state,{info,url,apiJSON,status=()=>{},verify=()=>{}}){
    state.reframe.enabled=this.needed(state,info);
    if(!state.reframe.enabled){status('The entire source fits. No tracking crop is needed.');return state;}
    state.composition.x=state.composition.y=.5;
    {status('Checking cached tracking…');const job=await apiJSON(url+'/reframe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({composition:state.composition,focus:state.reframe.focus,selection:state.reframe.selection})});verify();state.reframe.analysis_id=job.analysis_id;}
    for(let attempt=0;attempt<2400;attempt++){
      verify();const job=await apiJSON(url+'/reframe/'+state.reframe.analysis_id);verify();
      status(job.message+' '+Math.round(job.progress*100)+'%');
      if(job.status==='error')throw Error(job.message);
      if(job.status==='ready'){if(job.version!==3){state.reframe.analysis_id=null;return this.prepare(state,{info,url,apiJSON,status,verify});}return state;}
      await new Promise(resolve=>setTimeout(resolve,750));
    }
    throw Error('Automatic framing is taking too long. Retry when analysis finishes.');
  }
};
window.CascadeReframe=class {
  constructor({get,apiJSON,commit,lock,render}) {
    Object.assign(this,{get,apiJSON,commit,lock,render});this.cache=new Map();this.pending=new Map();this.generation=0;
    this.$=id=>document.getElementById(id);
    this.$('reframe-focus').onchange=()=>this.change({focus:this.$('reframe-focus').value,selection:null,analysis_id:null});
    this.$('subject-reset').onclick=()=>this.change({focus:'auto',selection:null,analysis_id:null});
    this.$('reframe-retry').onclick=()=>this.change({analysis_id:null});
    this.$('reframe-cancel').onclick=()=>{this.generation++;this.status('Analysis paused in this view. Retry to prepare automatic framing.');};
    window.addEventListener('cascade:session-ended',()=>{this.generation++;});
  }
  status(message){this.$('reframe-status').textContent=message;const feedback=this.$('auto-framing-status');if(feedback)feedback.textContent=message.includes('entire source fits')?'':message;}
  failure(error){this.error='Automatic framing unavailable: '+error.message+' Retry analysis or use Fit.';this.status(this.error);}
  key(state){return JSON.stringify([this.get().current?.key,state.reframe.analysis_id,state.reframe.focus,state.reframe.selection,state.composition]);}
  ready(state){return !window.CascadeAutoFrame.needed(state,this.get().info)||this.cache.has(this.key(state));}
  async prepare(state) {
    this.error=null;const generation=this.generation,current=this.get().current;
    const verify=()=>{if(generation!==this.generation||current!==this.get().current)throw Error('Tracking operation cancelled.');};
    this.preparing=true;this.$('reframe-cancel').hidden=false;this.$('reframe-cancel').disabled=false;
    if(this.$('editor-video').readyState>=2){this.$('preview-play').disabled=false;this.$('play-toggle').disabled=false;}
    try{
      await window.CascadeAutoFrame.prepare(state,{info:this.get().info,url:current.url,apiJSON:this.apiJSON,status:m=>this.status(m),verify});
      if(state.reframe.enabled){await this.ensure(state);verify();}
      return state;
    }finally{this.preparing=false;this.$('reframe-cancel').hidden=true;}
  }
  async ensure(state){
    const key=this.key(state);if(this.cache.has(key))return this.cache.get(key);
    if(this.pending.has(key))return this.pending.get(key);
    const current=this.get().current;
    const pending=this.apiJSON(current.url+'/reframe/'+state.reframe.analysis_id+'/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({composition:state.composition,focus:state.reframe.focus,selection:state.reframe.selection})}).then(plan=>{this.cache.set(key,plan);return plan;}).finally(()=>this.pending.delete(key));
    this.pending.set(key,pending);return pending;
  }
  selectRegion(selection){return this.change({selection,analysis_id:null});}
  async change(patch){
    const {state}=this.get();if(!state||this.busy)return;
    const next=window.CascadeEditorState.clone(state);Object.assign(next.reframe,patch);
    this.busy=true;this.lock(true);
    try{await this.prepare(next);this.commit(next);return true;}
    catch(error){this.failure(error);return false;}
    finally{this.busy=false;this.lock(false);this.render();}
  }
  sync(state,locked){
    const needed=window.CascadeAutoFrame.needed(state,this.get().info);
    this.$('subject-pick').disabled=locked||this.busy;this.$('subject-reset').disabled=locked||this.busy;
    this.$('reframe-focus').value=state.reframe.focus;this.$('reframe-focus').disabled=locked||this.busy||!needed;
    this.$('reframe-retry').disabled=locked||this.busy||!needed;
    if(this.error){this.status(this.error);return;}
    if(!needed){this.status('The entire source fits. No tracking crop is needed.');return;}
    const plan=this.cache.get(this.key(state));
    if(plan&&!this.busy)this.status('Automatic framing ready. '+plan.warning);
  }
  geometry(state,time,g){
    if(!state.reframe.enabled||!window.CascadeAutoFrame.needed(state,this.get().info))return g;
    const plan=this.cache.get(this.key(state));if(!plan)return g;
    const p=window.CascadeEditorState.reframeAt(plan.points,time);
    return {...g,x:2*Math.floor((g.scaledWidth-g.width)*p.x/2+.5),y:2*Math.floor((g.scaledHeight-g.height)*p.y/2+.5)};
  }
  reset(){this.generation++;this.cache.clear();this.error=null;this.status('');}
};
