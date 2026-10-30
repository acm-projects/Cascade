"""Responsive editor checks against the isolated editor_browser_server fixture."""

from browser_support import require_browser_tests
require_browser_tests()
import asyncio
import base64
import json
from pathlib import Path
import urllib.request

from tests.test_editor_browser import Chrome


async def main():
    import websockets

    artifacts = Path('/tmp/cascade-editor-layout-artifacts')
    artifacts.mkdir(exist_ok=True)
    target = next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type'] == 'page')
    async with websockets.connect(target['webSocketDebuggerUrl'], origin='http://localhost:9333', max_size=None) as ws:
        c = Chrome(ws)
        await c.call('Runtime.enable')
        await c.call('Page.enable')
        await c.call('Page.navigate', {'url': 'http://127.0.0.1:8767/__exports_test/editor?project=' + '9' * 32})
        await c.until('!!window.siteReady')
        await c.js('window.siteReady')
        await c.until("document.querySelector('#editor-video').readyState>=2")
        for width in (1440, 1024, 768, 390):
            await c.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            await c.js('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            assert await c.js('document.documentElement.scrollWidth<=innerWidth'), width
            assert await c.js("document.querySelectorAll('#editor-sessions .mini-clip.active[aria-current=true]').length===1"), width
            assert await c.js("!!document.querySelector('#research-tab')&&!!document.querySelector('#research-panel #settings-form')"), width
            # Labels must stay on a single line without overflowing their row.
            assert await c.js("[...document.querySelectorAll('#editor-sessions summary span,#editor-sessions .mini-clip')].every(e=>e.scrollWidth<=e.clientWidth+1)"), width
            await c.click('#ratio-tab')
            assert await c.js("document.querySelector('#ratio-panel').checkVisibility()&&!document.querySelector('#chat-panel').checkVisibility()"), width
            await c.click('#chat-tab')
            if width > 950:
                assert await c.js("document.querySelector('.mini-canvas').getBoundingClientRect().right<=document.querySelector('.editor-center').getBoundingClientRect().left"), width
                assert await c.js("document.querySelector('.editor-center').getBoundingClientRect().right<=document.querySelector('.editor-controls').getBoundingClientRect().left"), width
            await c.js('scrollTo(0,0)')
            shot = await c.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True})
            (artifacts / f'editor-{width}.png').write_bytes(base64.b64decode(shot['data']))
        await c.click('#research-tab')
        assert await c.js("document.querySelector('#research-topic').checkVisibility()")
        await c.click('#chat-tab')
        assert not c.errors, c.errors
        print('PASS: 1440/1024/768/390px layouts, no horizontal overflow, readable hierarchy, selected clip, tool tabs, Research Agent tab, desktop column placement.')


if __name__ == '__main__':
    asyncio.run(main())
