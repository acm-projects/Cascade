"""Calendar UI and native-scheduling state management in a real browser; Google is mocked."""
import asyncio,base64,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import websockets
from tests.test_editor_browser import Chrome

BOOTSTRAP=r"""
if(location.origin==='http://127.0.0.1:8767'){
 localStorage.setItem('cascade-export-selection:v1:editor-browser-user:'+ 'd'.repeat(32),JSON.stringify([{job_id:'a'.repeat(32),clip_index:0},{job_id:'b'.repeat(32),clip_index:0}]));
 const nativeFetch=window.fetch;window.scheduleCalls=[];
 window.fetch=(url,options={})=>{
  const path=String(url),response=data=>Promise.resolve(new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}}));
  if(path.endsWith('/social/youtube'))return response({connected:true,can_schedule:sessionStorage.getItem('scheduleScope')!=='missing',channel:'Calendar fixture channel'});
  if(path.endsWith('/publish/youtube')||path.endsWith('/publish/youtube/schedule')){
   const base=path.replace(/\/schedule$/,''),saved=JSON.parse(sessionStorage.getItem(base)||'null');
   if(options.method==='POST'){
    window.scheduleCalls.push({method:'POST',path,body:JSON.parse(options.body)});
    if(saved)return response(saved);
    const body=JSON.parse(options.body),value={status:'Rendering',schedule:{...body.schedule,publish_at:new Date(window.CascadeScheduleTime.candidates(body.schedule.local_datetime,body.schedule.timezone).find(c=>c.offset===body.schedule.utc_offset_minutes).instant).toISOString()},revision:0};
    sessionStorage.setItem(base,JSON.stringify(value));return response(value);
   }
   if(options.method==='PUT'){
    const body=JSON.parse(options.body);window.scheduleCalls.push({method:'PUT',path,body});
    const value={...saved,status:body.schedule?'Scheduled':'Private',schedule:body.schedule?{...body.schedule,publish_at:new Date(window.CascadeScheduleTime.candidates(body.schedule.local_datetime,body.schedule.timezone).find(c=>c.offset===body.schedule.utc_offset_minutes).instant).toISOString()}:null,revision:(saved.revision||0)+1,message:body.schedule?'':'Schedule canceled. Your uploaded video is Private and will not publish automatically.'};
    sessionStorage.setItem(base,JSON.stringify(value));return response(value);
   }
   if(!saved)return response({status:'Ready'});
   if(saved.status==='Rendering')Object.assign(saved,{status:'Processing',video_id:'scheduled-fixture',url:'https://www.youtube.com/watch?v=scheduled-fixture'});
   else if(saved.status==='Processing')Object.assign(saved,{status:'Scheduled',revision:1});
   sessionStorage.setItem(base,JSON.stringify(saved));return response(saved);
  }
  return nativeFetch(url,options);
 };
}
"""

