"""Official React UI, real persistence/executor/render; research providers mocked."""
import asyncio,base64,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import websockets
from tests.test_editor_browser import Chrome
async def main():
 origin='http://127.0.0.1:8782';project='d'*32;base=origin+'/projects/'+project
 api_url=origin+'/api/projects/'+project+'/editor/'+'a'*32+'/0'
 info=json.load(urllib.request.urlopen(api_url));state=info['draft']['state']
 state.update(start=0,end=info['duration'],audio=[],motion=[],text_overlays=[],broll=[],timeline=[],speed=[],accents=[],reel=None)
 state['captions'].update(animation='none',max_words=0,size=32)
 urllib.request.urlopen(urllib.request.Request(api_url,data=json.dumps({'state':state,'chat':[]}).encode(),method='PUT',headers={'Content-Type':'application/json'})).close()
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9352/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None) as ws:
  c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  async def press(text):await c.js("(()=>{const scope=document.querySelector('[role=dialog]')||document;const b=Array.from(scope.querySelectorAll('button')).find(b=>b.textContent.trim()==="+json.dumps(text)+");b.focus();b.click()})()")
  await c.call('Page.navigate',{'url':base+'/editor'});await c.until("!!document.querySelector('.clip-player-video')")
  await press('Trends');await c.until("!!document.querySelector('.trends-tabs')")
  assert await c.js("!!document.querySelector('[role=dialog][aria-modal=true]') && document.body.style.overflow==='hidden'")
  await c.until("document.querySelector('[role=dialog] video')?.getBoundingClientRect().height>100")
  assert json.load(urllib.request.urlopen(api_url))['draft']['state']==state
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
  await c.until("!document.querySelector('[role=dialog]')")
  assert await c.js("document.activeElement.textContent==='Trends'")
  await c.js("window.originalFetch=window.fetch;window.failResearchLoad=true;window.fetch=(url,options)=>{if(window.failResearchLoad&&String(url).endsWith('/trends')&&(!options?.method||options.method==='GET')){window.failResearchLoad=false;return Promise.resolve(new Response(JSON.stringify({detail:'Temporary research loading failure'}),{status:503,headers:{'Content-Type':'application/json'}}))}return window.originalFetch(url,options)}")
  await press('Trends');await c.until("document.body.textContent.includes('Temporary research loading failure')")
  await press('Retry');await c.until("!document.body.textContent.includes('Temporary research loading failure')")
  await c.until("!Array.from(document.querySelector('[role=dialog]').querySelectorAll('button')).find(b=>b.textContent==='Analyze clip').disabled")
  await press('Analyze clip');await c.until("document.body.textContent.includes('What to improve') && !!document.querySelector('.trends-chip')",30)
  assert json.load(urllib.request.urlopen(api_url))['draft']['state']==state
  assert await c.js("document.body.textContent.includes('Test data — not live YouTube analysis.')")
  assert await c.js("!!document.querySelector('.trends-guide')")
  await c.js("[...document.querySelectorAll('.trends-tabs button')].find(b=>b.textContent.startsWith('References')).click()")
  assert await c.js("document.querySelector('.trends-source a').href.startsWith('https://www.youtube.com/')")
  assert await c.js("Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Read aloud')")
  await c.js("window.speechSynthesis.speak=()=>{window.testSpoke=true};window.speechSynthesis.cancel=()=>{window.testStopped=true}")
  await press('Read aloud');await c.until("[...document.querySelectorAll('button')].some(b=>b.textContent==='Stop')")
  await press('Stop');assert await c.js("window.testSpoke&&window.testStopped")
  await c.js("document.querySelector('[role=dialog] button').focus()")
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Tab','code':'Tab','windowsVirtualKeyCode':9,'modifiers':8})
  assert await c.js("document.querySelector('[role=dialog]').contains(document.activeElement)")
  await press('Suggested edits');await press('Select available edits');await press('Apply selected edits (4)')
  await c.until("!!document.querySelector('.status-applied')",45)
  await press('↶ Undo');await c.until("!document.querySelector('.status-applied')")
  await press('↷ Redo');await c.until("document.querySelector('.editor-save').textContent.includes('Saved')")
  await c.call('Page.reload');await asyncio.sleep(.5);await c.until("Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Trends')")
  await press('Trends');await press('Suggested edits');await c.until("!!document.querySelector('.status-applied')")
  await c.js("document.querySelector('[role=dialog] video').currentTime=.6")
  await asyncio.sleep(.3)
  shot=await c.call('Page.captureScreenshot',{'format':'png'});Path('/tmp/cascade-trends-editor.png').write_bytes(base64.b64decode(shot['data']))
  await c.call('Page.navigate',{'url':base+'/export'});await c.until("Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Trends · YouTube research')")
  await press('Trends · YouTube research')
  await c.until("document.body.textContent.includes('What to improve')")
  assert await c.js("!!document.querySelector('.trends-guide')")
  await c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
  await asyncio.sleep(.3)
  assert await c.js("document.documentElement.scrollWidth<=window.innerWidth+1")
  assert await c.js("document.querySelector('[role=dialog]').getBoundingClientRect().width<=window.innerWidth && document.querySelector('.ui-modal-body').scrollHeight>document.querySelector('.ui-modal-body').clientHeight")
  shot=await c.call('Page.captureScreenshot',{'format':'png'});Path('/tmp/cascade-trends-modal-mobile.png').write_bytes(base64.b64decode(shot['data']))
  assert not c.errors,c.errors
  print('PASS: shared Trends modal, Escape/focus return/trap, read-only opening and analysis, retry, explicit test labels, citations, guide/read/stop, apply/undo/redo, save/reload, Exports reuse and mobile scrolling; providers mocked.')
if __name__=='__main__':asyncio.run(main())
