"""Isolated real-browser fixture server. Never run against real job storage.
Only this process replaces identity/provider calls; production auth is unchanged.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
import app1
import os
os.environ['CASCADE_WARM_MODELS']='0'
from backend import integration
from backend import editor_backend as editor

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='cascade-browser-') as directory:
        app1.JOBS_DIR=Path(directory)
        def verify(token):
            if token!='editor-browser-fixture':
                raise HTTPException(401,'Fixture token required')
            return 'editor-browser-user'
        app1.verify_clerk_token=verify
        app1.authorized_parties=lambda:['http://127.0.0.1:8767']
        user='editor-browser-user'; pid='d'*32
        project={'id':pid,'name':'Browser preview fixture','user_id':user,'created_at':1,'saved_clips':[]}
        storage=integration.project_dir(user); storage.mkdir(parents=True)
        app1.save_json(storage/(pid+'.json'),project)
        source=Path(directory)/'fixture.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=8', '-f','lavfi','-i','sine=frequency=440:duration=8','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
        for j,count in [('a'*32,1),('b'*32,3)]:
            folder=app1.JOBS_DIR/j; folder.mkdir()
            app1.save_json(folder/'owner.json',{'user_id':user,'project_id':pid,'kind':'generation'})
            clips=[]
            for i in range(count):
                import shutil
                shutil.copyfile(source,folder/f'clip_{i+1}.mp4')
                (folder/f'clip_{i+1}.vtt').write_text('WEBVTT\n\n00:00.500 --> 00:02.400\nLet&#x27;s say that one more time.\n\n00:03.000 --> 00:04.500\nAnother spoken moment\n\n00:06.000 --> 00:07.500\nFinal caption\n')
                clips.append({'start':100,'end':108,'clip_url':f'/clips/{j}/clip_{i+1}.mp4','captions_url':f'/clips/{j}/clip_{i+1}.vtt'})
            app1.save_json(folder/'results.json',{'clips':clips})
        def ai(payload):
            if 'failure' in payload['request']:
                raise HTTPException(502,'Fixture provider unavailable. No edits applied.')
            return editor.Proposal(message='Edited',actions=[editor.Action(type='trim_first',seconds=2),editor.Action(type='caption_color',color='#ffff00'),editor.Action(type='caption_position',position='top'),editor.Action(type='caption_bold',enabled=True)])
        editor.request_edit=ai
        @app1.app.post('/__editor_reset')
        def reset_fixture():
            import shutil
            shutil.rmtree(storage/'editor',ignore_errors=True)
            app1.save_json(storage/(pid+'.json'),project)
            return {'reset':True}
        @app1.app.get('/__editor_test',response_class=HTMLResponse)
        def fixture_page():
            html=app1.frontend.render_page('editor_C.html',app1.FRONTEND_DIR)
            bootstrap='''<script>
              document.getElementById('protected-page').hidden=false;
              const apiFetch=async(url,options={})=>{
                const r=await fetch(url,{...options,headers:{...options.headers,Authorization:'Bearer editor-browser-fixture'}});
                if(!r.ok) { let msg='HTTP '+r.status; try {msg=(await r.json()).detail||msg;} catch{} throw Error(msg); } return r;
              };
              const apiJSON=async(url,opts)=>(await apiFetch(url,opts)).json();
              window.editorReady=apiJSON('/api/projects/PROJECT').then(project=>window.CascadeEditor.initialize({project,userId:'editor-browser-user',apiJSON,apiFetch,setStatus:msg=>document.getElementById('status').textContent=msg,initializeResearch:async()=>{}}));
            </script>'''.replace('PROJECT',pid)
            return html.replace('<script src="flow_C.js"></script>',bootstrap)
        uvicorn.run(app1.app,host='127.0.0.1',port=8767,log_level='warning')
