"""Screenshots and UI checks use unchanged REAL research, not newly mocked findings.
Only the local display/identity/storage harness is isolated; Apply uses real tools.
"""
import asyncio,base64,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import websockets
from tests.test_editor_browser import Chrome
async def main():
 origin='http://127.0.0.1:8783';pid='d'*32;jid='a'*32;api=origin+'/api/projects/'+pid+'/editor/'+jid+'/0'
 baseline=json.loads(Path('/tmp/cascade-guided-display-baseline.json').read_text())
 urllib.request.urlopen(urllib.request.Request(api,data=json.dumps({'state':baseline,'chat':[]}).encode(),method='PUT',headers={'Content-Type':'application/json'})).close()
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9353/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None) as ws:
  c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  async def click(text):await c.js("(()=>{const root=document.querySelector('[role=dialog]')||document;const b=[...root.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+");b.focus();b.click()})()")
  async def shot(name):
   s=await c.call('Page.captureScreenshot',{'format':'png'});Path('/tmp/'+name+'.png').write_bytes(base64.b64decode(s['data']))
  await c.call('Page.navigate',{'url':origin+'/projects/'+pid+'/editor'})
  await c.until("[...document.querySelectorAll('button')].some(b=>b.textContent==='Trends')")
  await click('Trends');await c.until("document.body.textContent.includes('Analyzed 2 examples and 1 tutorial')")
  await c.until("document.querySelector('[role=dialog] video')?.getBoundingClientRect().height>100")
  await c.until("document.querySelector('[role=dialog]').textContent.includes('Rendered preview')",45)
  await c.js("document.querySelector('[role=dialog] video').currentTime=0.5")
  assert json.load(urllib.request.urlopen(api))['draft']['state']==baseline
  assert not await c.js("document.querySelector('.trends-scroll').textContent.includes('visual_style')")
  assert await c.js("document.querySelectorAll('.trends-opportunity').length<=3 && document.querySelectorAll('.trends-strengths li').length<=3")
  await shot('cascade-guided-overview')
  await c.js("document.querySelectorAll('.trends-chip')[1].click()")
  await c.until("document.activeElement.classList.contains('trends-source')")
  assert await c.js("document.activeElement.getAttribute('aria-label').startsWith('Reference 2:') && document.activeElement.getBoundingClientRect().top<document.querySelector('.trends-scroll').getBoundingClientRect().bottom")
  await c.until("[...document.querySelectorAll('.trends-thumbnail img')].every(i=>i.complete)",30)
  print('Thumbnail state:',await c.js("JSON.stringify([...document.querySelectorAll('.trends-thumbnail img')].map(i=>({loaded:i.naturalWidth,width:i.getBoundingClientRect().width,height:i.getBoundingClientRect().height})))"))
  assert await c.js("document.querySelectorAll('.trends-source').length===3 && [...document.querySelectorAll('.trends-watch')].every(a=>a.href.startsWith('https://www.youtube.com/watch?v='))")
  await shot('cascade-guided-references')
  await click('Suggested edits');await c.until("document.querySelectorAll('.trends-suggestion').length>0")
  assert await c.js("document.body.textContent.includes('Unsupported')")
  await shot('cascade-guided-edits')
  await click('Select available edits');await click('Apply selected edits (2)')
  await c.until("document.querySelectorAll('.status-applied').length===2",45)
  await c.until("document.querySelector('.trends-preview-stack').textContent.includes('saved')")
  after=json.load(urllib.request.urlopen(api))['draft']['state'];assert after!=baseline and after['motion'] and after['audio']
  await click('↶ Undo');await c.until("!document.querySelector('.status-applied')")
  await click('↷ Redo');await c.until("document.querySelectorAll('.status-applied').length===2")
  await c.until("document.querySelector('.trends-preview-stack').textContent.includes('saved')")
  await c.call('Page.reload');await asyncio.sleep(.5)
  await c.until("[...document.querySelectorAll('button')].some(b=>b.textContent==='Trends')");await click('Trends');await click('Suggested edits')
  await c.until("document.querySelectorAll('.status-applied').length===2")
  # Keyboard activation uses roving tab focus and does not leave the modal.
  await c.js("document.querySelector('[role=tablist][aria-label=\"Research views\"] [aria-selected=true]').focus()")
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowRight','code':'ArrowRight','windowsVirtualKeyCode':39})
  assert await c.js("document.activeElement.textContent.startsWith('References')")
  await c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
  await click('Overview');await c.js("document.querySelector('.ui-modal-body').scrollTop=0");await asyncio.sleep(.3)
  print('Mobile viewport:',await c.js("JSON.stringify({innerWidth,client:document.documentElement.clientWidth,visual:visualViewport.width,scale:visualViewport.scale})"))
  assert await c.js("Math.abs(visualViewport.width-390)<2")
  await shot('cascade-guided-mobile')
  assert await c.js("document.querySelector('[role=dialog]').getBoundingClientRect().right<=window.innerWidth+1")
  assert await c.js("document.querySelector('.ui-modal-body').scrollHeight>document.querySelector('.ui-modal-body').clientHeight")
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
  await c.until("!document.querySelector('[role=dialog]')")
  assert await c.js("document.activeElement.textContent==='Trends'")
  assert not c.errors,c.errors
  print('PASS: actual saved real analysis, compact limits, provenance chip navigation/focus, selected Apply/undo/redo/save/reload, tabs keyboard, mobile scrolling and Escape. No fresh provider findings simulated.')
if __name__=='__main__':asyncio.run(main())
