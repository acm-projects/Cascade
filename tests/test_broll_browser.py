"""Headless Chrome + isolated editor_browser_server; no live provider/AI calls."""

from browser_support import require_browser_tests
require_browser_tests()
import asyncio
import json
import urllib.request
from tests.test_editor_browser import Chrome

async def main():
    import websockets
    targets=json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list'))
    target=next(t for t in targets if t['type']=='page')
    async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None,origin='http://localhost:9333') as ws:
        c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
        await c.call('Emulation.setDeviceMetricsOverride',{'width':1366,'height':1000,'deviceScaleFactor':1,'mobile':False})
        await c.call('Page.navigate',{'url':'about:blank'})
        await c.until("location.href==='about:blank'");await asyncio.sleep(.5)
        await c.call('Storage.clearDataForOrigin',{'origin':'http://127.0.0.1:8767','storageTypes':'local_storage'})
        urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8767/__editor_reset',data=b'',method='POST')).close()
        await c.call('Page.navigate',{'url':'http://127.0.0.1:8767/__editor_test?project='+'d'*32+'&job='+'a'*32+'&clip=0'})
        await c.until('!!window.editorReady');await c.js('window.editorReady')
        await c.until("document.getElementById('editor-video').readyState>=2")
        await c.js("document.querySelector('[data-tab=broll]').click();document.getElementById('broll-query').value='mountains';document.getElementById('broll-search-form').requestSubmit()")
        await c.until("document.querySelectorAll('.broll-result').length===1&&!document.getElementById('broll-search').disabled")
        await c.js("document.querySelector('.broll-result button').click()")
        await c.until("!document.getElementById('broll-add').disabled")
        await c.input('broll-start',1);await c.input('broll-duration',2);await c.input('broll-offset',.5)
        await c.js("document.getElementById('broll-add').click()")
        await c.until("document.querySelectorAll('.broll-track-segment').length===1")
        await c.js("document.getElementById('editor-video').currentTime=1.5")
        await c.until("!document.getElementById('broll-live').hidden&&!document.getElementById('broll-live').seeking")
        assert await c.js("document.getElementById('broll-live').muted")
        assert abs(await c.js("document.getElementById('broll-live').currentTime")-1)<.06
        # Scrub out and back; comparison suppresses B-roll without changing state.
        await c.js("document.getElementById('editor-video').currentTime=3.5")
        await c.until("document.getElementById('broll-live').hidden")
        await c.js("document.getElementById('editor-video').currentTime=1.5")
        await c.until("!document.getElementById('broll-live').hidden")
        await c.js("document.getElementById('preview-original').click()")
        await c.until("document.getElementById('broll-live').hidden")
        await c.js("document.getElementById('preview-edited').click()")
        await c.until("!document.getElementById('broll-live').hidden")
        await c.js("document.getElementById('undo').click()")
        await c.until("document.querySelectorAll('.broll-track-segment').length===0")
        await c.js("document.getElementById('redo').click()")
        await c.until("document.querySelectorAll('.broll-track-segment').length===1")
        # Numeric edit and replacement use the same segment identity.
        await c.js("document.querySelector('.broll-track-segment').click()")
        await c.input('broll-duration',1.5);await c.js("document.getElementById('broll-timing-form').requestSubmit()")
        await c.until("document.getElementById('broll-status').textContent==='B-roll timing updated.'")
        await c.js("document.getElementById('broll-replace').click()")
        await c.until("document.getElementById('broll-status').textContent==='B-roll replaced.'")
        await c.until("document.getElementById('save-status').textContent==='Saved'")
        await c.call('Page.reload');await c.until('!!window.editorReady');await c.js('window.editorReady')
        await c.until("document.querySelectorAll('.broll-track-segment').length===1")
        assert await c.js("document.getElementById('undo').disabled") # stacks are session-only
        # Switching clips restores the correct stock track and in-memory history.
        await c.js("document.querySelectorAll('#editor-sessions button')[1].click()")
        await c.until("document.getElementById('editor-clip-title').textContent.includes('Session 2')&&!document.getElementById('chat-send').disabled")
        assert await c.js("document.querySelectorAll('.broll-track-segment').length===0")
        await c.js("document.querySelectorAll('#editor-sessions button')[0].click()")
        await c.until("document.querySelectorAll('.broll-track-segment').length===1&&!document.getElementById('chat-send').disabled")
        # Mocked AI searches only, then explicit insertion; remove uses selected context.
        async def chat(text):
            await c.js("document.getElementById('chat-input').value="+json.dumps(text)+";document.getElementById('chat-form').requestSubmit()")
            await c.until("!document.getElementById('chat-send').disabled")
        await chat('find stock')
        assert await c.js("document.querySelectorAll('.broll-track-segment').length===1")
        await chat('add stock')
        await c.until("document.querySelectorAll('.broll-track-segment').length===2")
        await c.js("document.querySelectorAll('.broll-track-segment')[1].click()")
        await chat('remove stock')
        await c.until("document.querySelectorAll('.broll-track-segment').length===1")
        await c.js("document.getElementById('undo').click()")
        await c.until("document.querySelectorAll('.broll-track-segment').length===2")
        # Playback synchronization within stock, then returning to main footage.
        await c.js("document.getElementById('editor-video').currentTime=4.3")
        await c.until("!document.getElementById('broll-live').hidden")
        await c.click("#preview-play")
        await c.until("!document.getElementById('broll-live').paused")
        await asyncio.sleep(.5)
        assert await c.js("Math.abs(document.getElementById('broll-live').currentTime-(document.getElementById('editor-video').currentTime-4))<.2")
        await c.click("#preview-play")
        await c.until("document.getElementById('broll-live').paused")
        assert not c.errors,c.errors
        print('B-roll browser checks passed: search, preview, insert, seek, comparison, timing, replace, persistence, switching, AI context, undo/redo and playback sync')

if __name__=='__main__':asyncio.run(main())
