"""Seven-view migration comparison and real legacy-URL navigation.
Requires project_browser_server.py and isolated Chrome. Identity/generation and
Clerk's external widget are fixtures; media, routes, persistence and downloads are real.
Optional original-page screenshots use the /tmp migration snapshot manifest.
"""

from browser_support import require_browser_tests
require_browser_tests()
import asyncio
import base64
import io
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from PIL import Image, ImageChops, ImageStat
from test_project_browser import ProjectChrome

ARTIFACTS=Path('/tmp/cascade-frontend-artifacts')
PID='e'*32
JID='c'*32
BASE='http://127.0.0.1:8767'


async def main():
 import websockets
 ARTIFACTS.mkdir(exist_ok=True)
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
  c=ProjectChrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1366,'height':900,'deviceScaleFactor':1,'mobile':False})
  await c.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
  def api(path,body=None,method='GET'):
   request=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Authorization':'Bearer groups-browser-fixture','Content-Type':'application/json'})
   return json.load(urllib.request.urlopen(request))
  api('/api/projects/'+PID+'/saved-clips',{'job_id':JID,'clip_index':0},'POST')
  async def ready(view):
   await c.until("document.readyState==='complete' && "+("!!document.querySelector('.home-card')" if view=='home' else "document.body.dataset.page==="+json.dumps(view)+" && !!window.siteReady"))
   if view!='home':await c.js('window.siteReady')
   if view=='editor':
    await c.until("document.querySelector('#save-status').textContent==='Saved'")
    await c.until("document.querySelector('#thumbnail-status').textContent==='Frames from selected clip'")
   await c.js("Promise.all(Array.from(document.querySelectorAll('video'),v=>v.readyState>=2?Promise.resolve():new Promise(r=>{v.addEventListener('loadeddata',r,{once:true});v.addEventListener('error',r,{once:true});setTimeout(r,3000)})))")
   await c.js("document.fonts.ready")
   await asyncio.sleep(.45)
   assert await c.js("(()=>{const ids=Array.from(document.querySelectorAll('[id]'),e=>e.id);return new Set(ids).size===ids.length})()")
   assert await c.js("document.querySelectorAll('script[src*=\"flow_C.js\"],script[src*=\"__flow_test.js\"]').length")==(0 if view=='home' else 1)
  async def visit(url,view):
   await c.call('Page.navigate',{'url':url})
   await c.until('location.href==='+json.dumps(url))
   await ready(view)
  async def shot(name):
   await c.js("scrollTo(0,0);document.querySelectorAll('video').forEach(v=>v.pause())")
   await asyncio.sleep(.15)
   result=await c.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
   raw=base64.b64decode(result['data']);(ARTIFACTS/name).write_bytes(raw)
   return Image.open(io.BytesIO(raw)).convert('RGB')
  manifest=Path('/tmp/cascade-consolidation-snapshot-path')
  if manifest.exists() and Path(manifest.read_text().strip()).is_dir():
   for view in ['home','login','projects','canvas','editor','exports','settings']:
    images=[]
    for baseline in [True,False]:
     await c.call('Storage.clearDataForOrigin',{'origin':BASE,'storageTypes':'local_storage'})
     url=BASE+'/__site/'+view+'?project='+PID+'&job='+JID+'&clip=0&baseline='+str(baseline).lower()+'&run='+str(time.time_ns())
     await visit(url,view)
     images.append(await shot(view+('-before' if baseline else '-after')+'.png'))
    difference=ImageChops.difference(*images)
    error=sum(ImageStat.Stat(difference).mean)/3
    # Media first-frame readiness can differ slightly; static markup is also
    # checked byte-for-byte separately during migration.
    assert error<.5,(view,error)
    print(view+': before/after mean pixel difference '+format(error,'.4f')+'/255')
  else:
   print('Original migration snapshots unavailable; visual comparison skipped.')
  # Real public URLs and native links (not only the fixture page aliases).
  await visit(BASE+'/index_C.html','home')
  await c.click('.home-card a');await ready('login')
  assert await c.js('location.pathname')=='/login_C.html'
  await visit(BASE+'/projects_C.html','projects')
  await c.click('a.project-tile[href*="'+PID+'"]');await ready('canvas')
  assert await c.js('location.pathname')=='/canvas_C.html'
  count=len(api('/api/projects/'+PID+'/generations')['groups'])
  await c.js("sessionStorage.removeItem('fixture-paused-on-hide');window.addEventListener('pagehide',()=>sessionStorage.setItem('fixture-paused-on-hide',String(Array.from(document.querySelectorAll('video,audio')).every(v=>v.paused))));const v=document.querySelector('#source-player');v.muted=true;v.play();")
  await c.until("!document.querySelector('#source-player').paused")
  await c.click('#open-editor');await ready('editor')
  assert await c.js("sessionStorage.getItem('fixture-paused-on-hide')")=='true'
  assert await c.js('location.pathname')=='/editor_C.html'
  # Persist a meaningful edit and keep the correct direct-link identifiers.
  await c.click('#captions-tab');await c.input('cap-color','#ffff00')
  await c.until("document.querySelector('#save-status').textContent==='Saved'")
  await visit(BASE+'/settings_C.html','settings')
  await c.input('settings-audience','Browser fixture audience')
  await c.click('#settings-form button[type="submit"]')
  await c.until("document.querySelector('#status').textContent.includes('saved') || document.querySelector('#status').textContent.includes('Saved')")
  assert api('/api/settings')['audience']=='Browser fixture audience'
  history=await c.call('Page.getNavigationHistory')
  previous=next(e for e in reversed(history['entries'][:history['currentIndex']]) if '/editor_C.html' in e['url'])
  await c.call('Page.navigateToHistoryEntry',{'entryId':previous['id']});await ready('editor')
  assert await c.js("document.querySelector('#cap-color').value")=='#ffff00'
  current=await c.call('Page.getNavigationHistory')
  forward=next(e for e in current['entries'][current['currentIndex']+1:] if '/settings_C.html' in e['url'])
  await c.call('Page.navigateToHistoryEntry',{'entryId':forward['id']});await ready('settings')
  assert await c.js("document.querySelector('#settings-audience').value")=='Browser fixture audience'
  await visit(BASE+'/exports_C.html?project='+PID,'exports')
  download_dir=ARTIFACTS/'downloads';download_dir.mkdir(exist_ok=True)
  output=download_dir/'cascade-clip.mp4'
  if output.exists():output.unlink()
  await c.call('Page.setDownloadBehavior',{'behavior':'allow','downloadPath':str(download_dir)})
  await c.click('#saved-clips button')
  for _ in range(100):
   if output.is_file() and not list(download_dir.glob('*.crdownload')):break
   await asyncio.sleep(.1)
  assert output.is_file(),'Original clip download missing'
  probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(output)]))
  assert float(probe['format']['duration'])>0
  await visit(BASE+'/canvas_C.html?project='+PID,'canvas')
  await c.js('window.siteReady=null');await c.call('Page.reload');await ready('canvas')
  assert len(api('/api/projects/'+PID+'/generations')['groups'])==count,'Navigation/reload created a generation'
  print('Legacy URLs, native links, Back/Forward, media pause on leave, saved captions/settings, real MP4 download, reload and no generation on navigation passed.')
  print('Artifacts: '+str(ARTIFACTS))

if __name__=='__main__':asyncio.run(main())
