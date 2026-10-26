"""Real Chrome framing/playback/export checks; requires editor_browser_server.py.
No paid calls. Test server replaces identity only and uses temporary real media.
"""
import asyncio
import base64
import io
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from PIL import Image,ImageChops,ImageStat
from tests.test_editor_browser import Chrome

ARTIFACTS=Path('/tmp/cascade-aspect-artifacts')

async def main():
    import websockets
    ARTIFACTS.mkdir(exist_ok=True)
    target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
    async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
        c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
        await c.call('Emulation.setDeviceMetricsOverride',{'width':1366,'height':1000,'deviceScaleFactor':1,'mobile':False})
        await c.call('Page.navigate',{'url':'about:blank'});await c.until("location.href==='about:blank'");await asyncio.sleep(.5)
        script=await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':"if(location.origin==='http://127.0.0.1:8767') localStorage.clear();"})
        urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8767/__editor_reset',method='POST',data=b'')).close()
        destination='http://127.0.0.1:8767/__editor_test?project='+'d'*32+'&run='+str(time.time_ns())
        await c.call('Page.navigate',{'url':destination});await c.until('location.href.startsWith('+json.dumps(destination)+') && !!window.editorReady');await c.js('window.editorReady')
        await c.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':script['identifier']})
        await c.until("document.querySelector('#editor-video').readyState>=2")
        await c.click('#ratio-tab')
        # Actual frame geometry changes, rather than just the preview workspace.
        ratios={'original':16/9,'9:16':9/16,'1:1':1,'4:5':4/5,'16:9':16/9,'4:3':4/3}
        for preset,ratio in ratios.items():
            await c.click('[data-ratio="'+preset+'"]')
            assert await c.js("document.querySelector('#device-shell').dataset.device")=={'9:16':'phone','4:3':'tablet','16:9':'desktop'}.get(preset,'clean')
            measurement=await c.js("(()=>{const f=document.querySelector('#composition-frame').getBoundingClientRect();const v=document.querySelector('#editor-video').getBoundingClientRect();return {ratio:f.width/f.height,videoRatio:v.width/v.height};})()")
            assert abs(measurement['ratio']-ratio)<.003,(preset,measurement)
            assert abs(measurement['videoRatio']-16/9)<.02,(preset,measurement)
            assert await c.js("document.querySelector('[data-ratio=\\\""+preset+"\\\"]').getAttribute('aria-pressed')")=='true'
        # Preview hardware is independent from output ratio and saved edits.
        for device, expected_ratio in [('phone',9/19.5),('tablet',4/3),('desktop',16/9),('tv',16/9),('clean',4/3)]:
            await c.input('preview-device',device)
            await asyncio.sleep(.3)
            measured=await c.js("(()=>{const s=document.querySelector('#device-screen').getBoundingClientRect();return {device:document.querySelector('#device-shell').dataset.device,ratio:s.width/s.height}})()")
            assert measured['device']==device and abs(measured['ratio']-expected_ratio)<.003,measured
        await c.input('preview-device','phone')
        for preset, ratio in [('1:1',1),('4:5',4/5)]:
            await c.click('[data-ratio="'+preset+'"]');await asyncio.sleep(.3)
            result=await c.js("(()=>{const s=document.querySelector('#device-screen').getBoundingClientRect(),f=document.querySelector('#composition-frame').getBoundingClientRect(),o=document.querySelector('#caption-overlay').getBoundingClientRect();return {screen:s.width/s.height,output:f.width/f.height,space:s.height-f.height,overlay:Math.abs(o.width-f.width)+Math.abs(o.height-f.height)}})()")
            assert abs(result['screen']-9/19.5)<.003 and abs(result['output']-ratio)<.003 and result['space']>20 and result['overlay']<1,result
        await c.input('preview-device','auto')
        await c.click('[data-ratio="9:16"]');await c.input('frame-background','#334455')
        fit=await c.js("({frame:document.querySelector('#composition-frame').getBoundingClientRect().toJSON(),video:document.querySelector('#editor-video').getBoundingClientRect().toJSON(),background:getComputedStyle(document.querySelector('#composition-frame')).backgroundColor})")
        assert fit['video']['height']<fit['frame']['height'] and fit['background']=='rgb(51, 68, 85)'
        await c.input('framing','fill')
        await c.until("document.querySelector('#reframe-status').textContent.includes('ready')&&!document.querySelector('#chat-send').disabled",90)
        assert await c.js("!document.querySelector('#crop-x')&&!document.querySelector('#crop-y')&&!document.querySelector('#follow-speaker')")
        assert await c.js("document.querySelector('#reframe-status').textContent.includes('No usable faces')")
        await c.click('#undo');assert await c.js("document.querySelector('#framing').value==='fit'")
        await c.click('#redo');assert await c.js("document.querySelector('#framing').value==='fill'")
        # Captions are rasterized in the new output frame, not cropped with the source.
        await c.click('#captions-tab');await c.input('cap-position','top');await c.input('cap-color','#ffff00');await c.input('cap-size','42');await c.input('caption-cue','0')
        assert await c.js("document.querySelector('#caption-overlay').width")==360
        assert await c.js("document.querySelector('#caption-overlay').height")==640
        bounds=await c.js("(()=>{let c=document.querySelector('#caption-overlay'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data,ys=[];for(let i=3;i<d.length;i+=4)if(d[i])ys.push(Math.floor(i/4/c.width));return {top:Math.min(...ys),bottom:Math.max(...ys)}})()")
        assert 30<bounds['top']<100 and bounds['bottom']<150,bounds
        await c.input('trim-start','1');await c.input('trim-end','2')
        # Main play control is actually beneath the preview and drives real media.
        button=await c.box('#preview-play');stage=await c.box('#preview-wrap');assert button['y']>=stage['y']+stage['height']
        await c.click('#preview-play');await c.until("!document.querySelector('#editor-video').paused && document.querySelector('#preview-play').textContent.includes('Pause')")
        assert 'Pause' in await c.js("document.querySelector('#preview-play').textContent")
        sync=await c.js("(()=>{const v=document.querySelector('#editor-video'),t=document.querySelector('#timeline-content');return {media:v.currentTime,timeline:parseFloat(t.style.getPropertyValue('--playhead'))/(t.getBoundingClientRect().width/8)}})()")
        assert abs(sync['media']-sync['timeline'])<.1,sync
        await c.until("document.querySelector('#editor-video').paused && document.querySelector('#editor-video').currentTime>=1.99",5)
        assert abs(await c.js("document.querySelector('#editor-video').currentTime")-2)<.03
        await c.click('#preview-play');await c.until("!document.querySelector('#editor-video').paused && document.querySelector('#preview-play').textContent.includes('Pause')")
        assert await c.js("document.querySelector('#editor-video').currentTime")<1.4
        await c.click('#preview-play');assert await c.js("document.querySelector('#editor-video').paused")
        state_key='cascade-editor:v1:editor-browser-user:'+'d'*32+':'+'a'*32+':0'
        before=await c.js('JSON.parse(localStorage.getItem('+json.dumps(state_key)+')).state')
        await c.click('#preview-original');assert await c.js("document.querySelector('#caption-overlay').hidden")
        original=await c.js("(()=>{let r=document.querySelector('#composition-frame').getBoundingClientRect();return r.width/r.height})()")
        assert abs(original-16/9)<.003
        await c.click('#preview-edited')
        assert await c.js('JSON.parse(localStorage.getItem('+json.dumps(state_key)+')).state')==before
        # Download through Exports, then inspect the encoded file.
        await c.call('Page.setDownloadBehavior',{'behavior':'allow','downloadPath':str(ARTIFACTS)})
        for mode in ['fit','fill']:
            await c.click('#ratio-tab');await c.input('framing',mode)
            await c.until("!document.querySelector('#chat-send').disabled",90)
            await c.js("(async()=>{const v=document.querySelector('#editor-video');await new Promise(r=>{v.addEventListener('seeked',r,{once:true});v.currentTime=1.5})})()")
            await c.js('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
            expected=await c.js("""(()=>{const s=JSON.parse(localStorage.getItem(KEY)).state;const g=CascadeEditorState.compositionGeometry(640,360,s.composition);const canvas=document.createElement('canvas');canvas.width=g.width;canvas.height=g.height;const ctx=canvas.getContext('2d');ctx.fillStyle=s.composition.background;ctx.fillRect(0,0,g.width,g.height);const fill=s.composition.mode==='fill';ctx.drawImage(document.querySelector('#editor-video'),fill?-g.x:g.x,fill?-g.y:g.y,g.scaledWidth,g.scaledHeight);ctx.drawImage(document.querySelector('#caption-overlay'),0,0);return canvas.toDataURL('image/png').split(',')[1];})()""".replace('KEY',json.dumps(state_key)))
            (ARTIFACTS/(mode+'-expected.png')).write_bytes(base64.b64decode(expected))
            download=ARTIFACTS/'cascade-session-1-wave-1-clip-1.mp4'
            if download.exists():download.unlink()
            await c.until("document.querySelector('#save-status').textContent==='Saved'")
            await c.call('Page.navigate',{'url':'http://127.0.0.1:8767/__exports_test/exports?project='+'d'*32+'&job='+'a'*32+'&clip=0'})
            await c.until('!!window.siteReady');await c.js('window.siteReady')
            await c.until("!document.querySelector('#download-active').disabled",90)
            await c.click('#download-active')
            for _ in range(100):
                if download.is_file() and not (ARTIFACTS/'cascade-session-1-wave-1-clip-1.mp4.crdownload').exists():break
                await asyncio.sleep(.1)
            assert download.is_file(),'Actual export download missing'
            output=ARTIFACTS/(mode+'.mp4');download.replace(output)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height:format=duration','-of','json',str(output)]))
            dimensions=next(s for s in probe['streams'] if 'width' in s)
            assert dimensions=={'width':360,'height':640},dimensions
            assert abs(float(probe['format']['duration'])-1)<.1
            frame=subprocess.check_output(['ffmpeg','-v','error','-ss','0.5','-i',str(output),'-frames:v','1','-f','image2pipe','-vcodec','png','-'])
            (ARTIFACTS/(mode+'-actual.png')).write_bytes(frame)
            reference=Image.open(io.BytesIO(base64.b64decode(expected))).convert('RGB');actual=Image.open(io.BytesIO(frame)).convert('RGB')
            error=sum(ImageStat.Stat(ImageChops.difference(reference,actual)).mean)/3
            assert error<10,(mode,error)
            print(mode,'export: 360×640, 1 second; mean preview/composite pixel error',round(error,2),'/255')
            if mode=='fit':
                assert max(abs(a-b) for a,b in zip(actual.getpixel((10,10)),(51,68,85)))<6
            await c.call('Page.navigate',{'url':destination});await c.until('!!window.editorReady');await c.js('window.editorReady');await c.until("document.querySelector('#editor-video').readyState>=2")
        # Per-clip independence and a genuinely new document after reload.
        await c.js("document.querySelectorAll('#editor-sessions button')[1].click()")
        await c.until("document.querySelector('#editor-clip-title').textContent==='Session 2 · Wave 1 · Clip 1'")
        assert await c.js("document.querySelector('[data-ratio=original]').getAttribute('aria-pressed')")=='true'
        await c.js("document.querySelectorAll('#editor-sessions button')[0].click()")
        await c.until("document.querySelector('#editor-clip-title').textContent==='Session 1 · Wave 1 · Clip 1'")
        assert await c.js("document.querySelector('#framing').value")=='fill'
        assert await c.js("!document.querySelector('#crop-x')")
        await c.until("document.querySelector('#save-status').textContent==='Saved'")
        origin=await c.js('performance.timeOrigin');await c.call('Page.reload');await c.until(f'performance.timeOrigin!=={origin} && !!window.editorReady');await c.js('window.editorReady');await c.until("document.querySelector('#editor-video').readyState>=2")
        assert await c.js("document.querySelector('#framing').value")=='fill'
        assert await c.js("!document.querySelector('#crop-x')")
        assert await c.js("document.querySelector('#trim-start').value")=='1'
        assert await c.js("document.querySelector('#cap-color').value")=='#ffff00'
        await c.click('#ratio-tab')
        shot=await c.call('Page.captureScreenshot',{'format':'png'});(ARTIFACTS/'restored-editor.png').write_bytes(base64.b64decode(shot['data']))
        # Real media failure, then recovery, without corrupting saved editing state.
        await c.js("document.querySelector('#editor-video').src='/__missing_aspect_fixture.mp4'")
        await c.until("document.querySelector('#playback-status').textContent.includes('unavailable')")
        await c.js("document.querySelectorAll('#editor-sessions button')[0].click()")
        await c.until("document.querySelector('#editor-video').readyState>=2 && !document.querySelector('#editor-video').error")
        assert await c.js("!document.querySelector('#crop-x')")
        assert not c.errors,c.errors
        print('Chrome passed: six presets, fit/background, automatic fill/centered no-face fallback, output captions, main playback/restart/pause, timeline synchronization, comparison, history, independent clips and reload.')
        print('Artifacts:',ARTIFACTS)

if __name__=='__main__':asyncio.run(main())
