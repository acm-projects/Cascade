"""Screenshots and UI checks use unchanged REAL research, not newly mocked findings.
Only the local display/identity/storage harness is isolated. Trends is analysis only.
"""
import asyncio,base64,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import websockets
from tests.browser.test_editor_browser import Chrome
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
  await click('Trends');await c.until("document.body.textContent.includes('Based on 2 examples and 1 tutorial')")
  assert json.load(urllib.request.urlopen(api))['draft']['state']==baseline
  assert not await c.js("document.querySelector('.trends-scroll').textContent.includes('visual_style')")
  assert await c.js("document.querySelectorAll('.trends-improvement').length<=6 && document.querySelectorAll('.trends-strengths li').length<=6")
  await shot('cascade-guided-report')
  await c.js("document.querySelectorAll('.trends-cite')[0].click()")
  await c.until("document.activeElement.classList.contains('trends-source')")
  await c.until("[...document.querySelectorAll('.trends-thumbnail img')].every(i=>i.complete)",30)
  assert await c.js("document.querySelectorAll('.trends-source').length===3 && [...document.querySelectorAll('.trends-source h4 a')].every(a=>a.href.startsWith('https://www.youtube.com/watch?v='))")
  await c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True});await asyncio.sleep(.3)
  await shot('cascade-guided-mobile')
  assert await c.js("document.querySelector('[role=dialog]').getBoundingClientRect().right<=window.innerWidth+1")
  assert await c.js("document.querySelector('.trends-scroll').scrollHeight>document.querySelector('.trends-scroll').clientHeight")
  await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
  await c.until("!document.querySelector('[role=dialog]')")
  assert await c.js("document.activeElement.textContent==='Trends'")
  assert json.load(urllib.request.urlopen(api))['draft']['state']==baseline
  assert not c.errors,c.errors
  print('PASS: actual saved real analysis in one report, source links and focus, clip unchanged, mobile scrolling and Escape. No fresh provider findings simulated.')
if __name__=='__main__':asyncio.run(main())
