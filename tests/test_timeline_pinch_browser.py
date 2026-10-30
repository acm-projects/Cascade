"""Browser input checks for cursor-anchored trackpad zoom and native scrolling."""

from browser_support import require_browser_tests
require_browser_tests()
import asyncio,json,urllib.request
from tests.test_editor_browser import Chrome

async def main():
 import websockets
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
  c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable');await c.call('Network.enable');await c.call('Network.setCacheDisabled',{'cacheDisabled':True})
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'")
  await c.call('Page.navigate',{'url':'http://127.0.0.1:8767/__editor_test?project='+'d'*32})
  await c.until('!!window.editorReady');await c.js('window.editorReady');await c.until("document.querySelector('#timeline-content').offsetWidth>0")
  await c.input('timeline-zoom','3');await c.js("document.querySelector('#timeline-scroll').scrollLeft=300")
  box=await c.box('#timeline-scroll');x=box['x']+box['width']*.42;y=box['y']+20
  async def state():
   return await c.js(f"(()=>{{const e=document.querySelector('#timeline-content'),s=document.querySelector('#timeline-scroll');return {{time:({x}-e.getBoundingClientRect().left)/e.offsetWidth,zoom:+document.querySelector('#timeline-zoom').value,label:document.querySelector('#zoom-label').textContent,scroll:s.scrollLeft,page:visualViewport.scale}}}})()")
  before=await state()
  await c.call('Input.dispatchMouseEvent',{'type':'mouseWheel','x':x,'y':y,'deltaX':0,'deltaY':-35,'modifiers':2})
  await asyncio.sleep(.3);after=await state()
  assert after['zoom']>before['zoom'] and abs(after['time']-before['time'])<.001,(before,after)
  assert after['label']==str(round(after['zoom']*100))+'%' and after['page']==1,after
  await c.call('Input.dispatchMouseEvent',{'type':'mouseWheel','x':x,'y':y,'deltaX':0,'deltaY':35,'modifiers':2})
  await asyncio.sleep(.3);out=await state();assert out['zoom']<after['zoom'] and abs(out['time']-before['time'])<.001,out
  await c.call('Input.dispatchMouseEvent',{'type':'mouseWheel','x':x,'y':y,'deltaX':160,'deltaY':0})
  await asyncio.sleep(.4);scrolled=await state();assert scrolled['scroll']>out['scroll']+100 and scrolled['zoom']==out['zoom'],scrolled
  await c.click('#zoom-fit');await c.until("(()=>{const s=document.querySelector('#timeline-scroll');return s.scrollLeft===0&&s.scrollWidth<=s.clientWidth+1;})()")
  fit=await c.js("(()=>{const s=document.querySelector('#timeline-scroll');return {left:s.scrollLeft,width:s.clientWidth,total:s.scrollWidth,label:document.querySelector('#zoom-label').textContent};})()");assert fit['left']==0 and fit['total']<=fit['width']+1 and fit['label']=='100%',fit
  await c.click('#zoom-in');assert (await state())['zoom']==1.5
  print('PASS: native Ctrl+wheel pinch in/out, cursor anchor, slider/percentage, horizontal wheel, Fit, zoom button')
if __name__=='__main__':asyncio.run(main())
