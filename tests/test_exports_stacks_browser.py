"""Reference-inspired wave stacks, real edited media, browser interactions and ZIPs.
Run against editor_browser_server.py. Auth/providers are fixtures, media is real.
"""
import asyncio,base64,json,urllib.request,zipfile
from pathlib import Path
from tests.test_editor_browser import Chrome

BASE='http://127.0.0.1:8767'
PID='d'*32
ARTIFACTS=Path('/tmp/cascade-wave-stack-artifacts')

def api(path):
 return json.load(urllib.request.urlopen(urllib.request.Request(BASE+path,headers={'Authorization':'Bearer editor-browser-fixture'})))

async def main():
 import websockets
 ARTIFACTS.mkdir(exist_ok=True)
 for path in ARTIFACTS.glob('*.zip'):path.unlink()
 before=api('/api/projects/'+PID)
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list'))if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None)as ws:
  c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
  await c.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'no-preference'}]})
  await c.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(ARTIFACTS)})
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'")
  await c.call('Storage.clearDataForOrigin',{'origin':BASE,'storageTypes':'local_storage'})
  await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':"localStorage.setItem('cascade-export-selection:v1:editor-browser-user:"+PID+"',JSON.stringify([{job_id:'a'.repeat(32),clip_index:0},...[0,1,2].map(clip_index=>({job_id:'b'.repeat(32),clip_index}))]));"})
  await c.call('Page.navigate',{'url':BASE+'/__exports_test/exports?project='+PID})
  await c.until('!!window.siteReady');await c.js('window.siteReady')
  assert await c.js("document.querySelectorAll('.wave-album').length")==1
  assert await c.js("[...document.querySelectorAll('.wave-item-count')].map(e=>e.textContent).join('|')")=='4 clips'
  assert await c.js("[...document.querySelectorAll('.wave-album')].every(e=>e.dataset.expanded==='false'&&e.querySelector('.wave-gallery').inert)")
  assert await c.js("[...document.querySelectorAll('.wave-album')].map(e=>e.querySelectorAll('.stack-layer').length).join('|')")=='4'
  await c.until("[...document.querySelectorAll('.stack-layer img')].every(i=>i.complete&&i.naturalWidth>0)",90)
  # Check actual geometry: portrait front, offset/rotated lower layers and no
  # download actions positioned over the thumbnails.
  geometry=await c.js("(()=>{const w=document.querySelectorAll('.wave-album')[0],layers=[...w.querySelectorAll('.stack-layer')],front=layers[0].getBoundingClientRect(),pile=w.querySelector('.stack-pile').getBoundingClientRect();return {ratio:front.width/front.height,width:front.width/pile.width,frontZ:+getComputedStyle(layers[0]).zIndex,backZ:+getComputedStyle(layers[1]).zIndex,rotation:getComputedStyle(layers[1]).transform,peek:layers.slice(1).some(l=>{const r=l.getBoundingClientRect();return r.left<front.left||r.right>front.right;}),actionsOutside:!w.querySelector('.wave-stack .export-card-download')};})()")
  assert geometry['ratio']>1.4 and abs(geometry['width']-1)<.01,geometry
  assert geometry['frontZ']>geometry['backZ'] and geometry['rotation']!='none' and geometry['peek'] and geometry['actionsOutside'],geometry
  async def shot(name):
   await c.js('scrollTo(0,0)');await asyncio.sleep(.5)
   result=await c.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True});(ARTIFACTS/name).write_bytes(base64.b64decode(result['data']))
  await shot('stacks-desktop.png')
  assert await c.js("getComputedStyle(document.querySelector('.wave-gallery')).transitionDuration.split(',')[0].trim()")=='0.38s'
  # A real click opens the shared stack and exposes all four clips.
  await c.click('.wave-album .wave-stack')
  await c.until("document.querySelectorAll('.wave-gallery')[0].getBoundingClientRect().height>100")
  assert await c.js("document.querySelectorAll('.wave-toggle')[0].getAttribute('aria-expanded')==='true'")
  await c.until("document.querySelectorAll('.wave-album')[0].querySelector('.wave-stack-wrap').getBoundingClientRect().height<1")
  await c.until("!document.querySelectorAll('.wave-album')[0].querySelector('.wave-clips').classList.contains('is-spreading')")
  assert await c.js("document.querySelectorAll('.wave-album')[0].querySelectorAll('.export-media-card').length")==4
  geometry=await c.js("(()=>{const g=document.querySelectorAll('.wave-album')[0],cards=[...g.querySelectorAll('.export-media-card')],rail=g.querySelector('.wave-clips');return {sameRow:Math.abs(cards[0].offsetTop-cards[1].offsetTop)<2,horizontal:cards[1].offsetLeft>cards[0].offsetLeft,width:g.getBoundingClientRect().width,available:document.querySelector('.export-studio').getBoundingClientRect().width,snap:getComputedStyle(rail).scrollSnapType};})()")
  assert geometry['sameRow'] and geometry['horizontal'] and geometry['width']>=geometry['available']*.95 and geometry['snap']=='x mandatory',geometry
  await c.js("document.querySelector('.wave-album[data-expanded=true] [data-active=true] video').play()")
  await c.until("!document.querySelector('.wave-album[data-expanded=true] [data-active=true] video').paused")
  await c.click('.wave-album .wave-toggle')
  await c.until("document.querySelectorAll('.wave-gallery')[0].getBoundingClientRect().height<1")
  assert await c.js("[...document.querySelectorAll('.wave-album')[0].querySelectorAll('video')].every(v=>v.paused)")
  # Sidebar navigation must expand the shared tile and highlight its clip.
  await c.js("document.querySelectorAll('#exports-tree .mini-clip')[3].click()")
  await c.until("document.querySelectorAll('.wave-album')[0].dataset.expanded==='true'&&document.querySelector('#export-position').textContent==='4 of 4'")
  assert await c.js("document.querySelectorAll('#exports-tree .mini-clip')[3].classList.contains('active')")
  await c.js("document.querySelectorAll('.export-card-check')[2].click()")
  assert await c.js("document.querySelector('#export-all').textContent==='Download selected clips (3)'&&document.querySelectorAll('#exports-tree .clip-nav-row input:checked').length===3")
  # The tile downloads the selected review set across source saves.
  await asyncio.sleep(1)  # Let expansion and sidebar smooth scrolling settle.
  await c.click('.wave-album .wave-download')
  for _ in range(300):
   if list(ARTIFACTS.glob('*.zip')):break
   await asyncio.sleep(.1)
  archive=next(ARTIFACTS.glob('*.zip'))
  with zipfile.ZipFile(archive)as zipped:
   names=zipped.namelist();assert len(names)==4 and any('a'*8 in name for name in names) and any('b'*8 in name for name in names),names
  await shot('wave-expanded-desktop.png')
  # Keyboard dismissal restores access to the collapse/expand control.
  await c.js("document.querySelectorAll('.wave-toggle')[0].focus()")
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape'})
  await c.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','code':'Escape'})
  await c.until("document.querySelectorAll('.wave-album')[0].dataset.expanded==='false'")
  for width in (1024,768,390):
   await c.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':1000,'deviceScaleFactor':1,'mobile':False})
   await asyncio.sleep(.5)
   assert await c.js('document.documentElement.scrollWidth<=innerWidth'),width
   await shot(f'stacks-{width}.png')
   await c.click('.wave-album .wave-toggle')
   await asyncio.sleep(.5)
   assert await c.js('document.documentElement.scrollWidth<=innerWidth'),width
   assert await c.js("document.querySelectorAll('.wave-gallery')[0].inert===false"),width
   if width==390:await shot('wave-expanded-phone.png')
   await c.click('.wave-album .wave-toggle')
  # Respect reduced motion, without losing expand/collapse behavior.
  await c.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
  assert await c.js("getComputedStyle(document.querySelector('.wave-gallery')).transitionDuration")=='0s'
  await c.click('.wave-album .wave-toggle')
  assert await c.js("document.querySelectorAll('.wave-album')[0].dataset.expanded==='true'")
  assert not c.errors,c.errors
 after=api('/api/projects/'+PID)
 assert before==after,'Exports changed the project history or saved project record.'
 print('PASS: single selection stack/count, real edited posters, wide/overlap geometry, expand/collapse, larger playback, pause on collapse, sidebar synchronization, selection, cross-save ZIP, keyboard, reduced motion, responsive layouts, unchanged project records.')

if __name__=='__main__':asyncio.run(main())
