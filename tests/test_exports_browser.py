"""Real Chrome + FFmpeg workflow against editor_browser_server.py; no paid APIs."""

from browser_support import require_browser_tests
require_browser_tests()
import asyncio
import json
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from tests.test_editor_browser import Chrome

ARTIFACTS=Path('/tmp/cascade-exports-browser-artifacts')
PID='d'*32

async def main():
    import websockets
    ARTIFACTS.mkdir(exist_ok=True)
    for path in ARTIFACTS.glob('*'):
        if path.is_file():path.unlink()
    target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
    async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None,origin='http://localhost:9333') as ws:
        c=Chrome(ws);await c.call('Page.enable');await c.call('Runtime.enable')
        await c.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
        await c.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
        await c.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(ARTIFACTS)})
        await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'");await asyncio.sleep(.3)
        await c.call('Storage.clearDataForOrigin',{'origin':'http://127.0.0.1:8767','storageTypes':'local_storage'})
        urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8767/__editor_reset',data=b'',method='POST')).close()
        await c.call('Page.navigate',{'url':f'http://127.0.0.1:8767/__editor_test?project={PID}'})
        await c.until('!!window.editorReady');await c.js('window.editorReady');await c.until("document.querySelector('#editor-video').readyState>=2")
        assert await c.js("[...document.querySelectorAll('[data-tab]')].map(e=>e.textContent.trim()).join('|')")=='Chat|Captions|Video|B-roll|Research Agent|Effects'
        assert await c.js("document.querySelector('.trim-inputs').getBoundingClientRect().height===0&&document.querySelector('#trim-summary').getBoundingClientRect().height===0&&document.querySelector('#thumbnail-status').classList.contains('sr-only')")
        await c.click('#captions-tab')
        assert await c.js("document.querySelector('#cap-size').getBoundingClientRect().height===0&&document.querySelector('#cap-text').getBoundingClientRect().height===0")
        await c.input('caption-preset','bold');await c.input('cap-color','#ffff00')
        await c.click('#effects-tab');await c.input('effect-grayscale','')
        await c.js("document.querySelector('#effect-grayscale').checked=true;document.querySelector('#effect-grayscale').dispatchEvent(new Event('input'));document.querySelector('#effect-grayscale').dispatchEvent(new Event('change'))")
        await c.input('effect-brightness','1.15')
        assert await c.js("document.querySelector('#footage-layer').style.filter.includes('grayscale(1)')")
        await c.click('#undo');assert await c.js("document.querySelector('#effect-brightness').value")=='1'
        await c.click('#redo');assert await c.js("document.querySelector('#effect-brightness').value")=='1.15'
        await c.click('#preview-original');assert await c.js("document.querySelector('#footage-layer').style.filter")=='none'
        await c.click('#preview-edited');await c.click('#ratio-tab');await c.click('[data-ratio="1:1"]')
        await c.input('trim-start','1');await c.input('trim-end','5')
        await c.click('#broll-tab');await c.input('broll-query','mountains');await c.click('#broll-search');await c.until("!!document.querySelector('#broll-results button')")
        await c.click('#broll-results button');await c.until("!document.querySelector('#broll-add').disabled")
        await c.click('#broll-add');await c.until("!!document.querySelector('#broll-segments button')")
        await c.until("document.querySelector('#save-status').textContent==='Saved'")
        await c.call('Page.reload');await c.until('!!window.editorReady');await c.js('window.editorReady');await c.until("document.querySelector('#effect-brightness').value==='1.15'")
        await c.call('Page.navigate',{'url':f'http://127.0.0.1:8767/__exports_test/canvas?project={PID}'})
        await c.until('!!window.siteReady');await c.js('window.siteReady')
        assert await c.js("document.querySelector('#export-selected')===null&&document.querySelector('.clip-export-select')===null")
        await c.call('Page.navigate',{'url':f'http://127.0.0.1:8767/__exports_test/editor?project={PID}'})
        await c.until('!!window.siteReady');await c.js('window.siteReady')
        await c.js("document.querySelectorAll('#editor-sessions .clip-nav-row input').forEach((e,i)=>{if([0,1,3].includes(i))e.click()})")
        assert await c.js("document.querySelector('#open-exports').textContent")=='Go to Exports (3) →'
        assert await c.js("document.querySelectorAll('#editor-sessions summary input:indeterminate').length")>=1
        await c.call('Page.reload');await c.until('!!window.siteReady');await c.js('window.siteReady')
        await c.until("document.querySelectorAll('#editor-sessions .clip-nav-row input:checked').length===3")
        await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':"const cascadeRealFetch=window.fetch;let cascadeFailPreview=true;window.fetch=(url,options)=>{if(cascadeFailPreview&&String(url).endsWith('/'+'b'.repeat(32)+'/2/export')){return Promise.resolve(new Response(JSON.stringify({detail:'Fixture preview failure'}),{status:503,headers:{'Content-Type':'application/json'}}));}return cascadeRealFetch(url,options);};"})
        await c.click('#open-exports');await c.until("document.body.dataset.page==='exports'&&!!window.siteReady");await c.js('window.siteReady')
        assert await c.js("document.querySelectorAll('#exports-tree .mini-clip').length")==3
        assert await c.js("document.querySelectorAll('.export-media-card').length")==3
        assert await c.js("document.querySelectorAll('.wave-album').length")==1
        assert await c.js("[...document.querySelectorAll('.wave-album')].every(e=>e.dataset.expanded==='false')")
        await c.click('.wave-stack')
        await c.until("document.querySelector('.export-media-card[data-active=true] video').readyState>=2",60)
        assert await c.js("document.querySelector('#export-position').textContent")=='1 of 3'
        await c.js("document.querySelector('.export-media-card[data-active=true] video').play()")
        await c.click('#export-next');await c.until("document.querySelector('#export-position').textContent==='2 of 3'")
        assert await c.js("document.querySelector('.export-media-card video').paused")
        await c.until("document.querySelector('.export-media-card[data-active=true] video').readyState>=2",60)
        await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowRight','code':'ArrowRight'});await c.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'ArrowRight','code':'ArrowRight'})
        await c.until("document.querySelector('#export-position').textContent==='3 of 3'")
        # Tile arrows navigate and snap the horizontal row.
        await c.click('.wave-album .wave-rail-prev')
        await c.until("document.querySelector('#export-position').textContent==='2 of 3'")
        await c.click('#export-prev');await c.until("document.querySelector('#export-position').textContent==='1 of 3'&&!document.querySelector('#download-active').disabled")
        assert await c.js("!document.querySelector('#export-youtube')&&document.querySelectorAll('.export-actions button').length===2")
        await c.until("!document.querySelectorAll('.export-preview-retry')[2].hidden",60)
        await c.js("cascadeFailPreview=false;document.querySelectorAll('.export-preview-retry')[2].click()")
        await c.until("document.querySelectorAll('.export-media-card video')[2].readyState>=2&&document.querySelectorAll('.export-preview-retry')[2].hidden",60)
        await c.click('#exports-tree .mini-clip');await c.until("document.querySelector('#export-position').textContent==='1 of 3'")
        await c.click('#download-active')
        for _ in range(200):
            if list(ARTIFACTS.glob('*.mp4')):break
            await asyncio.sleep(.1)
        mp4=next(ARTIFACTS.glob('*.mp4'))
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(mp4)]))
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        assert video['width']==video['height'],video
        assert any(s['codec_type']=='audio' for s in probe['streams'])
        assert abs(float(probe['format']['duration'])-4)<.15
        # The export has grayscale B-roll below yellow captions, plus uninterrupted audio.
        from PIL import Image, ImageStat
        import io
        frame=Image.open(io.BytesIO(subprocess.check_output(['ffmpeg','-v','error','-ss','0.6','-i',str(mp4),'-frames:v','1','-f','image2pipe','-vcodec','png','-']))).convert('RGB')
        center=frame.getpixel((frame.width//2,frame.height//2))
        assert max(center)-min(center)<6,center
        assert max(ImageStat.Stat(frame.crop((frame.width//3,frame.height//3,frame.width*2//3,frame.height//2))).stddev)<3
        assert sum(1 for r,g,b in frame.getdata() if r>180 and g>180 and b<80)>100
        await c.js("window.zipCalls=0;const originalFetch=window.fetch;window.fetch=(url,options)=>{if(String(url).endsWith('/export-selected'))window.zipCalls++;return originalFetch(url,options);}")
        await c.js("document.querySelectorAll('.export-card-check')[1].click()")
        assert await c.js("document.querySelector('#export-all').textContent==='Download selected clips (2)'")
        await c.click('#export-all')
        await c.js("document.querySelector('#export-all').click()")
        assert await c.js("document.querySelector('#export-all').disabled")
        for _ in range(600):
            if list(ARTIFACTS.glob('*.zip')):break
            await asyncio.sleep(.1)
        archive=next(ARTIFACTS.glob('*.zip'))
        with zipfile.ZipFile(archive) as zipped:
            assert len(zipped.namelist())==2
            assert 'clip-3-bbbbbbbb' in zipped.namelist()[-1]
        assert await c.js('window.zipCalls')==1
        assert not c.errors,c.errors
        screenshot=await c.call('Page.captureScreenshot',{'format':'png'})
        import base64
        (ARTIFACTS/'exports.png').write_bytes(base64.b64decode(screenshot['data']))
        print('PASS: effects/history/restore, simplified UI, editor tree selection/refresh, exact three-card exports, playback/pause, arrows/keyboard/swipe, edited MP4 (square/4s/audio/B-roll), subset ZIP, failed-preview retry, social destinations confined to posting panel; no JS exceptions.')

if __name__=='__main__':asyncio.run(main())
