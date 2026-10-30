"""Native horizontal scroll, mouse drag, touch input, snapping and wave spread."""

from browser_support import require_browser_tests
require_browser_tests()
import asyncio,base64,json,urllib.request
from pathlib import Path
from tests.test_editor_browser import Chrome

BASE='http://127.0.0.1:8767'
ARTIFACTS=Path('/tmp/cascade-horizontal-exports-artifacts')

async def main():
 import websockets
 ARTIFACTS.mkdir(exist_ok=True)
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list'))if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None)as ws:
  c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
  await c.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'no-preference'}]})
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'")
  await c.call('Storage.clearDataForOrigin',{'origin':BASE,'storageTypes':'local_storage'})
  await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':"localStorage.setItem('cascade-export-selection:v1:editor-browser-user:"+'9'*32+"',JSON.stringify([0,1,2,3].map(clip_index=>({job_id:'c'.repeat(32),clip_index}))));"})
  await c.call('Page.navigate',{'url':BASE+'/__exports_test/exports?project='+'9'*32})
  await c.until('!!window.siteReady');await c.js('window.siteReady')
  await c.until("document.querySelectorAll('.stack-layer.ready').length===4",90)
  assert await c.js("document.querySelector('.wave-toggle').getAttribute('aria-expanded')==='false'")
  async def shot(name):
   await c.js('scrollTo(0,0)');await asyncio.sleep(.5)
   r=await c.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True});(ARTIFACTS/name).write_bytes(base64.b64decode(r['data']))
  assert await c.js("(()=>{const d=document.querySelector('#export-deck').getBoundingClientRect(),a=document.querySelector('.export-actions').getBoundingClientRect();return a.bottom<=d.top&&!document.querySelector('#export-title')&&!document.querySelector('#export-meta')&&[...document.querySelectorAll('.wave-album-heading h3')].every(e=>e.hidden);})()")
  await shot('collapsed-desktop.png')
  await c.click('.wave-stack');await c.until("document.querySelector('.wave-stack-wrap').getBoundingClientRect().height<1")
  await asyncio.sleep(.6)
  geometry=await c.js("(()=>{const rail=document.querySelector('.wave-clips'),cards=[...rail.children].filter(e=>e.matches('.export-media-card'));return {width:rail.clientWidth,available:document.querySelector('.export-studio').clientWidth,card:cards[0].offsetWidth,visible:rail.clientWidth/cards[0].offsetWidth,sameRow:cards.every(c=>c.offsetTop===cards[0].offsetTop),x:cards.map(c=>c.offsetLeft),snap:getComputedStyle(rail).scrollSnapType};})()")
  assert geometry['width']>=geometry['available']*.9 and geometry['sameRow'] and geometry['visible']>=3 and geometry['card']>=250 and geometry['snap']=='x mandatory',geometry
  await shot('horizontal-desktop.png')
  async def settled(index):
   await c.until(f"!document.querySelector('.wave-clips').classList.contains('is-spreading')&&document.querySelector('.wave-rail-position').textContent==='{index+1} of 4'&&document.querySelectorAll('.export-media-card')[{index}].dataset.active==='true'",15)
   await c.until(f"(()=>{{const r=document.querySelector('.wave-clips'),card=r.children[{index}];return Math.abs(r.scrollLeft-(card.offsetLeft-parseFloat(getComputedStyle(r).paddingLeft)))<3;}})()")
   error=await c.js(f"(()=>{{const r=document.querySelector('.wave-clips'),card=r.children[{index}];return Math.abs(r.scrollLeft-(card.offsetLeft-parseFloat(getComputedStyle(r).paddingLeft)));}})()")
   assert error<3,(index,error)
  await c.click('.wave-rail-next');await settled(1)
  await c.click('.wave-rail-prev');await settled(0)
  # Native wheel/trackpad horizontal input; no synthetic DOM scroll handler.
  box=await c.box('.wave-clips')
  await c.call('Input.dispatchMouseEvent',{'type':'mouseWheel','x':box['x']+box['width']/2,'y':box['y']+100,'deltaX':geometry['x'][1],'deltaY':0})
  await settled(1)
  # Mouse drag from the active video picture, leaving its control bar untouched.
  await c.click('.wave-rail-prev');await settled(0)
  meta=await c.box('.export-media-card:first-child video')
  start=meta['x']+meta['width']-25;y=meta['y']+70
  await c.drag(start,y,start-geometry['card']*.8)
  await settled(1)
  assert await c.js("!document.querySelector('.wave-clips').classList.contains('is-dragging')")
  assert await c.js("document.querySelectorAll('#exports-tree .mini-clip')[1].classList.contains('active')")
  # Playback and checkbox actions must not turn into dragging.
  await c.js("document.querySelector('.export-media-card[data-active=true] video').play()")
  await c.until("!document.querySelector('.export-media-card[data-active=true] video').paused")
  await c.js("document.querySelectorAll('.export-card-check')[1].click()")
  assert await c.js("document.querySelector('#export-all').textContent==='Download selected clips (3)'")
  await c.click('.wave-toggle');await c.until("document.querySelector('.wave-gallery').getBoundingClientRect().height<1")
  assert await c.js("[...document.querySelectorAll('.wave-clips video')].every(v=>v.paused)")
  await c.click('.wave-toggle');await settled(1)
  # Direct sidebar selection scrolls to the last card without changing its order.
  await c.js("document.querySelectorAll('#exports-tree .mini-clip')[3].click()")
  await settled(3)
  assert await c.js("[...document.querySelectorAll('.export-card-header label')].map(l=>l.textContent).join('|')==='Clip 1|Clip 2|Clip 3|Clip 4'")
  for width in (1024,768,390):
   await c.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':1000,'deviceScaleFactor':1,'mobile':False})
   await asyncio.sleep(.6)
   assert await c.js('document.documentElement.scrollWidth<=innerWidth'),width
   assert await c.js("document.querySelector('.wave-clips').scrollWidth>document.querySelector('.wave-clips').clientWidth"),width
  # Browser-emulated native touch swipes on the narrow layout.
  await c.call('Emulation.setTouchEmulationEnabled',{'enabled':True,'maxTouchPoints':1})
  await c.js("document.querySelectorAll('#exports-tree .mini-clip')[0].click()")
  await settled(0)
  rail=await c.box('.wave-clips');x=rail['x']+rail['width']*.85;y=rail['y']+rail['height']-35
  await c.call('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
  for i in range(1,11):
   await c.call('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x-rail['width']*.7*i/10,'y':y}]})
   await asyncio.sleep(.025)
  await c.call('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
  await c.until("document.querySelector('.wave-clips').scrollLeft>40")
  await asyncio.sleep(.6)
  current=await c.js("Number(document.querySelector('.wave-rail-position').textContent.split(' ')[0])-1")
  assert current>0,current
  await settled(current)
  await c.call('Emulation.setTouchEmulationEnabled',{'enabled':False})
  await shot('horizontal-phone.png')
  await c.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
  assert await c.js("getComputedStyle(document.querySelector('.wave-clips')).scrollBehavior==='auto'")
  assert not c.errors,c.errors
  print('PASS: full desktop width, same-row large cards, arrows, native horizontal wheel, mouse drag, browser touch swipe, snapping, sidebar synchronization, selection/playback, collapse/restore, clip order, reduced motion, 1024/768/390px layouts.')

if __name__=='__main__':asyncio.run(main())
