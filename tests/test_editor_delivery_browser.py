"""Real Chrome/FFmpeg workflow. Auth, stock search, AI and trend provider are fixtures.
Uses production editor, persistence, pointer gestures, drop handling and exports.
"""
import asyncio,base64,json,urllib.request
from pathlib import Path
from tests.test_editor_browser import Chrome

PID='d'*32
BASE='http://127.0.0.1:8767'
ARTIFACTS=Path('/tmp/cascade-delivery-browser-artifacts')

def api(path,body=None,method='GET'):
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Authorization':'Bearer editor-browser-fixture','Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req))

async def main():
 import websockets
 ARTIFACTS.mkdir(exist_ok=True)
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list'))if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
  c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'");await asyncio.sleep(.3)
  await c.call('Storage.clearDataForOrigin',{'origin':BASE,'storageTypes':'local_storage'})
  api('/__editor_reset',{},'POST')
  async def visit(view):
   await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'")
   await c.call('Page.navigate',{'url':BASE+'/__exports_test/'+view+'?project='+PID})
   await c.until('!!window.siteReady');await c.js('window.siteReady')
  await visit('editor');await c.until("document.querySelector('#editor-video').readyState>=2")
  assert await c.js("!document.querySelector('#export-edit')&&!document.querySelector('#crop-x')&&!document.querySelector('#follow-speaker')")
  assert await c.js("document.querySelector('#timeline-toggle').getAttribute('aria-expanded')==='false'")
  await c.js("document.querySelector('#editor-video').currentTime=2")
  await c.until("!document.querySelector('#editor-video').seeking")
  await c.click('#timeline-toggle');assert await c.js("document.querySelector('#timeline-broll').checkVisibility()")
  await c.click('#timeline-toggle');assert await c.js("Math.abs(document.querySelector('#editor-video').currentTime-2)<.05")
  await c.click('#research-tab');await c.until("document.querySelector('#settings-form').onsubmit!==null")
  await c.input('settings-video-type','podcast');await c.input('settings-audience','Builders');await c.input('settings-tone','educational');await c.input('settings-goal','Explain the idea')
  await c.js("document.querySelector('[name=platforms][value=youtube]').checked=true")
  await c.click('#settings-form button');await c.until("document.querySelector('#preferences-status').textContent.includes('saved')")
  assert api('/api/settings')['audience']=='Builders'
  await c.input('research-topic','video editing');await c.click('#research-form button')
  await c.until("document.querySelector('#research-result').textContent.includes('Fixture research for video editing')",30)
  await visit('editor');await c.click('#research-tab')
  await c.until("document.querySelector('#settings-audience').value==='Builders'")
  assert await c.js("document.querySelector('[name=platforms][value=youtube]').checked")
  await c.click('#broll-tab');await c.input('broll-query','mountains');await c.click('#broll-search');await c.until("!!document.querySelector('#broll-results [data-asset]')")
  assert await c.js("document.querySelector('#broll-results article').draggable")
  await c.click('#broll-results [data-asset]');await c.until("!document.querySelector('#broll-add').disabled")
  await c.input('broll-start','0');await c.input('broll-duration','1');await c.click('#broll-add')
  await c.until("document.querySelectorAll('#broll-segments article').length===1")
  # Start a real HTML drag from a search card with DevTools mouse input.
  # This exercises dragstart/DataTransfer as well as hover expansion and drop.
  rect=await c.box('#timeline-content')
  source=await c.js("(()=>{const r=document.querySelector('#broll-results article').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+25};})()")
  x=rect['x']+rect['width']*3/8;y=rect['y']+70
  await c.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':source['x'],'y':source['y'],'button':'left','clickCount':1})
  for step in range(1,13):
   await c.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':source['x']+(x-source['x'])*step/12,'y':source['y']+(y-source['y'])*step/12,'button':'left','buttons':1})
  assert await c.js("document.querySelector('#timeline-toggle').getAttribute('aria-expanded')==='true'")
  assert await c.js("document.querySelector('.broll-drop-marker').checkVisibility()&&!document.querySelector('.broll-drop-marker').classList.contains('invalid')")
  await c.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':x,'y':y,'button':'left','clickCount':1})
  await c.until("document.querySelectorAll('#broll-segments article').length===2")
  await c.until("document.querySelector('#broll-live').readyState>=2&&!document.querySelector('#broll-live').hidden")
  state="JSON.parse(localStorage.getItem('cascade-editor:v1:editor-browser-user:'+ 'd'.repeat(32)+':'+ 'a'.repeat(32)+':0')).state"
  before=await c.js(state+'.broll[1]');assert abs(before['start']-3)<.1,before
  # Reposition the inserted segment; one pointer gesture must be one undo step.
  rect=await c.box('#timeline-content');pps=rect['width']/8
  box=await c.box('#timeline-broll [data-broll="'+before['id']+'"]')
  await c.drag(box['x']+box['width']/2,box['y']+box['height']/2,box['x']+box['width']/2+pps*.5)
  moved=await c.js(state+'.broll[1]');assert abs(moved['start']-before['start']-.5)<.05,(before,moved)
  await c.click('#undo');assert abs((await c.js(state+'.broll[1].start'))-before['start'])<.05
  await c.click('#redo')
  # Trim both edges and verify stock source offset follows the left edge.
  edge=await c.box('#timeline-broll [data-broll="'+before['id']+'"] .broll-edge-end')
  await c.drag(edge['x']+edge['width']/2,edge['y']+15,edge['x']+edge['width']/2-pps*.5)
  shortened=await c.js(state+'.broll[1]');assert abs(shortened['duration']-2.5)<.05,shortened
  edge=await c.box('#timeline-broll [data-broll="'+before['id']+'"] .broll-edge-start')
  await c.drag(edge['x']+edge['width']/2,edge['y']+15,edge['x']+edge['width']/2+pps*.25)
  trimmed=await c.js(state+'.broll[1]');assert abs(trimmed['offset']-.25)<.05,trimmed
  await c.click('#timeline-toggle');playhead=await c.js("document.querySelector('#editor-video').currentTime")
  await c.click('#timeline-toggle');assert abs(await c.js("document.querySelector('#editor-video').currentTime")-playhead)<.05
  # The existing replacement action and numeric placement remain usable.
  await c.click('#broll-results [data-asset]');await c.until("!document.querySelector('#broll-replace').disabled");await c.click('#broll-replace')
  await c.until("document.querySelector('#save-status').textContent==='Saved'")
  saved=api('/api/projects/'+PID+'/editor/'+'a'*32+'/0')['draft']['state']['broll'];assert len(saved)==2 and abs(saved[1]['offset']-.25)<.05,saved
  await visit('editor');await c.click('#broll-tab')
  await c.until("document.querySelectorAll('#broll-segments article').length===2")
  await c.click('#broll-segments article:last-child button:last-child');assert await c.js("document.querySelectorAll('#broll-segments article').length===1")
  await c.click('#undo');assert await c.js("document.querySelectorAll('#broll-segments article').length===2")
  # Layouts and screenshots exercise each new panel and the grouped destination.
  async def shot(name):
   await c.js('scrollTo(0,0)');r=await c.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True});(ARTIFACTS/name).write_bytes(base64.b64decode(r['data']))
  await shot('editor-broll-desktop.png')
  await c.click('#research-tab');await shot('research-desktop.png')
  for width in [1024,768,390]:
   await c.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':1000,'deviceScaleFactor':1,'mobile':False});await c.js('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
   assert await c.js('document.documentElement.scrollWidth<=innerWidth'),width
   await shot(f'editor-{width}.png')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await visit('settings');assert await c.js("!document.querySelector('#settings-form')&&document.body.textContent.includes('Research Agent')")
  await visit('editor');await c.until("document.querySelector('#save-status').textContent==='Saved'")
  await c.click('#open-exports');await c.until("document.body.dataset.page==='exports'&&!!window.siteReady");await c.js('window.siteReady')
  await c.until("document.querySelector('.export-media-card video').readyState>=2",60)
  assert await c.js("document.querySelectorAll('.export-card-check:checked').length===4")
  await c.js("document.querySelector('.export-card-check').click()")
  assert await c.js("document.querySelector('#export-all').textContent==='Download selected clips (3)'&&document.querySelectorAll('#exports-tree .clip-nav-row input:checked').length===3")
  await c.until("[...document.querySelectorAll('.export-media-card video')].every(v=>v.readyState>=3)",90)
  await c.js('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
  await asyncio.sleep(.5)
  await shot('exports-desktop.png')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':1000,'deviceScaleFactor':1,'mobile':False})
  assert await c.js('document.documentElement.scrollWidth<=innerWidth');await shot('exports-phone.png')
  assert not c.errors,c.errors
  print('PASS: compact/expanded timeline; preferences save/reload; Research Agent fixture request/results; Add, native drop/auto-expand/insertion preview, immediate B-roll playback, move, both-edge trim, undo/redo, replacement/removal/restore; Settings; grouped Exports selection; responsive UI.')

if __name__=='__main__':asyncio.run(main())