async def main():
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None) as ws:
  c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable')
  await c.call('Emulation.setTimezoneOverride',{'timezoneId':'America/Chicago'})
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
  await c.call('Storage.clearDataForOrigin',{'origin':'http://127.0.0.1:8767','storageTypes':'local_storage,session_storage'})
  await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOTSTRAP})
  await c.call('Page.navigate',{'url':'http://127.0.0.1:8767/__exports_test/exports?project='+'d'*32});await c.until('!!window.siteReady');await c.js('window.siteReady')
  await c.js("document.querySelector('.prepare-post').click()")
  await c.until("!document.querySelector('.post-section').hidden")
  await c.js("const title=document.querySelector('.post-field input');title.value='Scheduled clip';title.dispatchEvent(new Event('input'))")
  assert await c.js("document.querySelector('.post-timing').hidden&&document.querySelector('.post-schedule').hidden")
  await c.js("document.querySelector('[data-destination=youtube]').click()")
  assert await c.js("!document.querySelector('.post-timing').hidden&&document.querySelector('.post-schedule').hidden&&document.querySelector('.post-timing button').getAttribute('aria-pressed')==='true'")
  await c.js("document.querySelectorAll('.post-timing button')[1].click()")
  await c.until("!document.querySelector('.schedule-popover').hidden&&!document.querySelector('.post-destination>button').disabled")
  assert await c.js("document.querySelector('.schedule-zone select').value==='America/Chicago'&&document.querySelector('.post-field select').parentElement.hidden&&document.querySelector('.post-destination>button').textContent==='Schedule on YouTube'")
  assert await c.js("!!document.querySelector('.schedule-calendar [aria-current=date]')&&[...document.querySelectorAll('.schedule-calendar button:disabled')].every(b=>b.dataset.date<window.CascadeScheduleTime.date(Date.now(),'America/Chicago'))")
  # Keyboard navigation selects the next calendar day; months navigate independently.
  await c.js("window.selectedDay=document.querySelector('.schedule-calendar [aria-selected=true]').dataset.date;document.querySelector('.schedule-calendar [aria-selected=true]').focus()")
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowRight'})
  assert await c.js("document.activeElement.dataset.date!==window.selectedDay")
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'nativeVirtualKeyCode':13,'text':'\r'})
  await c.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'nativeVirtualKeyCode':13})
  assert await c.js("document.querySelector('.schedule-calendar [aria-selected=true]').dataset.date!==window.selectedDay")
  await c.js("window.calendarMonth=document.querySelector('.schedule-month strong').textContent;document.querySelector('[aria-label=\"Next month\"]').click()")
  assert await c.js("document.querySelector('.schedule-month strong').textContent!==window.calendarMonth")
  await c.js("document.querySelector('[aria-label=\"Previous month\"]').click()")
  assert await c.js("document.querySelector('.schedule-month strong').textContent===window.calendarMonth")
  # Same-day past/too-soon time displays a control-local error and blocks submission.
  await c.js("document.querySelector('.schedule-calendar [aria-current=date]').click();const p=window.CascadeScheduleTime.parts(Date.now(),'America/Chicago');const s=document.querySelectorAll('.schedule-clock select');s[0].value=String(+p.hour%12||12);s[1].value=p.minute;s[2].value=+p.hour<12?'AM':'PM';s[0].dispatchEvent(new Event('change'))")
  assert await c.js("document.querySelector('.schedule-error:last-of-type')!==null&&document.querySelector('.schedule-summary').textContent.includes('30 minutes')&&document.querySelector('.post-destination>button').disabled")
  # Pick tomorrow and 3:30 PM, then choose another timezone.
  await c.js("const tomorrow=window.CascadeScheduleTime.date(Date.now()+86400000,'America/Chicago');if(!document.querySelector('[data-date=\"'+tomorrow+'\"]'))document.querySelector('[aria-label=\"Next month\"]').click();document.querySelector('[data-date=\"'+tomorrow+'\"]').click();const clock=document.querySelectorAll('.schedule-clock select');clock[0].value='3';clock[1].value='30';clock[2].value='PM';clock[0].dispatchEvent(new Event('change'));const z=document.querySelector('.schedule-zone select');z.value='America/New_York';z.dispatchEvent(new Event('change'))")
  assert await c.js("document.querySelector('.schedule-summary').textContent.includes('3:30 PM · America/New_York')&&!document.querySelector('.post-destination>button').disabled")
  async def shot(name):
   await c.js("document.querySelector('.post-destination').scrollIntoView({block:'start',behavior:'instant'})");await asyncio.sleep(.4)
   data=await c.call('Page.captureScreenshot',{'format':'png'});Path('/tmp/cascade-schedule-'+name+'.png').write_bytes(base64.b64decode(data['data']))
  await shot('desktop')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':1000,'deviceScaleFactor':1,'mobile':True});await shot('mobile')
  assert await c.js("document.documentElement.scrollWidth<=innerWidth&&document.querySelector('.schedule-popover').getBoundingClientRect().right<=innerWidth")
  await c.js("document.querySelector('.schedule-calendar [aria-selected=true]').focus()")
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape'})
  assert await c.js("document.querySelector('.schedule-popover').hidden&&!document.querySelector('.post-section').hidden&&document.activeElement.className==='schedule-trigger'")
  await c.js("document.querySelector('.post-destination>button').click();document.querySelector('.post-destination>button').click()")
  await c.until("document.querySelector('.post-destination>p').textContent==='Processing'",10)
  await c.until("document.querySelector('.post-destination>p').textContent.startsWith('Scheduled for')",10)
  assert await c.js("window.scheduleCalls.filter(c=>c.method==='POST').length===1&&window.scheduleCalls[0].body.privacy==='private'&&window.scheduleCalls[0].body.schedule.timezone==='America/New_York'&&!document.querySelector('.post-destination>a').hidden")
  # An uploaded clip can change its schedule without another POST or render.
  await c.js("document.querySelector('.post-schedule-management button').click();document.querySelectorAll('.schedule-clock select')[0].value='4';document.querySelectorAll('.schedule-clock select')[0].dispatchEvent(new Event('change'));document.querySelector('.post-destination>button').click()")
  await c.until("document.querySelector('.post-destination>p').textContent.includes('4:30 PM')")
  assert await c.js("window.scheduleCalls.filter(c=>c.method==='POST').length===1&&window.scheduleCalls.filter(c=>c.method==='PUT').length===1")
  # Reload reads the persisted schedule and offers management, not another upload.
  await c.call('Page.reload');await c.until('!!window.siteReady');await c.js('window.siteReady');await c.js("document.querySelector('.prepare-post').click()");await c.until("!document.querySelector('.post-section').hidden")
  await c.js("document.querySelector('[data-destination=youtube]').click()")
  await c.until("document.querySelector('.post-destination>p').textContent.includes('4:30 PM')")
  assert await c.js("document.querySelector('.post-destination>button').hidden&&window.scheduleCalls.length===0")
  await c.js("document.querySelectorAll('.post-schedule-management>button')[1].click()")
  assert await c.js("!document.querySelector('.schedule-cancel-confirm').hidden&&document.querySelector('.schedule-cancel-confirm').textContent.includes('Private')")
  await c.js("document.querySelectorAll('.schedule-cancel-confirm button')[1].click()")
  await c.until("document.querySelector('.post-destination>p').textContent.includes('Schedule canceled.')")
  assert await c.js("window.scheduleCalls.length===1&&window.scheduleCalls[0].body.schedule===null")
  # Other clips/platforms keep their own form, hide scheduling and preserve handoffs.
  await c.js("document.querySelector('#export-next').click()")
  await c.until("!document.querySelector('.post-section').hidden&&document.querySelector('#export-position').textContent==='2 of 2'")
  await c.js("document.querySelector('[data-destination=instagram]').click()")
  await c.until("['Download & Open Instagram','Share video…'].includes(document.querySelector('.post-destination>button').textContent)")
  assert await c.js("document.querySelector('.post-timing').hidden&&document.querySelector('.post-schedule').hidden")
  await c.js("document.querySelector('[data-destination=download]').click()")
  assert await c.js("document.querySelector('.post-timing').hidden&&document.querySelector('.post-destination>button').textContent==='Download MP4'")
  assert not c.errors,c.errors
  print('PASS: calendar months, selected/today/past dates, keyboard navigation/Escape, AM/PM/timezone validation, responsive layout, Public explanation, scheduling states, single submission, change/cancel, reload persistence and per-clip/platform isolation. Google transport mocked; no real scheduled upload.')

if __name__=='__main__':asyncio.run(main())
