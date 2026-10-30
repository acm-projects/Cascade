"""Real thumbnails before edited rendering, retry and refresh across saves."""

from browser_support import require_browser_tests
require_browser_tests()
import asyncio
import base64
import json
import urllib.request
from pathlib import Path
from tests.test_editor_browser import Chrome

BASE='http://127.0.0.1:8767'
PID='d'*32

async def main():
 import websockets
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
  c=Chrome(ws)
  await c.call('Runtime.enable');await c.call('Page.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  script="""
   localStorage.setItem('cascade-export-selection:v1:editor-browser-user:PROJECT',JSON.stringify([
     {job_id:'a'.repeat(32),clip_index:0},{job_id:'b'.repeat(32),clip_index:2}]));
   const realFetch=window.fetch;window.thumbnailRequests=[];window.releaseExports=[];
   let failThumbnail=true;
   window.fetch=async(url,options)=>{
     if(String(url).endsWith('/thumbnail')) {
       window.thumbnailRequests.push(String(url));
       if(String(url).includes('b'.repeat(32))&&failThumbnail){failThumbnail=false;return new Response(JSON.stringify({detail:'Fixture thumbnail failure'}),{status:503,headers:{'Content-Type':'application/json'}});}
     }
     if(String(url).endsWith('/export'))await new Promise(resolve=>window.releaseExports.push(resolve));
     return realFetch(url,options);
   };
  """.replace('PROJECT',PID)
  injection=await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':script})
  try:
   for refresh in (False,True):
    if refresh:await c.call('Page.reload')
    else:await c.call('Page.navigate',{'url':BASE+'/__exports_test/exports?project='+PID})
    await c.until("document.querySelectorAll('.export-media-card').length===2&&window.thumbnailRequests.length===2")
    await c.until("document.querySelectorAll('.export-media-card video')[0].poster.startsWith('blob:')&&!document.querySelectorAll('.export-thumbnail-retry')[1].hidden")
    assert await c.js("document.querySelectorAll('.wave-album').length===1")
    assert await c.js("!document.querySelectorAll('.export-media-card video')[0].getAttribute('src')"),'Thumbnail waited for the edited export'
    await c.click('.wave-stack')
    await c.until("document.querySelector('.wave-stack-wrap').getBoundingClientRect().height<1&&!document.querySelector('.wave-clips').classList.contains('is-spreading')")
    await c.click('.export-media-card:nth-child(2) .export-thumbnail-retry')
    await c.until("[...document.querySelectorAll('.export-media-card video')].every(v=>v.poster.startsWith('blob:'))")
    await c.until("[...document.querySelectorAll('.stack-layer img')].every(i=>i.complete&&i.naturalWidth>0&&getComputedStyle(i).opacity==='1')")
    # Decode every actual card poster, including the clip from the second save.
    assert await c.js("Promise.all([...document.querySelectorAll('.export-media-card video')].map(v=>new Promise(resolve=>{const i=new Image();i.onload=()=>resolve(i.naturalWidth===640&&i.naturalHeight===360);i.onerror=()=>resolve(false);i.src=v.poster;}))).then(results=>results.every(Boolean))")
    assert await c.js("thumbnailRequests.every(u=>u.endsWith('/'+'a'.repeat(32)+'/0/thumbnail')||u.endsWith('/'+'b'.repeat(32)+'/2/thumbnail'))")
    if refresh:
     shot=await c.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True})
     Path('/tmp/cascade-exports-thumbnails.png').write_bytes(base64.b64decode(shot['data']))
   assert not c.errors,c.errors
  finally:
   await c.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':injection['identifier']})
   await c.call('Page.navigate',{'url':'about:blank'})
 print('PASS: real JPEGs from two saves, one tile, no unselected requests, posters before edited rendering, failed request/retry, CSS visibility, refresh')

if __name__=='__main__':asyncio.run(main())
