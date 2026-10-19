/* DOM adapter tests, not a replacement for real browser playback testing. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const state = require('../web/editor_state.js');
class Element {
  constructor(tag='div', id='') { this.tagName=tag.toUpperCase(); this.id=id; this.children=[]; this.dataset={}; this.style={}; this.listeners={}; this.value=''; this.type=''; this.classList={toggle(){}}; this.clientWidth=640; this.clientHeight=320; this.paused=true; this.currentTime=0; this.readyState=1; }
  append(...els) { this.children.push(...els); }
  replaceChildren() { this.children=[]; }
  setAttribute() {}
  addEventListener(name,fn) { (this.listeners[name] ||= []).push(fn); }
  fire(name) { for(const fn of this.listeners[name]||[]) fn({target:this}); }
  checkValidity() { return true; }
  pause() { this.paused=true; }
  async play() { this.paused=false; this.fire('play'); }
  closest(selector) { if(selector.includes('textarea') && this.tagName==='TEXTAREA') return this; return null; }
}
const defaults = {enabled:true,font:'Arial',size:32,color:'#ffffff',stroke:'#000000',thickness:2,background:'#000000',opacity:0,position:'bottom',bold:false};
const drafts=new Map(), storage=new Map();
let failSave=false, failMedia=false;
const calls=[];
const key=url=>url.split('/').slice(5,7).join('/');
const responseDraft = id => state.clone(drafts.get(id) || {state:{start:0,end:12,captions:defaults},chat:[],updated_at:0});
async function apiJSON(url, options={}) {
 calls.push([url,options.method||'GET']);
 if(url.endsWith('/editor')) return {sessions:[{job_id:'job1',clips:[{}]},{job_id:'job2',clips:[{},{},{},{},{}]}],selection:null};
 if(options.method==='PUT') { if(failSave) throw Error('Save unavailable'); drafts.set(key(url),JSON.parse(options.body)); return {saved:true}; }
 if(url.endsWith('/chat')) { const data=JSON.parse(options.body); const next=state.clone(data.state); next.start+=2; next.captions.color='#ffff00'; return {state:next,message:'Trimmed two seconds; captions yellow.'}; }
 return {duration:12,width:1280,height:720,cues:[{start:0,end:12,text:'Caption'}],warning:'',draft:responseDraft(key(url))};
}
function setup(search='?project=p') {
 const markup = require('node:child_process').execFileSync('python3',['-c',"from pathlib import Path; from backend.frontend import render_page; print(render_page('editor_C.html',Path('web')),end='')"],{encoding:'utf8'});
 const ids = [...markup.matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
 const elements = Object.fromEntries(ids.map(id=>[id,new Element('div',id)]));
 for(const name of Object.keys(defaults)) { const e=elements['cap-'+name]; e.tagName='INPUT'; e.type=['enabled','bold'].includes(name)?'checkbox':name==='opacity'?'range':['size','thickness'].includes(name)?'number':'text'; }
 for(const id of ['seek','trim-start','trim-end']) Object.assign(elements[id],{tagName:'INPUT',type:'range'});
 elements['chat-input'].tagName='TEXTAREA';
 const docListeners={};
 const document={body:{},hidden:false,getElementById:id=>elements[id], createElement:tag=>new Element(tag),addEventListener:(name,fn)=>docListeners[name]=fn,
 querySelectorAll(selector) {
   if(selector==='[data-tab]' || selector==='.tab-panel' || selector.startsWith('a[')) return [];
   if(selector==='#editor-sessions button') return elements['editor-sessions'].children.flatMap(s=>s.children.filter(e=>e.tagName==='BUTTON'));
   return Object.values(elements).filter(e=>['INPUT','BUTTON','SELECT'].includes(e.tagName));
 }};
 const location={search,href:'http://localhost/editor_C.html'+search};
 const window={CascadeEditorState:state,CascadeTimeline:class {setDisabled(){} update(){} setClip(){}},CascadeCaptions:{draw(){},exportFrames(){return[];}},history:{replaceState(a,b,url){location.href=url.href;}},addEventListener(){}};
 const timers=new Map(); let timer=0;
 const context={window,document,location,console,URL,URLSearchParams,ResizeObserver:class {observe(){}},requestAnimationFrame:()=>1,cancelAnimationFrame(){},setTimeout:fn=>{timers.set(++timer,fn);return timer;},clearTimeout:id=>timers.delete(id)};
 vm.runInNewContext(fs.readFileSync('web/editor_C.js','utf8'),context);
 return {elements,document,docListeners,window,apiFetch:async()=>{if(failMedia)throw Error('Media missing');return {blob:async()=>new Blob(['video'])};}, timers};
}
async function initialize(ctx) {
 await ctx.window.CascadeEditor.initialize({project:{id:'p',name:'Project'},userId:'u',apiJSON,apiFetch:ctx.apiFetch,setStatus:msg=>ctx.elements.status.textContent=msg,initializeResearch:async()=>{}});
}
global.localStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)};
// VM has an explicit localStorage binding so no real browser/session is used.
const originalRun=vm.runInNewContext;
vm.runInNewContext=(code,context)=>originalRun(code,{...context,localStorage:global.localStorage,Blob});
async function main() {
 const ctx=setup(); await initialize(ctx); const e=ctx.elements;
 assert.equal(e['editor-clip-title'].textContent,'Session 1 · Clip 1');
 const clips=ctx.document.querySelectorAll('#editor-sessions button'); assert.equal(clips.length,6);
 // One range gesture, undo and redo while range has focus.
 e['trim-start'].value=1; e['trim-start'].fire('pointerdown'); e['trim-start'].fire('input'); e['trim-start'].value=2; e['trim-start'].fire('input'); e['trim-start'].fire('change');
 assert.equal(Number(e['trim-start'].value),2);
 ctx.docListeners.keydown({target:e['trim-start'],ctrlKey:true,key:'z',preventDefault(){}});
 assert.equal(Number(e['trim-start'].value),0);
 e.redo.onclick(); assert.equal(Number(e['trim-start'].value),2);
 await clips[5].onclick(); assert.equal(e['editor-clip-title'].textContent,'Session 2 · Clip 5');
 assert.equal(Number(e['trim-start'].value),0);
 e['chat-input'].value='Trim two seconds and make captions yellow';
 await e['chat-form'].onsubmit({preventDefault(){}});
 assert.equal(Number(e['trim-start'].value),2); assert.equal(e['cap-color'].value,'#ffff00');
 e.undo.onclick(); assert.equal(Number(e['trim-start'].value),0); assert.equal(e['cap-color'].value,'#ffffff');
 await clips[0].onclick(); assert.equal(Number(e['trim-start'].value),2);
 // Ordinary textarea undo is untouched.
 let prevented=false;ctx.docListeners.keydown({target:e['chat-input'],ctrlKey:true,key:'z',preventDefault(){prevented=true;}});assert.equal(prevented,false);
 failSave=true; await e['retry-save'].onclick(); assert.equal(e['save-status'].textContent,'Could not save — retry');
 await clips[1].onclick(); assert.equal(e['editor-clip-title'].textContent,'Session 1 · Clip 1');
 failSave=false; await e['retry-save'].onclick(); assert.equal(e['save-status'].textContent,'Saved');
 const reloaded=setup(); await initialize(reloaded); assert.equal(Number(reloaded.elements['trim-start'].value),2);
 // Missing media still allows choosing a different sidebar item.
 failMedia=true; const missing=setup(); await initialize(missing);
 const missingClips=missing.document.querySelectorAll('#editor-sessions button'); assert.equal(missingClips[0].disabled,false);
 failMedia=false; await missingClips[1].onclick(); assert.equal(missing.elements['editor-clip-title'].textContent,'Session 2 · Clip 1');
 console.log('Editor DOM adapter checks passed: selection, gestures, AI undo, restore, save failure, missing media');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
