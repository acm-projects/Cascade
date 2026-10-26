"""Real models/media, preview subject picking, undo, isolation, persistence and MP4."""
import asyncio,json,urllib.request,base64,subprocess
from pathlib import Path
from tests.test_editor_browser import Chrome
BASE='http://127.0.0.1:8767';PID='8'*32;JID='e'*32
ART=Path('/tmp/cascade-subject-browser');ART.mkdir(exist_ok=True)

def api(path):return json.load(urllib.request.urlopen(urllib.request.Request(BASE+path,headers={'Authorization':'Bearer editor-browser-fixture'})))
async def main():
 import websockets
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
  c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable');await c.call('Network.enable');await c.call('Network.setCacheDisabled',{'cacheDisabled':True})
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'")
  await c.call('Storage.clearDataForOrigin',{'origin':BASE,'storageTypes':'local_storage'})
  urllib.request.urlopen(urllib.request.Request(BASE+'/__editor_reset',data=b'',method='POST')).close()
  await c.call('Page.navigate',{'url':BASE+'/__exports_test/editor?project='+PID+'&job='+JID+'&clip=0'})
  await c.until('!!window.siteReady');await c.js('window.siteReady');await c.until("document.querySelector('#editor-video').readyState>=2")
  await c.click('#ratio-tab');await c.click('[data-ratio="9:16"]');await c.input('framing','fill')
  async def ready():await c.until("!document.querySelector('#chat-send').disabled&&document.querySelector('#reframe-status').textContent.includes('ready')",120)
  await ready()
  await c.js("document.querySelector('#editor-video').currentTime=0")
  await c.until("!document.querySelector('#editor-video').seeking")
  await c.click('#subject-pick');await c.until("!document.querySelector('#subject-picker').hidden");await asyncio.sleep(.5)
  r=await c.box('#editor-video');x=r['x']+r['width']*.72;y=r['y']+r['height']*.55
  for kind in ('mousePressed','mouseReleased'):await c.call('Input.dispatchMouseEvent',{'type':kind,'x':x,'y':y,'button':'left','clickCount':1})
  await ready();await c.until("document.querySelector('#subject-help').textContent.includes('saved')",120)
  await asyncio.sleep(.9);path='/api/projects/'+PID+'/editor/'+JID+'/0'
  selection=api(path)['draft']['state']['reframe']['selection'];assert selection and selection['box'][2]>.05,selection
  await c.click('#undo');await ready();await asyncio.sleep(.9);assert api(path)['draft']['state']['reframe']['selection'] is None
  await c.click('#redo');await ready();await asyncio.sleep(.9);assert api(path)['draft']['state']['reframe']['selection']==selection
  # Separate bag clip retains its own draft; manually select this unsupported COCO region.
  await c.js("document.querySelectorAll('#editor-sessions .mini-clip')[2].click()")
  await c.until("document.querySelector('#editor-clip-title').textContent.includes('Clip 3')&&!document.querySelector('#chat-send').disabled")
  bagpath='/api/projects/'+PID+'/editor/'+JID+'/2';assert api(bagpath)['draft']['state']['reframe']['selection'] is None
  await c.click('[data-ratio="9:16"]');await c.input('framing','fill');await ready()
  await c.click('#subject-pick');await asyncio.sleep(.5);r=await c.box('#editor-video')
  await c.drag(r['x']+r['width']*.64,r['y']+r['height']*.36,r['x']+r['width']*.89,r['y']+r['height']*.72)
  await ready();await c.until("document.querySelector('#subject-help').textContent.includes('saved')",120);await asyncio.sleep(1)
  draft=api(bagpath)['draft']['state'];assert draft['reframe']['selection']
  origin=await c.js('performance.timeOrigin');await c.call('Page.reload');await c.until(f'performance.timeOrigin!=={origin}&&!!window.siteReady');await c.js('window.siteReady');await ready()
  assert api(bagpath)['draft']['state']['reframe']['selection']==draft['reframe']['selection']
  # Source/preview crop and encoded output use identical points; sample the actual result.
  await c.js("document.querySelector('#editor-video').currentTime=.6")
  await c.until("!document.querySelector('#editor-video').seeking")
  await c.js('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
  preview=await c.js("(()=>{const v=document.querySelector('#editor-video');return {left:parseFloat(v.style.left),width:parseFloat(v.style.width)};})()")
  plan=api(bagpath+'/reframe/'+draft['reframe']['analysis_id']+'/subjects?t=.6')
  req=urllib.request.Request(BASE+bagpath+'/export',data=json.dumps({**draft,'overlays':[]}).encode(),headers={'Authorization':'Bearer editor-browser-fixture','Content-Type':'application/json'})
  data=urllib.request.urlopen(req,timeout=120).read();(ART/'selected-bag.mp4').write_bytes(data)
  assert len(data)>1000
  # Independently construct the expected frame using the browser's crop position.
  x=2*round((-preview['left']/preview['width']*640)/2)
  (ART/'bag-source.mp4').write_bytes(urllib.request.urlopen(urllib.request.Request(BASE+bagpath+'/media',headers={'Authorization':'Bearer editor-browser-fixture'})).read())
  for name,source,filters in [('actual',ART/'selected-bag.mp4',None),('expected',ART/'bag-source.mp4',f'scale=640:480:flags=lanczos,setsar=1,crop=270:480:{x}:0')]:
   command=['ffmpeg','-v','error','-y','-ss','0.6','-i',str(source)]
   if filters:command+=['-vf',filters]
   subprocess.run([*command,'-frames:v','1',str(ART/(name+'.png'))],check=True)
  from PIL import Image,ImageChops,ImageStat
  difference=sum(ImageStat.Stat(ImageChops.difference(Image.open(ART/'actual.png').convert('RGB'),Image.open(ART/'expected.png').convert('RGB'))).mean)/3
  assert difference<10,{'preview_export_pixel_difference':difference,'crop_x':x}

  shot=await c.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True});(ART/'selected-bag-editor.png').write_bytes(base64.b64decode(shot['data']))
  assert not c.errors,c.errors
  print('PASS: real dog click selection, bag box selection, independent drafts, undo/redo, reload, real selected-region MP4; screenshot:',ART)
if __name__=='__main__':asyncio.run(main())
