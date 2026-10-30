"""Coordinated Reel in the official editor; fixtures never call account services."""
import asyncio,base64,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import websockets
from tests.test_editor_browser import Chrome
async def main():
 base='http://127.0.0.1:8771/api/projects/'+'d'*32+'/editor/'+'a'*32+'/0'
 info=json.load(urllib.request.urlopen(base));state=info['draft']['state']
 state.update(audio=[],motion=[],text_overlays=[],broll=[],timeline=[],speed=[],accents=[],reel=None,transition={'fade_in':0,'fade_out':0})
 state['captions']['animation']='none'
 urllib.request.urlopen(urllib.request.Request(base,data=json.dumps({'state':state,'chat':[]}).encode(),method='PUT',headers={'Content-Type':'application/json'})).close()
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9351/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None) as ws:
  c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Page.navigate',{'url':'http://127.0.0.1:8771/projects/'+'d'*32+'/editor'})
  await c.until("!!document.querySelector('.clip-player-video')")
  async def press(text):await c.js("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==="+json.dumps(text)+").click()")
  await press('Reel');await press('Apply High-Energy Reel')
  await c.until("document.body.textContent.includes('detected beats')",30)
  await c.until("document.body.textContent.includes('Rendered preview · same audio/effects as MP4 export')",45)
  expected=json.load(urllib.request.urlopen(base))['draft']['state']
  await c.until("document.querySelector('.editor-save').textContent.includes('Saved')")
  expected=json.load(urllib.request.urlopen(base))['draft']['state']
  assert expected['reel'] and len(expected['motion'])<=3
  assert await c.js("document.querySelector('[role=tab][aria-selected=true]').textContent==='Edited'")
  edited=await c.js("document.querySelector('video').duration")
  await press('Original');await c.until("document.body.textContent.includes('Original source · no edits')")
  await c.until("document.querySelector('video').readyState>=2")
  original=await c.js("document.querySelector('video').duration")
  assert abs(original-6)<.1 and edited<=original+.1
  await press('Edited');await c.until("document.querySelector('video').readyState>=2")
  assert abs(await c.js("document.querySelector('video').duration")-edited)<.01
  await press('↶ Undo');await c.until("!document.body.textContent.includes('detected beats')")
  await press('↷ Redo');await c.until("document.body.textContent.includes('detected beats')")
  await c.until("document.querySelector('.editor-save').textContent.includes('Saved')")
  await c.call('Page.reload');await asyncio.sleep(.6)
  await c.until("!!document.querySelector('.clip-player-video')")
  await press('Reel');await c.until("document.body.textContent.includes('detected beats')")
  await c.until("document.body.textContent.includes('Rendered preview · same audio/effects as MP4 export')",45)
  shot=await c.call('Page.captureScreenshot',{'format':'png'});Path('/tmp/cascade-high-energy-editor.png').write_bytes(base64.b64decode(shot['data']))
  assert not c.errors,c.errors
  print('PASS: Reel apply/plan, Original/Edited tabs, saved state, undo/redo, reload persistence and rendered preview duration parity.')
if __name__=='__main__':asyncio.run(main())
