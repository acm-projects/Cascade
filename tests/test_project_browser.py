"""Real Chrome UI with project_browser_server.py. Selection/identity are fixtures;
HTTP persistence, original-source cutting, playable media and editor are real.
"""
import asyncio
import json
import time
import urllib.request
from test_editor_browser import Chrome


class ProjectChrome(Chrome):
    accept_dialog = True
    async def call(self,method,params=None):
        self.seq+=1;seq=self.seq
        await self.ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
        while True:
            message=json.loads(await self.ws.recv())
            if message.get('method')=='Page.javascriptDialogOpening':
                self.seq+=1
                await self.ws.send(json.dumps({'id':self.seq,'method':'Page.handleJavaScriptDialog','params':{'accept':self.accept_dialog}}))
            if message.get('method')=='Runtime.exceptionThrown':self.errors.append(message['params'])
            if message.get('id')==seq:
                if 'error' in message:raise RuntimeError(message['error'])
                return message.get('result',{})


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
        await visit('canvas','?project='+pid)
        assert await c.js("document.querySelector('#clip-count').value")=='4'
        assert await c.js("document.querySelectorAll('.generation-group').length")==1
        await c.input('search-engine','visual')
        await c.input('clip-count','0');await c.input('clip-prompt','Invalid count');await c.click('#generate-clip')
        assert 'whole number' in await c.js("document.querySelector('#status').textContent")
        async def generate(prompt,count,groups):
            await c.input('search-engine','visual');await c.input('clip-count',str(count));await c.input('clip-prompt',prompt);await c.click('#generate-clip')
            await c.until("!document.querySelector('#generate-clip').disabled && document.querySelectorAll('.generation-group').length==="+str(groups),30)
        await generate('Five suitable moments',5,2)
        assert await c.js("document.querySelectorAll('.generation-group:last-child .clip-placeholder').length")==5
        await generate('Another ordinary prompt',2,3)
        assert await c.js("document.querySelectorAll('.generation-group:nth-child(2) .clip-placeholder').length")==5
        # Branch from a clip in the earlier five-clip group.
        await c.click('.generation-group:nth-child(2) .clip-placeholder:nth-child(2) button')
        assert not await c.js("document.querySelector('#followup-parent').hidden")
        await c.click('#cancel-followup');assert await c.js("document.querySelector('#followup-parent').hidden")
        await c.click('.generation-group:nth-child(2) .clip-placeholder:nth-child(2) button')
        await generate('Expand this moment before and after it',4,4)
        assert '1 of 4' in await c.js("document.querySelector('.generation-group:last-child').textContent")
        await c.click('.generation-group:last-child .clip-placeholder button')
        await generate('Find related moments',3,5)
        # Reload restores all groups and the parent relationship.
        await visit('canvas','?project='+pid)
        assert await c.js("document.querySelectorAll('.generation-group').length")==5
        assert 'Builds on' in await c.js("document.querySelector('.generation-group:last-child').textContent")
        for selector in ['.generation-group:nth-child(2) .clip-placeholder:nth-child(5) a','.generation-group:last-child .clip-placeholder a']:
            href=await c.js('document.querySelector('+json.dumps(selector)+').getAttribute("href")')
            await visit('editor','?'+href.split('?',1)[1])
            await c.until("document.querySelector('#editor-video').readyState>=2")
            await c.click('#preview-play');await c.until("!document.querySelector('#editor-video').paused")
            await c.click('#preview-play')
            await visit('canvas','?project='+pid)
        await c.input('search-engine','visual')
        await generate('Fail fixture',4,6)
        assert 'Fixture provider failure' in await c.js("document.querySelector('.generation-group:last-child').textContent")
        assert await c.js("document.querySelectorAll('.generation-group:nth-child(2) .clip-placeholder').length")==5
        await visit('projects')
        assert await c.js("document.querySelectorAll('.project-card').length")==2
        # Actual native confirmation dialog: cancel, then accept.
        c.accept_dialog=False;await c.click('.project-card:last-child .project-delete')
        assert await c.js("document.querySelectorAll('.project-card').length")==2
        c.accept_dialog=True;await c.click('.project-card:last-child .project-delete')
        await c.until("document.querySelectorAll('.project-card').length===1")
        await visit('projects');assert await c.js("document.querySelectorAll('.project-card').length")==1
        assert 'Keep this project' in await c.js("document.querySelector('.project-card').textContent")
        # A stale editor/canvas project URL returns to the existing projects page.
        await c.call('Page.navigate',{'url':'http://127.0.0.1:8767/__site/canvas?project='+pid})
        await c.until("location.pathname==='/projects_C.html'")
        print('Chrome passed: counts including five, retained ordinary groups, follow-up/cancel, original-source expansion, child follow-up, reload, editor playback across groups, failed group isolation, native deletion cancel/confirm, persistent deletion, and stale-project redirect.')

if __name__=='__main__':asyncio.run(main())
