"""Chrome DevTools browser checks against editor_browser_server.py, no paid APIs.
Run isolated Chrome with --headless=new --remote-debugging-port=9333, then this file.
"""
import asyncio
import base64
import io
import json
import time
import subprocess
import urllib.request
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

ARTIFACTS=Path('/tmp/cascade-editor-browser-artifacts')

class Chrome:
    def __init__(self,ws): self.ws=ws; self.seq=0; self.errors=[]
    async def call(self,method,params=None):
        self.seq+=1; seq=self.seq
        await self.ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
        while True:
            message=json.loads(await self.ws.recv())
            if message.get('method')=='Page.javascriptDialogOpening':
                self.seq+=1
                await self.ws.send(json.dumps({'id':self.seq,'method':'Page.handleJavaScriptDialog','params':{'accept':True}}))
            if message.get('method')=='Runtime.exceptionThrown': self.errors.append(message['params'])
            if message.get('id')==seq:
                if 'error' in message: raise RuntimeError(message['error'])
                return message.get('result',{})
    async def js(self,expression):
        result=await self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
        if result.get('exceptionDetails'): raise RuntimeError(result['exceptionDetails'])
        return result.get('result',{}).get('value')
    async def until(self,expression,timeout=15):
        start=time.monotonic()
        while time.monotonic()-start<timeout:
            if await self.js(expression): return
            await asyncio.sleep(.1)
        raise AssertionError('Timed out: '+expression)
    async def box(self,selector):
        return await self.js(f"(()=>{{const e=document.querySelector({json.dumps(selector)});if({json.dumps(selector)}!=='#timeline-content')e.scrollIntoView({{block:'nearest',inline:'nearest'}});const r=e.getBoundingClientRect();return {{x:r.x,y:r.y,width:r.width,height:r.height}};}})()")
    async def click(self,selector):
        box=await self.box(selector); x=box['x']+box['width']/2; y=box['y']+box['height']/2
        await self.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':x,'y':y,'button':'left','clickCount':1})
        await self.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':x,'y':y,'button':'left','clickCount':1})
    async def drag(self,x,y,to_x,to_y=None):
        to_y=y if to_y is None else to_y
        await self.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':x,'y':y,'button':'left','buttons':1,'clickCount':1})
        for step in range(1,9):
            await self.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':x+(to_x-x)*step/8,'y':y+(to_y-y)*step/8,'button':'left','buttons':1})
        await self.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':to_x,'y':to_y,'button':'left','buttons':0,'clickCount':1})
    async def input(self,id,value):
        await self.js(f"(()=>{{const e=document.getElementById({json.dumps(id)}); e.value={json.dumps(value)}; e.dispatchEvent(new Event('input',{{bubbles:true}})); e.dispatchEvent(new Event('change',{{bubbles:true}}));}})()")
    async def shot(self,name,selector='#preview-wrap'):
        await self.until("!document.querySelector('#editor-video').seeking")
        await self.js('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        rect=await self.box(selector)
        scroll=await self.js('({x:scrollX,y:scrollY})')
        result=await self.call('Page.captureScreenshot',{'format':'png','clip':{'x':rect['x']+scroll['x'],'y':rect['y']+scroll['y'],'width':rect['width'],'height':rect['height'],'scale':1},'captureBeyondViewport':True})
        data=base64.b64decode(result['data']); (ARTIFACTS/name).write_bytes(data)
        return Image.open(io.BytesIO(data)).convert('RGB')

async def main():
    import websockets  # Optional browser-test dependency; not needed by unittest discovery.
    ARTIFACTS.mkdir(exist_ok=True)
    targets=json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list'))
    target=next(t for t in targets if t['type']=='page')
    async with websockets.connect(target['webSocketDebuggerUrl'],max_size=None,origin='http://localhost:9333') as ws:
        c=Chrome(ws); await c.call('Runtime.enable'); await c.call('Page.enable')
        await c.call('Emulation.setDeviceMetricsOverride',{'width':1366,'height':1000,'deviceScaleFactor':1,'mobile':False})
        await c.call('Page.navigate',{'url':'about:blank'})
        await c.until("location.href==='about:blank'")
        await asyncio.sleep(.5)  # Let the old page's visibility-save finish before resetting fixture data.
        clear_script=await c.call('Page.addScriptToEvaluateOnNewDocument',{'source':"if(location.origin==='http://127.0.0.1:8767') localStorage.clear();"})
        await c.call('Storage.clearDataForOrigin',{'origin':'http://127.0.0.1:8767','storageTypes':'local_storage'})
        urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8767/__editor_reset',data=b'',method='POST')).close()
        destination='http://127.0.0.1:8767/__editor_test?project='+'d'*32+'&run='+str(time.time_ns())
        await c.call('Page.navigate',{'url':destination})
        await c.until('location.href.startsWith('+json.dumps(destination)+') && !!window.editorReady'); await c.js('window.editorReady');
        await c.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':clear_script['identifier']})
        await c.until("document.querySelector('#editor-video').readyState>=2 && document.querySelector('#thumbnail-strip img') && document.querySelector('#thumbnail-status').textContent==='Frames from selected clip'")
        assert await c.js("document.querySelectorAll('#editor-sessions button').length") ==4
        await c.until("[...document.querySelectorAll('#thumbnail-strip img')].every(img=>img.complete && img.naturalWidth===160)")
        assert await c.js("new Set([...document.querySelectorAll('#thumbnail-strip img')].map(img=>img.src)).size")>1
        await c.click('#captions-tab'); await c.input('caption-cue','0')
        await c.until("Math.abs(document.querySelector('#editor-video').currentTime-.501)<.02")
        await asyncio.sleep(.15)
        before=await c.shot('01-before.png')
        # Real canvas and composited Chrome screenshots must visibly change for each setting.
        old=await c.js("document.querySelector('#caption-overlay').toDataURL()")
        for id,value in [('cap-color','#ffff00'),('cap-font','Georgia'),('cap-size','64'),('cap-background','#6500c9'),('cap-opacity','0.7'),('cap-stroke','#ff0000'),('cap-thickness','4'),('cap-position','top'),('cap-text','Live caption text')]:
            await c.input(id,value)
            now=await c.js("document.querySelector('#caption-overlay').toDataURL()")
            # Background is intentionally invisible until opacity is nonzero.
            if id!='cap-background': assert old!=now, 'No caption pixel change for '+id
            old=now
        text_pixels=await c.js("document.querySelector('#caption-overlay').toDataURL()")
        await c.click('#undo'); assert await c.js("document.querySelector('#cap-text').value")== 'A real caption'
        assert await c.js("document.querySelector('#caption-overlay').toDataURL()")!=text_pixels
        await c.click('#redo'); assert await c.js("document.querySelector('#cap-text').value")== 'Live caption text'
        after=await c.shot('02-live-edited.png'); assert ImageChops.difference(before,after).getbbox()
        state_before=await c.js("JSON.stringify(JSON.parse(localStorage.getItem('cascade-editor:v1:editor-browser-user:'+ 'd'.repeat(32)+':'+ 'a'.repeat(32)+':0')).state)")
        edited_pixels=await c.js("document.querySelector('#caption-overlay').toDataURL()")
        await c.click('#preview-original'); assert await c.js("document.querySelector('#caption-overlay').hidden")
        original=await c.shot('03-original.png'); assert ImageChops.difference(after,original).getbbox()
        await c.click('#preview-edited'); edited=await c.shot('04-edited-again.png');
        assert await c.js("document.querySelector('#caption-overlay').toDataURL()")==edited_pixels
        # Chrome's native buffering spinner can animate in the middle of a paused video.
        region=(0,0,after.width,int(after.height*.3))
        assert not ImageChops.difference(after.crop(region),edited.crop(region)).getbbox()
        assert await c.js("JSON.stringify(JSON.parse(localStorage.getItem('cascade-editor:v1:editor-browser-user:'+ 'd'.repeat(32)+':'+ 'a'.repeat(32)+':0')).state)")==state_before
        # A real pointer drag creates one history transaction.
        handle=await c.box('#handle-start'); content=await c.box('#timeline-content')
        pps=content['width']/8
        await c.drag(handle['x']+handle['width']/2,handle['y']+30,content['x']+pps)
        assert abs(float(await c.js("document.querySelector('#trim-start').value"))-1)<.08
        await c.click('#undo'); assert float(await c.js("document.querySelector('#trim-start').value"))==0
        await c.click('#redo'); assert abs(float(await c.js("document.querySelector('#trim-start').value"))-1)<.08
        await c.input('trim-end','2.0')
        assert '0:01.00' in await c.js("document.querySelector('#trim-summary').textContent")
        await c.click('#play-toggle'); await c.until("document.querySelector('#editor-video').paused && document.querySelector('#editor-video').currentTime>=1.99",5)
        assert abs(await c.js("document.querySelector('#editor-video').currentTime")-2)<.03
        # Original mode can seek outside the trim, edited mode restores its retained range.
        await c.click('#preview-original'); await c.js("document.querySelector('#editor-video').currentTime=6")
        await c.until("document.querySelector('#editor-video').currentTime>5.9")
        await c.click('#preview-edited'); assert 1<=await c.js("document.querySelector('#editor-video').currentTime")<=2.001
        await c.click('#reset-trim'); await c.click('#chat-tab'); await c.input('chat-input','Trim first two seconds and yellow top captions')
        await c.click('#chat-send'); await c.until("!document.querySelector('#chat-send').disabled")
        assert float(await c.js("document.querySelector('#trim-start').value"))==2
        assert await c.js("document.querySelector('#cap-color').value")=='#ffff00'
        assert await c.js("document.querySelector('#cap-position').value")=='top'
        assert await c.js("document.querySelector('#preview-label').textContent")=='Edited preview'
        await c.shot('05-ai-edited.png')
        await c.click('#undo'); assert float(await c.js("document.querySelector('#trim-start').value"))==0
        assert not await c.js("document.querySelector('#cap-bold').checked")
        await c.click('#redo'); assert float(await c.js("document.querySelector('#trim-start').value"))==2
        assert await c.js("document.querySelector('#cap-bold').checked")
        # Zoom, scroll, seek and scrub use media coordinates rather than viewport percentages.
        await c.input('timeline-zoom','4')
        await c.js("document.querySelector('#timeline-scroll').scrollLeft=300")
        content=await c.box('#timeline-content'); view=await c.box('#timeline-scroll'); pps=content['width']/8
        target=4.0; x=content['x']+target*pps
        if not view['x']+20<x<view['x']+view['width']-20:
            await c.js(f"document.querySelector('#timeline-scroll').scrollLeft={target*pps-view['width']/2}")
            content=await c.box('#timeline-content'); x=content['x']+target*pps
        y=content['y']+18
        await c.drag(x,y,x+pps*.5)
        assert abs(await c.js("document.querySelector('#editor-video').currentTime")-4.5)<.08
        segment=await c.js("(()=>{const r=document.querySelectorAll('.caption-segment')[1].getBoundingClientRect();const t=document.querySelector('#timeline-content').getBoundingClientRect();return {left:r.left-t.left,width:r.width,pps:t.width/8};})()")
        assert abs(segment['left']/segment['pps']-3)<.01 and abs(segment['width']/segment['pps']-1.5)<.01
        await c.shot('06-timeline-zoomed.png','#timeline-controls')
        # A trim handle uses the same accurate coordinates while zoomed and scrolled.
        await c.js("const scroller=document.querySelector('#timeline-scroll'); scroller.scrollLeft=scroller.scrollWidth;")
        handle=await c.box('#handle-end'); content=await c.box('#timeline-content'); pps=content['width']/8
        hit=await c.js(f"document.elementFromPoint({handle['x']+handle['width']/2},{handle['y']+30})?.id")
        assert hit=='handle-end', (hit,handle,content)
        await c.drag(handle['x']+handle['width']/2,handle['y']+30,handle['x']+handle['width']/2-pps*.5)
        assert abs(float(await c.js("document.querySelector('#trim-end').value"))-7.5)<.08, await c.js("({end:document.querySelector('#trim-end').value,time:document.querySelector('#editor-video').currentTime})")
        await c.click('#undo'); assert float(await c.js("document.querySelector('#trim-end').value"))==8
        # Returning to Fit and resizing preserves usable geometry.
        await c.click('#zoom-fit')
        await c.call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False})
        await asyncio.sleep(.2)
        assert await c.js('document.documentElement.scrollWidth<=innerWidth')
        await c.shot('07-editor-laptop.png','main')
        # Export using the exact live caption rasters; examine encoded duration/pixels separately.
        export_data=await c.js("""(async()=>{const root='/api/projects/'+ 'd'.repeat(32)+'/editor/'+ 'a'.repeat(32)+'/0'; const info=await apiJSON(root); const state=JSON.parse(localStorage.getItem('cascade-editor:v1:editor-browser-user:'+ 'd'.repeat(32)+':'+ 'a'.repeat(32)+':0')).state; const overlays=CascadeCaptions.exportFrames(info.cues,state,info.width,info.height); window.exportState=state; const r=await apiFetch(root+'/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...state,overlays})}); const bytes=new Uint8Array(await r.arrayBuffer()); let s=''; for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192)); return btoa(s);})()""")
        (ARTIFACTS/'edited.mp4').write_bytes(base64.b64decode(export_data))
        expected=await c.js("""(async()=>{const v=document.querySelector('#editor-video'); await new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=3.5;}); const canvas=document.createElement('canvas');canvas.width=640;canvas.height=360; const ctx=canvas.getContext('2d');ctx.drawImage(v,0,0);ctx.drawImage(document.querySelector('#caption-overlay'),0,0);return canvas.toDataURL('image/png').split(',')[1];})()""")
        (ARTIFACTS/'expected-export-frame.png').write_bytes(base64.b64decode(expected))
        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(ARTIFACTS/'edited.mp4')]))
        assert abs(duration-6)<.1, duration
        frame=subprocess.check_output(['ffmpeg','-v','error','-ss','1.5','-i',str(ARTIFACTS/'edited.mp4'),'-frames:v','1','-f','image2pipe','-vcodec','png','-'])
        (ARTIFACTS/'actual-export-frame.png').write_bytes(frame)
        expected_img=Image.open(io.BytesIO(base64.b64decode(expected))).convert('RGB')
        actual_img=Image.open(io.BytesIO(frame)).convert('RGB')
        mae=sum(ImageStat.Stat(ImageChops.difference(expected_img,actual_img)).mean)/3
        caption_mae=sum(ImageStat.Stat(ImageChops.difference(expected_img.crop((0,20,640,70)),actual_img.crop((0,20,640,70)))).mean)/3
        # yuv420p export subsamples chroma; allow its expected color loss around high-contrast caption edges.
        assert mae<6 and caption_mae<12, (mae,caption_mae)
        print(f'Export comparison: duration {duration:.3f}s, mean pixel error {mae:.2f}/255, caption area {caption_mae:.2f}/255 (lossy H.264).')
        # Independent clips and restored visible state.
        await c.js("document.querySelectorAll('#editor-sessions button')[3].click()")
        await c.until("document.querySelector('#editor-clip-title').textContent==='Session 2 · Clip 3'")
        assert float(await c.js("document.querySelector('#trim-start').value"))==0
        await c.js("document.querySelectorAll('#editor-sessions button')[0].click()")
        await c.until("document.querySelector('#editor-clip-title').textContent==='Session 1 · Clip 1'")
        assert float(await c.js("document.querySelector('#trim-start').value"))==2
        await c.until("document.querySelector('#save-status').textContent==='Saved'")
        origin=await c.js('performance.timeOrigin')
        await c.call('Page.reload'); await c.until(f'performance.timeOrigin!=={origin} && !!window.editorReady'); await c.js('window.editorReady')
        await c.until("document.querySelector('#editor-video').readyState>=2")
        assert float(await c.js("document.querySelector('#trim-start').value"))==2
        assert await c.js("document.querySelector('#cap-text').value")=='Live caption text'
        await c.js("document.querySelector('#editor-video').currentTime=2.1"); await asyncio.sleep(.15)
        assert await c.js("document.querySelector('#caption-overlay').getContext('2d').getImageData(0,0,640,360).data.some((v,i)=>i%4===3 && v>0)")
        await c.shot('08-restored-visible.png','main')
        assert not c.errors, c.errors
        print('Chrome checks passed: visible caption pixels/screenshots, actual playback, comparison, AI synchronization, pointer trim/scrub, zoom/scroll, caption segments, clip independence, reload.')
        print('Artifacts:',ARTIFACTS)

if __name__=='__main__': asyncio.run(main())
