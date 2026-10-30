"""Horizontal branch/history Chrome checks against project_browser_server.py.
Selection and identity are mocked; HTTP persistence, media cuts and playback are real.
"""

from browser_support import require_browser_tests
require_browser_tests()
import asyncio
import base64
import json
import time
import urllib.request
from pathlib import Path
from test_project_browser import ProjectChrome


async def main():
 import websockets
 pid='e'*32
 target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
  c=ProjectChrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
  await c.call('Emulation.setDeviceMetricsOverride',{'width':1366,'height':900,'deviceScaleFactor':1,'mobile':False})
  async def visit(page,query=''):
   url='http://127.0.0.1:8767/__site/'+page+query+('&' if query else '?')+'run='+str(time.time_ns())
   await c.call('Page.navigate',{'url':url});await c.until('location.href==='+json.dumps(url)+' && !!window.siteReady');await c.js('window.siteReady')
  async def groups():return await c.js("Array.from(document.querySelectorAll('.generation-group'),n=>n.dataset.job)")
  async def submit(prompt,count,expected):
   await c.input('clip-count',str(count));await c.input('clip-prompt',prompt)
   await c.box('#generate-clip')
   await asyncio.sleep(.35)  # Let native focus/media and smooth scroll settle before a pointer click.
   await c.click('#generate-clip')
   page_y=await c.js('scrollY')  # Native focus may scroll the button; measure subsequent column changes.
   await c.until('document.querySelectorAll(".generation-group").length==='+str(expected))
   jid=(await groups())[-1]
   await c.until("document.querySelector('[data-job=\""+jid+"\"]').textContent.includes('queued') || document.querySelector('[data-job=\""+jid+"\"]').textContent.includes('processing') || document.querySelector('[data-job=\""+jid+"\"]').textContent.includes('done')",3)
   assert await c.js('Math.abs(scrollY-'+str(page_y)+')<3'),('New column moved the page',page_y,await c.js('scrollY'))
   await c.until("!document.querySelector('#generate-clip').disabled",30)
   assert len(await groups())==expected
   return jid
  await visit('canvas','?project='+pid)
  root=(await groups())[0]
  assert await c.js("document.querySelector('.generation-group').dataset.depth")=='0'
  await c.click('[data-job="'+root+'"] .clip-placeholder button')
  child=await submit('Find five related moments',5,2)
  await c.click('[data-job="'+child+'"] .clip-placeholder:nth-child(5) button')
  grand=await submit('Explain this child moment',2,3)
  await c.click('[data-job="'+root+'"] .clip-placeholder button')
  sibling=await submit('A sibling from the same parent',3,4)
  await c.click('[data-job="'+child+'"] .clip-placeholder:nth-child(2) button')
  second=await submit('Follow-up specifically from Clip 2',2,5)
  assert await c.js("document.querySelector('[data-prompt-job=\""+second+"\"]').textContent.includes('Clip 2')")
  assert await c.js("document.querySelectorAll('.prompt-node').length")==5
  assert not await c.js("document.querySelector('#prompt-history')!==null")
  assert await c.js("document.querySelectorAll('.clip-connectors path').length")==13
  positions=await c.js("Object.fromEntries(Array.from(document.querySelectorAll('.generation-group'),n=>[n.dataset.job,{depth:+n.dataset.depth,column:+n.dataset.column,row:+n.dataset.row,left:n.offsetLeft,top:n.offsetTop}]))")
  assert positions[root]['depth']==0 and positions[child]['depth']==1 and positions[grand]['depth']==2
  assert positions[sibling]['depth']==1 and positions[sibling]['column']>positions[grand]['column'] and positions[sibling]['row']==positions[child]['row']==0
  assert len(set(v['top'] for v in positions.values()))==1
  assert positions[grand]['left']>positions[child]['left']>positions[root]['left']
  assert await c.js("document.querySelectorAll('.branch-connectors path[data-kind=\"parent-prompt\"]').length")==len(await groups())
  await c.click('[data-job="'+child+'"] .clip-placeholder button')
  failed=await submit('Fail fixture once',2,6)
  assert await c.js("document.querySelectorAll('.prompt-node').length")==6
  assert 'error' in await c.js("document.querySelector('[data-history-id=\""+failed+"\"]').textContent")
  before=await c.js("document.querySelectorAll('.generation-group').length")
  await c.click('[data-history-id="'+failed+'"] .generation-retry')
  await c.until("!document.querySelector('#generate-clip').disabled && document.querySelector('[data-job=\""+failed+"\"]').textContent.includes('done')",30)
  assert await c.js("document.querySelectorAll('.generation-group').length")==before
  assert await c.js("document.querySelectorAll('.prompt-node').length")==6
  assert await c.js("document.querySelectorAll('[data-job=\""+root+"\"] .clip-placeholder').length")==1
  # Jump reveals the sibling column horizontally and highlights it; the canvas stays on one row.
  await c.click('[data-history-id="'+sibling+'"] .history-jump');await asyncio.sleep(.5)
  measurement=await c.js("(()=>{const v=document.querySelector('#branch-viewport'),r=v.getBoundingClientRect(),g=document.querySelector('[data-job=\""+sibling+"\"]'),b=g.getBoundingClientRect();return {visible:b.left>=r.left-1&&b.right<=r.right+1&&b.top>=r.top-1&&b.top<r.bottom,highlight:g.classList.contains('branch-highlight'),scrollY:v.scrollTop}})()")
  assert measurement['visible'] and measurement['highlight'] and measurement['scrollY']==0,measurement
  # Trackpad-like horizontal wheel, keyboard and real touch scroll gesture.
  await c.js("document.querySelector('#branch-viewport').scrollTo({left:0,top:0,behavior:'instant'})")
  box=await c.box('#branch-viewport')
  await c.call('Input.dispatchMouseEvent',{'type':'mouseWheel','x':box['x']+box['width']/2,'y':box['y']+8,'deltaX':250,'deltaY':0})
  await c.until("document.querySelector('#branch-viewport').scrollLeft>100")
  await c.js("document.querySelector('#branch-viewport').scrollTo({left:0,top:0,behavior:'instant'})")
  await c.call('Emulation.setTouchEmulationEnabled',{'enabled':True})
  await c.call('Input.synthesizeScrollGesture',{'x':box['x']+box['width']/2,'y':box['y']+8,'xDistance':-250,'yDistance':0,'gestureSourceType':'touch','speed':500})
  await c.until("document.querySelector('#branch-viewport').scrollLeft>80")
  await c.call('Emulation.setTouchEmulationEnabled',{'enabled':False})
  # No generation on navigation/reload; graph and complete history remain stable.
  positions=await c.js("Object.fromEntries(Array.from(document.querySelectorAll('.generation-group'),n=>[n.dataset.job,{depth:+n.dataset.depth,column:+n.dataset.column,row:+n.dataset.row}]))")
  await visit('canvas','?project='+pid)
  assert await groups()==[root,child,grand,sibling,second,failed]
  restored=await c.js("Object.fromEntries(Array.from(document.querySelectorAll('.generation-group'),n=>[n.dataset.job,[+n.dataset.depth,+n.dataset.column,+n.dataset.row]]))")
  assert all(restored[jid]==[positions[jid]['depth'],positions[jid]['column'],positions[jid]['row']] for jid in positions)
  # Parent unavailable during reuse must require a deliberate new source context.
  request=urllib.request.Request('http://127.0.0.1:8767/__remove_fixture_clip/'+child+'/4',method='POST',data=b'')
  urllib.request.urlopen(request).close()
  await visit('canvas','?project='+pid)
  await c.click('[data-history-id="'+grand+'"] .history-reuse')
  assert 'Source context required' in await c.js("document.querySelector('#prompt-source-context').textContent")
  await c.click('#generate-clip');assert len(await groups())==6
  assert 'valid parent' in await c.js("document.querySelector('#status').textContent")
  await c.click('#cancel-followup')
  # Saved parent metadata alone does not mask an unavailable media preview.
  await c.call('Network.enable')
  await c.call('Network.setBlockedURLs',{'urls':['http://127.0.0.1:8767/clips/'+child+'/clip_1.mp4']})
  await c.click('[data-history-id="'+failed+'"] .history-reuse')
  await c.until("document.querySelector('#prompt-source-context').textContent.includes('Parent preview unavailable')")
  await c.click('#generate-clip');assert len(await groups())==6
  await c.call('Network.setBlockedURLs',{'urls':[]})
  await c.click('#cancel-followup')
  await c.click('[data-history-id="'+root+'"] .history-reuse')
  assert await c.js("document.querySelector('#clip-count').value")=='1'
  assert len(await groups())==6
  reused=await submit('Reviewed reused full-video prompt',1,7)
  assert reused!=root
  strip=await c.js("Array.from(document.querySelectorAll('.generation-group'),n=>({left:n.offsetLeft,top:n.offsetTop}))")
  assert len(set(node['top'] for node in strip))==1
  assert all(a['left']<b['left'] for a,b in zip(strip,strip[1:]))
  await c.js("document.querySelector('#branch-viewport').scrollTo({left:0,top:0,behavior:'instant'})")
  box=await c.box('#branch-viewport');scroll=await c.js('({x:scrollX,y:scrollY})')
  picture=await c.call('Page.captureScreenshot',{'format':'png','clip':{'x':box['x']+scroll['x'],'y':box['y']+scroll['y'],'width':box['width'],'height':box['height'],'scale':1},'captureBeyondViewport':True})
  Path('/tmp/cascade-horizontal-branches.png').write_bytes(base64.b64decode(picture['data']))
  # Small-screen width is bounded; clip lists scroll inside columns.
  await c.call('Emulation.setDeviceMetricsOverride',{'width':480,'height':850,'deviceScaleFactor':1,'mobile':False})
  await asyncio.sleep(.3)
  assert await c.js('document.documentElement.scrollWidth<=innerWidth+1')
  assert await c.js("(()=>{const g=document.querySelector('[data-job=\""+child+"\"]');return g.scrollHeight>g.clientHeight && getComputedStyle(g).overflowY==='auto'})()")
  # Editor playback from root and deeper saved generations.
  for jid in [root,grand]:
   await visit('editor','?project='+pid+'&job='+jid+'&clip=0')
   await c.until("document.querySelector('#editor-video').readyState>=2")
   await c.click('#preview-play');await c.until("!document.querySelector('#editor-video').paused")
   await c.click('#preview-play')
  await visit('projects');c.accept_dialog=True
  await c.click('.project-card:last-child .project-delete');await c.until("document.querySelectorAll('.project-card').length===1")
  response=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8767/api/projects/'+'f'*32+'/generations',headers={'Authorization':'Bearer groups-browser-fixture'}))
  remaining=json.load(response)['groups'];assert len(remaining)==1 and remaining[0]['prompt']=='Other project history'
  print('Chrome passed: unique single-row rightward columns for parents/children/siblings/full-video requests and connectors, pending column identity and auto-scroll without page movement, wheel/touch navigation, history jump/reuse, missing-parent context, retry without duplicate history/groups, reload, mobile width, column scrolling, editor playback and isolated project/history deletion.')

if __name__=='__main__':asyncio.run(main())
