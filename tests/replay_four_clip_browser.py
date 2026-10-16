"""Real canvas/editor browser check using replay_saved_generation.py artifacts.
Temporary identity bootstrap only; production source/authentication stays intact.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from fastapi.responses import HTMLResponse,Response
import uvicorn
import app1
from test_editor_browser import Chrome


async def verify(root):
    import websockets
    report=json.loads((root/'verification.json').read_text())
    app1.JOBS_DIR=root
    def identity(token):
        if token!='replay-fixture': raise HTTPException(401,'Fixture token required')
        return 'clip-replay-user'
    app1.verify_clerk_token=identity
    app1.authorized_parties=lambda:['http://127.0.0.1:8768']
    @app1.app.middleware('http')
    async def fixture_frontend(request,call_next):
        if request.url.path in ('/canvas_C.html','/editor_C.html'):
            html=(app1.PROJECT_DIR/request.url.path.lstrip('/')).read_text()
            return HTMLResponse(html.replace('<script src="flow_C.js"></script>','<script src="/__replay_flow.js"></script>'))
        return await call_next(request)
    @app1.app.get('/__replay_flow.js')
    def fixture_flow():
        source=(app1.PROJECT_DIR/'flow_C.js').read_text()
        bootstrap='''
          userId='clip-replay-user'; window.Clerk={session:{getToken:async()=>'replay-fixture'}};
          window.fixtureReady=(async()=>{
            $('protected-page').hidden=false; await loadProject();
            if(page==='canvas') await initializeCanvas(); else await initializeEditor();
          })();
        '''
        assert source.count('  start();')==1
        return Response(source.replace('  start();',bootstrap),media_type='text/javascript')
    server=uvicorn.Server(uvicorn.Config(app1.app,host='127.0.0.1',port=8768,log_level='warning'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    with tempfile.TemporaryDirectory(prefix='cascade-count-browser-') as profile:
        binary='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        with (root/'browser.log').open('w') as log:
            browser=subprocess.Popen([binary,'--headless=new','--no-first-run','--disable-background-networking','--remote-debugging-port=9334','--remote-allow-origins=http://localhost:9334','--user-data-dir='+profile,'about:blank'],stdout=log,stderr=log)
            try:
                targets=None
                for _ in range(100):
                    try:
                        targets=json.load(urllib.request.urlopen('http://127.0.0.1:9334/json/list'));break
                    except OSError: await asyncio.sleep(.1)
                assert targets,'Chrome did not start'
                target=next(t for t in targets if t['type']=='page')
                async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9334',max_size=None) as ws:
                    c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
                    await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
                    url='http://127.0.0.1:8768/canvas_C.html?project='+report['project_id']+'&job='+report['job_id']
                    await c.call('Page.navigate',{'url':url});await c.until('!!window.fixtureReady');await c.js('window.fixtureReady')
                    await c.until("document.querySelectorAll('.clip-group video').length===4 && [...document.querySelectorAll('.clip-group video')].every(v=>v.readyState>=2)")
                    screenshot=await c.call('Page.captureScreenshot',{'format':'png'});(root/'canvas.png').write_bytes(base64.b64decode(screenshot['data']))
                    await c.click('.clip-group article:nth-child(4) input')
                    assert await c.js("new URL(document.querySelector('#open-editor').href).searchParams.get('clip')")=='3'
                    await c.click('#open-editor')
                    await c.until("location.pathname==='/editor_C.html' && !!window.fixtureReady");await c.js('window.fixtureReady')
                    await c.until("document.querySelector('#editor-video').readyState>=2")
                    assert await c.js("document.querySelectorAll('#editor-sessions button').length")==4
                    assert await c.js("document.querySelector('#editor-clip-title').textContent")=='Session 1 · Clip 4'
                    await c.until("document.querySelector('#save-status').textContent==='Saved'")
                    screenshot=await c.call('Page.captureScreenshot',{'format':'png'});(root/'editor-clip4.png').write_bytes(base64.b64decode(screenshot['data']))
                    assert not c.errors,c.errors
                    print('Chrome: actual API clips=4; canvas cards=4, all videos playable; radio 4 links clip=3; editor Session 1 · Clip 4 playable, sidebar clips=4. Identity bootstrap mocked; media/API/rendered clips real.')
                    print('Screenshots:',root)
            finally:
                browser.terminate();browser.wait(timeout=15)
                server.should_exit=True;thread.join(timeout=10)

if __name__=='__main__': asyncio.run(verify(Path(sys.argv[1]).resolve()))
