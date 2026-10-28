"""Isolated Chrome fixture checks for posting metadata and the in-flow preparation section. No paid AI calls."""
import asyncio,base64,json,urllib.request,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_editor_browser import Chrome
import websockets
async def main():
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None) as ws:
  c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable')
  await c.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':'/tmp/cascade-post-downloads'})
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':"if(location.origin==='http://127.0.0.1:8767')localStorage.setItem('cascade-export-selection:v1:editor-browser-user:'+ 'd'.repeat(32),JSON.stringify([{job_id:'a'.repeat(32),clip_index:0},...[0,1,2].map(clip_index=>({job_id:'b'.repeat(32),clip_index}))]));"})
  await c.call('Storage.clearDataForOrigin',{'origin':'http://127.0.0.1:8767','storageTypes':'local_storage'})
  await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':"Object.defineProperty(window,'CascadePostPreparation',{configurable:true,set(value){Object.defineProperty(window,'CascadePostPreparation',{configurable:true,writable:true,value:class extends value{constructor(options){super(options);window.testPostPreparation=this;}}});}});"})
  url='http://127.0.0.1:8767/__exports_test/exports?project='+'d'*32
  await c.call('Page.navigate',{'url':url});await c.until('!!window.siteReady');await c.js('window.siteReady');c.errors=[]
  await c.until("[...document.querySelectorAll('.export-media-card video')].every(v=>v.readyState>=2)",45)
  await c.click('.wave-toggle');await asyncio.sleep(.8)
  await c.click('.prepare-post');await c.until("!document.querySelector('.post-section').hidden")
  assert await c.js("document.querySelectorAll('.export-card-check:checked').length===4&&document.querySelector('.wave-album').dataset.expanded==='true'")
  await c.until("document.querySelector('.post-preview video').readyState>=2")
  assert await c.js("(()=>{const s=document.querySelector('.post-section'),g=document.querySelector('#export-deck'),p=document.querySelector('.post-preview'),c=document.querySelector('.post-controls');return getComputedStyle(s).position==='static'&&s.offsetTop>=g.offsetTop+g.offsetHeight&&c.getBoundingClientRect().left>p.getBoundingClientRect().left&&document.querySelector('.exports-footer').getBoundingClientRect().top>s.getBoundingClientRect().bottom;})()")
  await c.js("document.querySelector('.post-preview video').play()")
  await c.until("!document.querySelector('.post-preview video').paused")
  def downloads():return {p.name:(p.stat().st_mtime_ns,p.stat().st_size) for p in Path('/tmp/cascade-post-downloads').glob('*.mp4')}
  before=downloads()
  await c.js("[...document.querySelectorAll('.post-controls button')].find(b=>b.textContent==='Download MP4').click()")
  for _ in range(100):
   if downloads()!=before:break
   await asyncio.sleep(.1)
  assert downloads()!=before,'Posting download missing'
  await c.js("document.querySelector('.post-preview video').pause()")
  await c.js("(()=>{let e=document.querySelector('.post-field input');e.value='A moment worth sharing';e.dispatchEvent(new Event('input'));let t=document.querySelector('.post-field textarea');t.value='A fresh perspective, one clip at a time.';t.dispatchEvent(new Event('input'));let h=document.querySelector('[aria-label=\"New hashtag\"]');h.value='Cascade';h.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()")
  await c.until("document.querySelector('.post-saving span').textContent==='Saved'")
  # A failed save retains edits locally and Retry recovers without a render.
  await c.js("window.postOriginalFetch=window.fetch;window.postExportRequests=0;window.fetch=(url,options={})=>{if(String(url).endsWith('/export'))window.postExportRequests++;if(String(url).endsWith('/post')&&options.method==='PUT')return Promise.resolve(new Response(JSON.stringify({detail:'Fixture save failure'}),{status:503,headers:{'Content-Type':'application/json'}}));return window.postOriginalFetch(url,options);}")
  await c.js("(()=>{const t=document.querySelector('.post-field textarea');t.value+='';t.dispatchEvent(new Event('input'));})()")
  await c.until("document.querySelector('.post-saving span').textContent.startsWith('Not saved:')")
  await c.js("window.fetch=window.postOriginalFetch;document.querySelector('.post-saving button').click()")
  await c.until("document.querySelector('.post-saving span').textContent==='Saved'")
  assert await c.js('window.postExportRequests===0')
  # The form is manual, and destination settings stay scoped to their platform.
  assert await c.js("!document.querySelector('#export-youtube')&&document.querySelectorAll('.export-actions button').length===2")
  assert await c.js("!['Generate caption','Rewrite','Suggest tags','Copy post text'].some(text=>[...document.querySelectorAll('.post-controls button')].some(b=>b.textContent===text))")
  assert await c.js("document.querySelectorAll('.post-platform').length===4&&!document.querySelector('[data-destination=linkedin]').disabled&&document.querySelector('.post-timing button').getAttribute('aria-pressed')==='true'&&!document.querySelectorAll('.post-timing button')[1].disabled&&document.querySelector('.post-timing').hidden")
  await c.js("document.querySelector('[data-destination=youtube]').click()")
  await c.until("document.querySelector('.post-account').textContent.includes('Connect your YouTube channel.')")
  assert await c.js("!document.querySelector('.post-account').hidden&&document.querySelector('.post-field select').value==='private'&&document.querySelector('.post-destination>button').disabled")
  # Fixture responses exercise connected, publishing and result UI without a real upload.
  await c.js("window.youtubePosts=[];window.fetch=(url,options={})=>{if(String(url).endsWith('/social/youtube'))return Promise.resolve(new Response(JSON.stringify({connected:true,channel:'Fixture channel'})));if(String(url).endsWith('/publish/youtube')){if(options.method==='POST'){window.youtubePosts.push({url:String(url),body:JSON.parse(options.body)});return Promise.resolve(new Response(JSON.stringify({status:'Processing'})));}return Promise.resolve(new Response(JSON.stringify(window.youtubePosts.length?{status:'Published',url:'https://www.youtube.com/watch?v=fixture'}:{status:'Ready'})));}return window.postOriginalFetch(url,options);};[...document.querySelectorAll('.post-account button')].find(b=>b.textContent==='Refresh connection').click()")
  await c.until("document.querySelector('.post-account').textContent.includes('Fixture channel')")
  assert await c.js("[...document.querySelectorAll('.post-account button')].find(b=>b.textContent==='Connect YouTube').hidden")
  await c.js("document.querySelector('.post-destination>button').click();document.querySelector('.post-destination>button').click()")
  await c.until("document.querySelector('.post-destination>p').textContent==='Published'",10)
  assert await c.js("window.youtubePosts.length===1&&window.youtubePosts[0].body.title==='A moment worth sharing'&&window.youtubePosts[0].body.privacy==='private'&&!document.querySelector('.post-destination>a').hidden")
  await c.js("document.querySelector('[data-destination=instagram]').click()")
  assert await c.js("document.querySelector('.post-account').hidden&&document.querySelector('.post-field select').parentElement.hidden&&document.querySelector('.post-destination>a').hidden&&!document.querySelector('.post-instagram').hidden")
  # Clipboard contents belong to this displayed clip; no subtitle text is copied.
  await c.js("window.copiedPost='';Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copiedPost=text;}}});document.querySelector('.post-instagram button').click()")
  await c.until("window.copiedPost==='A fresh perspective, one clip at a time.\\n\\n#Cascade'")
  # A blocked popup still downloads and gives an explicit fallback link.
  before=downloads()
  await c.js("window.nativePostOpen=window.open;window.open=()=>null;document.querySelector('.post-destination>button').click()")
  await c.until("document.querySelector('.post-destination>p').textContent.includes('popup was blocked')")
  assert await c.js("!document.querySelector('.post-instagram-link').hidden")
  for _ in range(100):
   if downloads()!=before:break
   await asyncio.sleep(.1)
  assert downloads()!=before,'Instagram MP4 download missing'
  # Successful handoff opens Instagram after the download starts.
  await c.js("window.open=window.nativePostOpen;document.querySelector('.post-destination>button').click()")
  await c.until("document.querySelector('.post-destination>p').textContent.includes('MP4 download started. Click Create')")
  for _ in range(100):
   targets=(await c.call('Target.getTargets'))['targetInfos']
   if any(t['url'].startswith('https://www.instagram.com/') for t in targets):break
   await asyncio.sleep(.1)
  assert any(t['url'].startswith('https://www.instagram.com/') for t in targets),targets
  for t in targets:
   if t['url'].startswith('https://www.instagram.com/'):await c.call('Target.closeTarget',{'targetId':t['targetId']})
  # A failed final download never opens Instagram or reports success.
  await c.js("window.postRealDownload=window.CascadePostPreparation.prototype.download;window.downloadNativeOpen=window.open;window.popupClosed=false;window.open=()=>({opener:null,closed:false,location:{href:''},close(){window.popupClosed=true;}});window.postOriginalDownload=window.testPostPreparation.download;window.testPostPreparation.download=async()=>{throw Error('Fixture render failure');};document.querySelector('.post-destination>button').click()")
  await c.until("document.querySelector('.post-destination>p').textContent.includes('Download failed: Fixture render failure')")
  assert await c.js('window.popupClosed')
  await c.js("window.testPostPreparation.download=window.postOriginalDownload;window.open=window.downloadNativeOpen;window.fetch=window.postOriginalFetch;document.querySelector('[data-destination=download]').click()")
  async def shot(name):
   await c.until("document.querySelector('.post-preview video').readyState>=3")
   await c.js("document.querySelector('.post-preview video').currentTime=.04")
   await c.until("!document.querySelector('.post-preview video').seeking")
   await asyncio.sleep(.7)
   result=await c.call('Page.captureScreenshot',{'format':'png'});Path('/tmp/cascade-post-'+name+'.png').write_bytes(base64.b64decode(result['data']))
  await shot('desktop')
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape'});assert await c.js("document.querySelector('.post-section').hidden&&document.querySelector('.wave-album').dataset.expanded==='true'")
  await c.js("document.querySelector('.prepare-post').click()");await c.until("!document.querySelector('.post-section').hidden")
  await c.js("document.querySelector('#export-next').click()");await c.until("!document.querySelector('.post-section').hidden")
  assert await c.js("document.querySelector('.post-field input').value!=='A moment worth sharing'")
  await c.until("document.querySelector('.post-preview video').readyState>=2")
  assert await c.js("document.querySelectorAll('.post-section').length===1&&document.querySelector('.post-preview video').src===document.querySelectorAll('.export-media-card video')[1].src")
  await c.js("document.querySelector('#export-prev').click()");await asyncio.sleep(.2)
  assert await c.js("document.querySelector('.post-field input').value==='A moment worth sharing'")
  await c.js("document.querySelector('.post-header button').click()")
  await c.call('Page.reload');await c.until('!!window.siteReady');await c.js('window.siteReady');await c.click('.wave-toggle');await asyncio.sleep(.8);await c.click('.prepare-post');await c.until("!document.querySelector('.post-section').hidden")
  assert await c.js("document.querySelector('.post-field input').value==='A moment worth sharing'")
  await c.js("[...document.querySelectorAll('.post-section button')].find(b=>b.textContent.startsWith('Choose cover')).click()")
  await c.until("document.querySelector('.post-cover video').readyState>=2")
  await c.js("(()=>{const s=document.querySelector('.post-cover input');s.value='2';s.dispatchEvent(new Event('input'));})()")
  await c.until("!document.querySelector('.post-cover video').seeking")
  await c.js("[...document.querySelectorAll('.post-section button')].find(b=>b.textContent==='Use this frame').click()")
  await c.until("document.querySelector('.post-saving span').textContent==='Saved'")
  await c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
  await asyncio.sleep(.5);await c.js("document.querySelector('.post-section').scrollIntoView({block:'start',behavior:'instant'})");await shot('mobile')
  assert await c.js("document.querySelector('.post-section').getBoundingClientRect().right<=innerWidth&&document.documentElement.scrollWidth<=innerWidth")
  await c.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':2,'y':130,'button':'left','clickCount':1})
  await c.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':2,'y':130,'button':'left','clickCount':1})
  assert await c.js("!document.querySelector('.post-section').hidden")
  assert await c.js("document.querySelector('.post-controls').getBoundingClientRect().top>=document.querySelector('.post-preview').getBoundingClientRect().bottom")
  await c.js("document.querySelector('.post-header button').click()")
  await c.js("document.querySelector('.export-card-check').click()")
  assert await c.js("document.querySelector('#export-all').textContent==='Download selected clips (3)'")
  await c.js("document.querySelector('.wave-toggle').click()")
  assert await c.js("document.querySelector('.wave-album').dataset.expanded==='false'")
  assert not c.errors,c.errors
  print('PASS: clean form, platform icons, YouTube-only timing, scoped YouTube controls/publish/progress/link, Instagram copy/download/real new tab/blocked popup/failure, clip navigation and persistence, cover selection, desktop/mobile bounds, selection and expansion; no JS exceptions')
if __name__=='__main__':asyncio.run(main())
