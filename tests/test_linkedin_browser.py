"""LinkedIn-only browser verification. Provider responses are mocked; no real post/OAuth."""
import asyncio,base64,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import websockets
from tests.test_editor_browser import Chrome
BOOTSTRAP=r"""
if(location.origin==='http://127.0.0.1:8767'){
 localStorage.setItem('cascade-export-selection:v1:editor-browser-user:'+ 'd'.repeat(32),JSON.stringify([{job_id:'a'.repeat(32),clip_index:0},{job_id:'b'.repeat(32),clip_index:0}]));
 const native=window.fetch;window.linkedinCalls=[];window.linkedinConnected=sessionStorage.getItem('li-connected')==='true';window.linkedinConfigured=true;window.linkedinMode='success';window.nativePopupCalls=0;
 window.open=()=>{window.nativePopupCalls++;return {opener:null,location:{href:''},close(){}};};
 window.fetch=(url,options={})=>{
  const path=String(url),respond=data=>Promise.resolve(new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}}));
  if(path.endsWith('/social/linkedin'))return respond({configured:window.linkedinConfigured,connected:window.linkedinConnected,profile:'Fixture personal profile',error:window.linkedinConfigured?'Connect your personal LinkedIn profile.':'LinkedIn is not configured. Set LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET and LINKEDIN_REDIRECT_URI.'});
  if(path.endsWith('/social/linkedin/connect')){window.linkedinConnected=true;sessionStorage.setItem('li-connected','true');return respond({url:'https://www.linkedin.com/oauth/v2/authorization?fixture=1'});}
  if(path.endsWith('/publish/linkedin')){
   let record=JSON.parse(sessionStorage.getItem(path)||'null');
   if(options.method==='POST'){
    const body=JSON.parse(options.body);window.linkedinCalls.push({path,body});
    if(!record){record=window.linkedinMode==='forbidden'?{status:'Failed',error:'LinkedIn video upload initialization failed (HTTP 403, service error 100). Verify Share on LinkedIn (w_member_social) and Videos API access.'}:{status:'Rendering',profile:'Fixture personal profile',submission_id:body.submission_id};sessionStorage.setItem(path,JSON.stringify(record));}
    return respond(record);
   }
   if(!record)return respond({status:'Ready'});
   if(record.status==='Rendering')record.status='Processing';else if(record.status==='Processing'){record.status='Published';record.url='https://www.linkedin.com/feed/update/urn:li:share:12345/';record.video='urn:li:video:fixture';record.post_attempted=true;}
   sessionStorage.setItem(path,JSON.stringify(record));return respond(record);
  }
  return native(url,options);
 };
}
"""
async def main():
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9334/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None) as ws:
  c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
  await c.call('Storage.clearDataForOrigin',{'origin':'http://127.0.0.1:8767','storageTypes':'local_storage,session_storage'})
  await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOTSTRAP})
  await c.call('Page.navigate',{'url':'http://127.0.0.1:8767/__exports_test/exports?project='+'d'*32});await c.until('!!window.siteReady');await c.js('window.siteReady')
  await c.js("document.querySelector('.prepare-post').click()");await c.until("!document.querySelector('.post-section').hidden")
  await c.until("document.querySelector('.post-preview video').readyState>=2")
  await c.js("document.querySelector('[data-destination=linkedin]').click()")
  await c.until("document.querySelector('.post-linkedin .post-account span').textContent.includes('Connect your personal')")
  assert await c.js("document.querySelector('.post-linkedin-publish').disabled&&!document.querySelector('[data-destination=linkedin]').disabled&&document.querySelector('[data-destination=linkedin]').getAttribute('aria-pressed')==='true'&&document.querySelector('.post-timing').hidden&&document.querySelector('.post-instagram').hidden")
  assert await c.js("window.linkedinCalls.length===0")
  # Missing app access stays honest; the panel never simulates a connection.
  await c.js("window.linkedinConfigured=false;document.querySelectorAll('.post-linkedin .post-account button')[1].click()")
  await c.until("document.querySelector('.post-linkedin .post-account span').textContent.includes('LINKEDIN_CLIENT_ID')")
  assert await c.js("document.querySelector('.post-linkedin .post-account button').disabled")
  await c.js("window.linkedinConfigured=true;document.querySelectorAll('.post-linkedin .post-account button')[1].click()")
  await c.until("!document.querySelector('.post-linkedin .post-account button').disabled")
  # Popup blocking is visible; OAuth itself is only a mocked fixture URL.
  await c.js("window.fixtureOpen=window.open;window.open=()=>null;document.querySelector('.post-linkedin .post-account button').click()")
  assert await c.js("document.querySelector('.post-linkedin .post-account span').textContent.includes('Popup blocked')")
  await c.js("window.open=window.fixtureOpen;document.querySelector('.post-linkedin .post-account button').click()")
  await c.until('window.linkedinConnected')
  await c.js("document.querySelectorAll('.post-linkedin .post-account button')[1].click()")
  await c.until("document.querySelector('.post-linkedin .post-account span').textContent.includes('Fixture personal profile')")
  assert await c.js("document.querySelector('.post-linkedin .post-account button').hidden&&window.linkedinCalls.length===0")
  await c.js("const title=document.querySelector('.post-field input');title.value='Current edited clip';title.dispatchEvent(new Event('input'));const caption=document.querySelector('.post-field textarea');caption.value='Personal LinkedIn caption';caption.dispatchEvent(new Event('input'));const tag=document.querySelector('[aria-label=\"New hashtag\"]');tag.value='Cascade';tag.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));document.querySelector('.post-linkedin-publish').click();document.querySelector('.post-linkedin-publish').click()")
  await c.until("document.querySelector('.post-linkedin>p[role=status]').textContent==='Processing'",10)
  await c.until("document.querySelector('.post-linkedin>p[role=status]').textContent==='Published'",10)
  assert await c.js("window.linkedinCalls.length===1&&window.linkedinCalls[0].body.title==='Current edited clip'&&window.linkedinCalls[0].body.caption==='Personal LinkedIn caption'&&window.linkedinCalls[0].body.hashtags.includes('#Cascade')&&!!window.linkedinCalls[0].body.edit.overlays&&document.querySelector('.post-linkedin-publish').disabled&&!document.querySelector('.post-linkedin>a').hidden")
  async def shot(name):
   await c.js("document.querySelector('.post-destination').scrollIntoView({block:'start',behavior:'instant'})");await asyncio.sleep(.4)
   data=await c.call('Page.captureScreenshot',{'format':'png'});Path('/tmp/cascade-linkedin-'+name+'.png').write_bytes(base64.b64decode(data['data']))
  await shot('desktop')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':900,'deviceScaleFactor':1,'mobile':True});await shot('mobile')
  assert await c.js("document.documentElement.scrollWidth<=innerWidth")
  # Reload restores published state and cannot create a duplicate post.
  await c.call('Page.reload');await c.until('!!window.siteReady');await c.js('window.siteReady');await c.js("document.querySelector('.prepare-post').click()");await c.until("!document.querySelector('.post-section').hidden");await c.js("document.querySelector('[data-destination=linkedin]').click()")
  await c.until("document.querySelector('.post-linkedin>p[role=status]').textContent==='Published'")
  assert await c.js("window.linkedinCalls.length===0&&document.querySelector('.post-linkedin-publish').disabled")
  # Switching clips gets its own preview/post data and shows actual access errors.
  await c.js("document.querySelector('#export-next').click()");await c.until("document.querySelector('#export-position').textContent==='2 of 2'&&!document.querySelector('.post-section').hidden")
  await c.js("document.querySelector('[data-destination=linkedin]').click()")
  await c.until("!document.querySelector('.post-linkedin-publish').disabled")
  assert await c.js("document.querySelector('.post-field input').value!=='Current edited clip'")
  await c.js("const title=document.querySelector('.post-field input');title.value='Second clip';title.dispatchEvent(new Event('input'));window.linkedinMode='forbidden';document.querySelector('.post-linkedin-publish').click()")
  await c.until("document.querySelector('.post-linkedin>p[role=status]').textContent.includes('HTTP 403')")
  assert await c.js("document.querySelector('.post-linkedin>a').hidden&&window.linkedinCalls.length===1&&window.linkedinCalls[0].path.includes('b'.repeat(32))")
  # YouTube remains scoped to its original controls; Instagram is never invoked.
  await c.js("document.querySelector('[data-destination=youtube]').click()")
  assert await c.js("document.querySelector('.post-linkedin').hidden&&!document.querySelector('.post-timing').hidden&&document.querySelector('.post-field select').value==='private'")
  assert not c.errors,c.errors
  print('PASS: LinkedIn icon/connect/profile, missing configuration, blocked popup, explicit publish, duplicate protection, final edited payload, progress/link, refresh persistence, per-clip errors, YouTube controls, desktop/mobile layout. All LinkedIn calls mocked; no real post.')
if __name__=='__main__':asyncio.run(main())
