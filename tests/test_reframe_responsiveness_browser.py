"""Real analysis responsiveness, cancellation/rejoin and ready-cache latency."""
import asyncio,json,urllib.request,time,statistics
from pathlib import Path
from tests.test_editor_browser import Chrome
BASE='http://127.0.0.1:8767';PID='9'*32;JID='c'*32;URL='/api/projects/'+PID+'/editor/'+JID+'/0'
def post(focus):
 req=urllib.request.Request(BASE+URL+'/reframe',data=json.dumps({'composition':{'ratio':'9:16','mode':'fill'},'focus':focus}).encode(),headers={'Authorization':'Bearer editor-browser-fixture','Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(req))
async def main():
 import websockets
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
  c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable');await c.call('Network.enable');await c.call('Network.setCacheDisabled',{'cacheDisabled':True})
  await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'")
  await c.call('Storage.clearDataForOrigin',{'origin':BASE,'storageTypes':'local_storage'})
  urllib.request.urlopen(urllib.request.Request(BASE+'/__editor_reset',data=b'',method='POST')).close()
  await c.call('Page.navigate',{'url':BASE+'/__exports_test/editor?project='+PID+'&job='+JID+'&clip=0'})
  await c.until('!!window.siteReady');await c.js('window.siteReady');await c.until("document.querySelector('#editor-video').readyState>=2")
  await c.click('#ratio-tab');await c.click('[data-ratio="9:16"]');await c.input('framing','fill')
  await c.until("!document.querySelector('#chat-send').disabled&&document.querySelector('#reframe-status').textContent.includes('ready')",120)
  await c.input('reframe-focus','left')
  await c.until("!document.querySelector('#reframe-cancel').hidden&&!document.querySelector('#reframe-cancel').disabled")
  await asyncio.sleep(.1);shared=post('left');assert shared['cache_hit'],shared
  assert await c.js("!document.querySelector('#preview-play').disabled")
  await c.click('#preview-play');await c.until("!document.querySelector('#editor-video').paused&&document.querySelector('#editor-video').currentTime>.1")
  await c.click('#reframe-cancel');await c.until("!document.querySelector('#chat-send').disabled")
  if await c.js("!document.querySelector('#editor-video').paused"):await c.click('#preview-play')
  again=post('left');assert again['analysis_id']==shared['analysis_id'] and again['cache_hit'],(shared,again)
  await c.input('reframe-focus','left');await c.until("!document.querySelector('#chat-send').disabled&&document.querySelector('#reframe-focus').value==='left'",120)
  samples=[]
  for _ in range(10):
   start=time.perf_counter();result=post('left');samples.append((time.perf_counter()-start)*1000)
   assert result['cache_hit'] and result['analysis_id']==shared['analysis_id'] and result['status']=='ready'
  status=json.load(urllib.request.urlopen(urllib.request.Request(BASE+URL+'/reframe/'+shared['analysis_id'],headers={'Authorization':'Bearer editor-browser-fixture'})))
  assert status['profile']=='visual' and 'active_speaker' not in status['timings'],status
  await c.click('#undo');await c.until("document.querySelector('#reframe-focus').value==='auto'&&!document.querySelector('#chat-send').disabled")
  await c.click('#redo');await c.until("document.querySelector('#reframe-focus').value==='left'&&!document.querySelector('#chat-send').disabled")
  assert not c.errors,c.errors
  record={'cache_request_milliseconds':samples,'median_milliseconds':statistics.median(samples),'analysis_id':shared['analysis_id'],'profile':status['profile']}
  Path('/tmp/cascade-perf-cache.json').write_text(json.dumps(record,indent=2));print('PASS: real-analysis playback, enabled Cancel, cancellation/rejoin shares job, undo/redo, visual focus skips ASD; ready-cache median',round(record['median_milliseconds'],2),'ms')
if __name__=='__main__':asyncio.run(main())
