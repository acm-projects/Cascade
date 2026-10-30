"""Official React editor UI against advanced_editor_browser_server.py.
No real AI, stock search, account or publishing requests are used.
"""
import asyncio,base64,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import websockets
from tests.test_editor_browser import Chrome

async def main():
 base='http://127.0.0.1:8771/api/projects/'+'d'*32+'/editor/'+'a'*32+'/0'
 info=json.load(urllib.request.urlopen(base));state=info['draft']['state']
 state.update(audio=[],motion=[],text_overlays=[],broll=[],dialogue_volume=1,transition={'fade_in':0,'fade_out':0})
 state['captions']['animation']='none'
 urllib.request.urlopen(urllib.request.Request(base,data=json.dumps({'state':state,'chat':[]}).encode(),method='PUT',headers={'Content-Type':'application/json'})).close()
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9351/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None) as ws:
  c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Page.navigate',{'url':'http://127.0.0.1:8771/projects/'+'d'*32+'/editor'})
  await c.until("!!document.querySelector('.clip-player-video')")
  async def press(text):await c.js("(()=>{const b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==="+json.dumps(text)+");if(!b||b.disabled)throw Error('Missing or disabled '+"+json.dumps(text)+");b.click()})()")
  async def input(selector,value):
   await c.js("(()=>{const e=document.querySelector("+json.dumps(selector)+");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,"+json.dumps(value)+");e.dispatchEvent(new Event('input',{bubbles:true}))})()")
  async def shot(name):
   image=await c.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});Path('/tmp/cascade-advanced-'+name+'.png').write_bytes(base64.b64decode(image['data']))
  await press('Music');await c.until("document.querySelectorAll('.music-asset').length===7",30)
  assert await c.js("Array.from(document.querySelectorAll('.editor-panel-tab')).map(e=>e.textContent).join(',')==='Trim,Captions,Trends,Aspect Ratio,Music,Reel,Chat'")
  await press('Preview audio');await c.until("document.querySelector('.music-asset audio')?.readyState>=2")
  await c.js("document.querySelector('.music-asset .editor-choice:last-child').click()")
  await c.until("document.querySelectorAll('.music-segment').length===1")
  await press('↶ Undo');await c.until("document.querySelectorAll('.music-segment').length===0")
  await press('↷ Redo');await c.until("document.querySelectorAll('.music-segment').length===1")
  await press('Remove audio');await c.until("document.querySelectorAll('.music-segment').length===0")
  await press('Chat');await input('.chatbox-input','Add short B-roll, dramatic music, bell sound, punch-in and highlighted captions; keep full duration.')
  await c.js("document.querySelector('.chatbox-send').click()")
  await c.until("document.querySelector('.chatbox-messages').textContent.includes('APPLIED:')",30)
  await c.until("document.body.textContent.includes('Rendered preview · same audio/effects as MP4 export')",45)
  await press('Music');await c.until("document.querySelectorAll('.music-segment').length===2")
  assert await c.js("!!document.querySelector('[aria-label=\"Music track\"]')&&!!document.querySelector('[aria-label=\"B-roll track\"]')")
  await input('[aria-label="music volume"]','0.35')
  await asyncio.sleep(.9)
  await c.until("document.querySelector('.editor-save')?.textContent.includes('Saved')",20)
  await shot('music-desktop')
  await c.call('Page.reload')
  await asyncio.sleep(.5)
  await c.until("!!document.querySelector('.clip-player-video')")
  await press('Music');await c.until("document.querySelector('[aria-label=\"music volume\"]')?.value==='0.35'",30)
  assert await c.js("document.querySelectorAll('.music-segment').length===2")
  await c.until("document.body.textContent.includes('Rendered preview · same audio/effects as MP4 export')",45)
  await c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
  await asyncio.sleep(.5);await shot('music-mobile')
  assert await c.js('document.documentElement.scrollWidth<=innerWidth')
  assert not c.errors,c.errors
  print('PASS: official editor layout, Music listing/audio preview/add/remove, undo/redo, multi-edit chat, shared timeline/music state, manual volume autosave/reload, exact rendered preview and mobile layout.')
if __name__=='__main__':asyncio.run(main())
