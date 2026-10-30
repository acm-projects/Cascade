"""Opt-in React integration check against advanced_editor_browser_server.py.

Uses an isolated fixture identity/media and real saves, previews and MP4/ZIP
renders. AI/stock are fixtures; no OAuth, research or publishing calls are made.
"""
from tests.browser_support import require_browser_tests
require_browser_tests()
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import websockets

sys.path.insert(0, str(Path(__file__).parent))
from tests.test_editor_browser import Chrome


async def main():
    origin = 'http://127.0.0.1:' + os.getenv('CASCADE_FIXTURE_PORT', '18771')
    pid, jid = 'd'*32, 'a'*32
    endpoint = origin + f'/api/projects/{pid}/editor/{jid}/0'
    output = Path(tempfile.mkdtemp(prefix='cascade-merged-browser-', dir='/private/tmp'))
    pages = json.load(urllib.request.urlopen('http://127.0.0.1:9333/json'))
    async with websockets.connect(next(page for page in pages if page.get('type') == 'page')['webSocketDebuggerUrl'], max_size=30_000_000) as ws:
        c = Chrome(ws)
        await c.call('Page.enable'); await c.call('Runtime.enable')
        await c.call('Browser.setDownloadBehavior', {'behavior':'allow', 'downloadPath':str(output)})
        await c.call('Emulation.setDeviceMetricsOverride', {'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
        await c.call('Page.navigate', {'url':origin+f'/projects/{pid}/editor'})
        await c.until("!!document.querySelector('.clip-player-video')")

        async def press(text):
            await c.js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+");if(!b||b.disabled)throw Error('Missing or disabled '+"+json.dumps(text)+");b.click()})()")

        await press('Captions')
        await c.until("!!document.querySelector('.captions-tab') || !!document.querySelector('.captions-presets') || !!document.querySelector('select')")
        # Remote preset + local animation work in the same persisted state.
        await c.js("[...document.querySelectorAll('.captions-preset')].find(b=>b.textContent.includes('Bold pop')).click()")
        await c.js("(()=>{const e=[...document.querySelectorAll('select')].find(e=>[...e.options].some(o=>o.value==='karaoke'));e.value='karaoke';e.dispatchEvent(new Event('change',{bubbles:true}))})()")
        await c.until("document.querySelector('.editor-save').textContent.includes('Saved')",30)
        await press('Aspect Ratio')
        await c.until("!!document.querySelector('.aspect-tab') || !!document.querySelector('.aspect-presets') || document.body.textContent.includes('9:16')")
        await press('Trends')
        await c.until("!!document.querySelector('[role=dialog]')")
        before = json.load(urllib.request.urlopen(endpoint))['draft']['state']
        await c.call('Input.dispatchKeyEvent', {'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
        await c.until("!document.querySelector('[role=dialog]')")
        assert json.load(urllib.request.urlopen(endpoint))['draft']['state'] == before
        await press('Go to Export →')
        await c.until("!!document.querySelector('.export-tree') && !!document.querySelector('.export-player video')")
        assert await c.js("!!document.querySelector('.export-stack') && !!document.querySelector('.export-pager')")
        await press('Trends · YouTube research')
        await c.until("!!document.querySelector('[role=dialog]')")
        await c.call('Input.dispatchKeyEvent', {'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
        await c.until("!document.querySelector('[role=dialog]')")
        await c.js("window.exportBodies=[];const original=window.fetch;window.fetch=(url,options)=>{if(String(url).endsWith('/export')||String(url).endsWith('/export-selected'))window.exportBodies.push(JSON.parse(options.body));return original(url,options)}")
        await press('Download this clip')
        for _ in range(600):
            media = list(output.glob('*.mp4'))
            if media: break
            await asyncio.sleep(.1)
        assert media, 'MP4 download missing'
        sent = await c.js('window.exportBodies[0]')
        assert sent['captions'] == before['captions']
        assert sent['motion'] == before['motion'] and sent['audio'] == before['audio']
        await press('Download selected clips (1)')
        for _ in range(600):
            archives = list(output.glob('*.zip'))
            if archives: break
            await asyncio.sleep(.1)
        assert archives, 'ZIP download missing'
        with zipfile.ZipFile(archives[0]) as archive:
            entries = [n for n in archive.namelist() if n.endswith('.mp4')]
            assert len(entries) == 1
            zipped = output/'zip-selected.mp4'; zipped.write_bytes(archive.read(entries[0]))
        def frame(path):
            return subprocess.check_output(['ffmpeg','-v','error','-ss','1','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        assert frame(media[0]) == frame(zipped), 'ZIP and single export differ'
        await c.call('Page.reload')
        await c.until("!!document.querySelector('.export-tree')")
        assert json.load(urllib.request.urlopen(endpoint))['draft']['state'] == before
        await c.call('Emulation.setDeviceMetricsOverride', {'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
        await asyncio.sleep(.3)
        assert await c.js('document.documentElement.scrollWidth<=innerWidth+1'), 'Mobile overflow'
        assert await c.js("document.querySelector('.export-main').getBoundingClientRect().width>300 && document.querySelector('.export-actions').getBoundingClientRect().right<=innerWidth+1"), 'Mobile content clipped'
        assert await c.js("document.querySelector('.topnav-steps').getBoundingClientRect().right<=innerWidth+1"), 'Navigation clipped'
        screenshot = await c.call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
        (output/'exports-mobile.png').write_bytes(base64.b64decode(screenshot['data']))
        assert not c.errors, c.errors
        print('PASS: caption presets + animation, aspect controls, Trends read-only in Editor/Exports, navigation/save/reload, new Exports layout, real MP4/ZIP matching decoded frames, mobile. Artifacts:',output)


if __name__ == '__main__':
    asyncio.run(main())
