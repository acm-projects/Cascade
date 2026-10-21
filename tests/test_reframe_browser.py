"""Real CPU models, Chrome and FFmpeg; fixture auth/chat only are mocked.
Start editor_browser_server with CASCADE_REFRAME_FIXTURES pointing at controlled media.
"""
import asyncio
import base64
import io
import json
from pathlib import Path
import subprocess
import urllib.request
from tests.test_editor_browser import Chrome
from PIL import Image, ImageChops, ImageStat

async def main():
 import websockets
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list'))if t['type']=='page')
 artifacts=Path('/tmp/cascade-reframe-browser-artifacts');artifacts.mkdir(exist_ok=True)
 for path in artifacts.glob('*.mp4'):path.unlink()
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None)as ws:
  c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable');await c.call('Page.bringToFront')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(artifacts)})
  await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'");await asyncio.sleep(.5)
  await c.call('Storage.clearDataForOrigin',{'origin':'http://127.0.0.1:8767','storageTypes':'local_storage'})
  urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8767/__editor_reset',data=b'',method='POST')).close()
  await c.call('Page.navigate',{'url':'http://127.0.0.1:8767/__exports_test/editor?project='+'9'*32})
  await c.until('!!window.siteReady');await c.js('window.siteReady');await c.until("document.querySelector('#editor-video').readyState>=2")
  assert await c.js("document.querySelectorAll('#editor-sessions>details').length")==1
  assert await c.js("document.querySelectorAll('#editor-sessions .clip-nav-wave').length")==1
  assert await c.js("document.querySelectorAll('#editor-sessions .mini-clip').length")==4
  assert await c.js("[...document.querySelectorAll('#editor-sessions details')].every(e=>e.open)")
  # Exercise the native disclosure controls, including hidden descendants.
  for selector in ['#editor-sessions .clip-nav-wave','#editor-sessions>details']:
   await c.click(selector+'>summary span')
   assert not await c.js(f"document.querySelector({json.dumps(selector)}).open")
   assert await c.js("!document.querySelector('#editor-sessions .mini-clip').checkVisibility()")
   await c.click(selector+'>summary span')
  assert await c.js("document.querySelector('.mini-canvas').getBoundingClientRect().right<=document.querySelector('#preview-wrap').getBoundingClientRect().left")
  await c.click('#ratio-tab');assert await c.js("document.querySelector('#follow-speaker')===null&&document.querySelector('#crop-x')===null&&document.querySelector('#export-edit')===null")
  await c.input('framing','fill')
  await c.until("!document.querySelector('#chat-send').disabled")
  assert await c.js("document.querySelector('#reframe-status').textContent.includes('entire source fits')")
  await c.input('framing','fit')
  await c.click('[data-ratio="9:16"]');await c.input('framing','fill')
  await c.until("document.querySelector('#reframe-status').textContent.includes('ready')&&!document.querySelector('#chat-send').disabled",90)
  await c.box('#preview-wrap')
  await c.js("document.querySelector('#editor-video').currentTime=3")
  await c.until("!document.querySelector('#editor-video').seeking")
  left=await c.js("parseFloat(document.querySelector('#editor-video').style.left)")
  await c.js("document.querySelector('#editor-video').currentTime=10")
  await c.until("!document.querySelector('#editor-video').seeking")
  right=await c.js("parseFloat(document.querySelector('#editor-video').style.left)")
  assert right<left-100,(left,right)
  previews={}
  for instant in (3,10):
   await c.js(f"document.querySelector('#editor-video').currentTime={instant}")
   await c.until("!document.querySelector('#editor-video').seeking")
   await c.js('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
   rect=await c.box('#composition-frame');scroll=await c.js('({x:scrollX,y:scrollY})')
   shot=await c.call('Page.captureScreenshot',{'format':'png','clip':{**rect,'x':rect['x']+scroll['x'],'y':rect['y']+scroll['y'],'scale':1},'captureBeyondViewport':True})
   raw=base64.b64decode(shot['data']);(artifacts/f'preview-{instant}.png').write_bytes(raw)
   previews[instant]=Image.open(io.BytesIO(raw)).convert('RGB')
  await c.click('#undo');await c.until("document.querySelector('#framing').value==='fit'&&!document.querySelector('#chat-send').disabled")
  await c.click('#redo');await c.until("document.querySelector('#framing').value==='fill'&&!document.querySelector('#chat-send').disabled")
  await c.click('#chat-tab');await c.input('chat-input','Focus on the person on the left')
  await c.click('#chat-send');await c.until("!document.querySelector('#chat-send').disabled&&document.querySelector('#reframe-focus').value==='left'",30)
  await c.click('#undo');await c.until("document.querySelector('#reframe-focus').value==='auto'&&!document.querySelector('#chat-send').disabled")
  await c.js("document.querySelectorAll('#editor-sessions .clip-nav-row input').forEach((e,i)=>{if(i<2)e.click()})")
  assert await c.js("document.querySelector('#editor-sessions>details>summary input').indeterminate")
  assert await c.js("document.querySelector('#open-exports').textContent.includes('(2)')")
  await c.js("document.querySelectorAll('#editor-sessions .mini-clip')[1].click()")
  await c.until("document.querySelector('#editor-clip-title').textContent.includes('Clip 2')&&!document.querySelector('#chat-send').disabled")
  assert await c.js("document.querySelector('#open-exports').textContent.includes('(2)')")
  await c.click('#ratio-tab');await c.click('[data-ratio="9:16"]');await c.input('framing','fill')
  await c.until("document.querySelector('#reframe-status').textContent.includes('ready')&&!document.querySelector('#chat-send').disabled",90)
  await c.box('#preview-wrap')
  await c.js("document.querySelector('#editor-video').currentTime=.5");await c.until("!document.querySelector('#editor-video').seeking")
  first=await c.js("parseFloat(document.querySelector('#editor-video').style.left)")
  await c.js("document.querySelector('#editor-video').currentTime=5.5");await c.until("!document.querySelector('#editor-video').seeking")
  last=await c.js("parseFloat(document.querySelector('#editor-video').style.left)")
  assert last<first-100,(first,last)
  await c.input('reframe-focus','right')
  await c.until("document.querySelector('#reframe-focus').value==='right'&&!document.querySelector('#chat-send').disabled")
  await c.until("document.querySelector('#save-status').textContent==='Saved'")
  states=await c.js("Promise.all([0,1].map(i=>fetch('/api/projects/'+'9'.repeat(32)+'/editor/'+'c'.repeat(32)+'/'+i,{headers:{Authorization:'Bearer editor-browser-fixture'}}).then(r=>r.json()).then(r=>r.draft.state.reframe)))")
  assert states[0]['focus']=='auto' and states[1]['focus']=='right',states
  assert states[0]['analysis_id']!=states[1]['analysis_id'],states
  # A legacy Fill draft with tracking disabled must migrate automatically on
  # opening, retaining unrelated caption edits and using its own analysis.
  legacy_url='http://127.0.0.1:8767/api/projects/'+'9'*32+'/editor/'+'c'*32+'/2'
  headers={'Authorization':'Bearer editor-browser-fixture','Content-Type':'application/json'}
  legacy=json.load(urllib.request.urlopen(urllib.request.Request(legacy_url,headers=headers)))['draft']
  legacy['state']['composition'].update(mode='fill',ratio='9:16');legacy['state']['reframe']['enabled']=False;legacy['state']['captions']['color']='#123456'
  urllib.request.urlopen(urllib.request.Request(legacy_url,data=json.dumps(legacy).encode(),headers=headers,method='PUT')).close()
  await c.js("document.querySelectorAll('#editor-sessions .mini-clip')[2].click()")
  await c.until("document.querySelector('#editor-clip-title').textContent.includes('Clip 3')&&document.querySelector('#reframe-status').textContent.includes('ready')&&!document.querySelector('#chat-send').disabled",90)
  await c.until("document.querySelector('#save-status').textContent==='Saved'")
  migrated=json.load(urllib.request.urlopen(urllib.request.Request(legacy_url,headers=headers)))['draft']['state']
  assert migrated['reframe']['enabled'] and migrated['reframe']['analysis_id']
  assert migrated['captions']['color']=='#123456'
  await c.js("document.querySelectorAll('#editor-sessions .mini-clip')[1].click()")
  await c.until("document.querySelector('#editor-clip-title').textContent.includes('Clip 2')&&!document.querySelector('#chat-send').disabled")
  await c.call('Page.reload');await c.until('!!window.siteReady');await c.js('window.siteReady')
  await c.until("!document.querySelector('#chat-send').disabled&&document.querySelector('#reframe-status').textContent.includes('ready')")
  assert await c.js("document.querySelector('#open-exports').textContent.includes('(2)')")
  await c.click('#open-exports');await c.until("document.body.dataset.page==='exports'&&!!window.siteReady");await c.js('window.siteReady')
  assert await c.js("document.querySelectorAll('#exports-tree>details').length")==1
  assert await c.js("document.querySelectorAll('#exports-tree .clip-nav-wave').length")==1
  assert await c.js("document.querySelectorAll('#exports-tree .mini-clip').length")==2
  for selector in ['#exports-tree .clip-nav-wave','#exports-tree>details']:
   await c.click(selector+'>summary span')
   assert not await c.js(f"document.querySelector({json.dumps(selector)}).open")
   assert await c.js("!document.querySelector('#exports-tree .mini-clip').checkVisibility()")
   await c.click(selector+'>summary span')
  await c.until("document.querySelector('.export-media-card[data-active=true] video').readyState>=2",90)
  await c.js("document.querySelectorAll('#exports-tree .mini-clip')[1].click()")
  await c.until("document.querySelector('#export-position').textContent==='2 of 2'")
  assert await c.js("document.querySelector('#exports-tree .mini-clip.active').textContent")=='Clip 2'
  await c.click('#export-prev');await c.until("document.querySelector('#export-position').textContent==='1 of 2'&&!document.querySelector('#download-active').disabled")
  assert await c.js("document.querySelector('#exports-tree .mini-clip.active').textContent")=='Clip 1'
  await c.click('#download-active')
  for _ in range(300):
   if list(artifacts.glob('*.mp4')):break
   await asyncio.sleep(.1)
  output=next(artifacts.glob('*.mp4'))
  probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
  stream=next(s for s in probe['streams']if s['codec_type']=='video')
  assert abs(stream['width']/stream['height']-9/16)<.001
  assert abs(float(probe['format']['duration'])-12)<.1
  assert any(s['codec_type']=='audio'for s in probe['streams'])
  # Compare real browser-composited pixels with decoded export frames at both
  # speaker positions. Merely checking CSS coordinates cannot establish parity.
  for instant,preview in previews.items():
   raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(instant),'-i',str(output),'-frames:v','1','-f','image2pipe','-vcodec','png','-'])
   exported=Image.open(io.BytesIO(raw)).convert('RGB')
   exported.save(artifacts/f'export-{instant}.png')
   error=sum(ImageStat.Stat(ImageChops.difference(preview,exported.resize(preview.size,Image.Resampling.LANCZOS))).mean)/3
   assert error<18,(instant,error)
   print(f'Preview/export pixel difference at {instant}s: {error:.2f}/255')
  assert not c.errors,c.errors
  print('PASS: real audio-visual Follow Speaker shifts between test subjects, follows movement, supports chat/undo/redo/restore, nested one-session/one-wave selection, tri-state checkboxes, synchronized Exports sidebar/carousel, real 9:16 moving-crop export with original duration/audio.')

if __name__=='__main__':asyncio.run(main())
