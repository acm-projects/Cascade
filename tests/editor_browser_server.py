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
from fastapi.responses import HTMLResponse, Response
import app1
import os
os.environ['CASCADE_WARM_MODELS']='0'
from backend import integration
from backend import editor_backend as editor
from backend import broll

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='cascade-browser-') as directory:
        app1.JOBS_DIR=Path(directory)
        os.environ['SOCIAL_DATABASE_PATH']=str(Path(directory)/'social.sqlite3')
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
            import shutil
            shutil.copyfile(source,folder/'source.video')
            app1.save_json(folder/'owner.json',{'user_id':user,'project_id':pid,'kind':'generation'})
            clips=[]
            for i in range(count):
                import shutil
                shutil.copyfile(source,folder/f'clip_{i+1}.mp4')
                (folder/f'clip_{i+1}.vtt').write_text('WEBVTT\n\n00:00.500 --> 00:02.400\nLet&#x27;s say that one more time.\n\n00:03.000 --> 00:04.500\nAnother spoken moment\n\n00:06.000 --> 00:07.500\nFinal caption\n')
                clips.append({'start':100,'end':108,'clip_url':f'/clips/{j}/clip_{i+1}.mp4','captions_url':f'/clips/{j}/clip_{i+1}.vtt'})
            app1.save_json(folder/'results.json',{'clips':clips})
        tracking_fixtures=os.getenv('CASCADE_REFRAME_FIXTURES')
        if tracking_fixtures:
            tracking_pid='9'*32;tracking_job='c'*32
            app1.save_json(storage/(tracking_pid+'.json'),{**project,'id':tracking_pid,'name':'Real reframe fixture'})
            folder=app1.JOBS_DIR/tracking_job;folder.mkdir()
            app1.save_json(folder/'owner.json',{'user_id':user,'project_id':tracking_pid,'kind':'generation','source_job':tracking_job,'prompt':'Conversation and movement test','creation_order':1})
            clips=[]
            for i,name in enumerate(['conversation','moving','conversation','moving'],1):
                import shutil
                shutil.copyfile(Path(tracking_fixtures)/(name+'.mp4'),folder/f'clip_{i}.mp4')
                (folder/f'clip_{i}.vtt').write_text('WEBVTT\n\n00:00.500 --> 00:03.000\nTracking fixture caption\n')
                clips.append({'start':0,'end':12 if name=='conversation'else 6,'title':name.title(),'clip_url':f'/clips/{tracking_job}/clip_{i}.mp4','captions_url':f'/clips/{tracking_job}/clip_{i}.vtt'})
            app1.save_json(folder/'results.json',{'clips':clips})
        if tracking_fixtures and (Path(tracking_fixtures)/'dog.mp4').is_file():
            subject_pid='8'*32;subject_job='e'*32
            app1.save_json(storage/(subject_pid+'.json'),{**project,'id':subject_pid,'name':'Subjects fixture'})
            folder=app1.JOBS_DIR/subject_job;folder.mkdir()
            app1.save_json(folder/'owner.json',{'user_id':user,'project_id':subject_pid,'kind':'generation','prompt':'Follow the dog, walking person or selected bag','creation_order':1})
            clips=[]
            for i,name in enumerate(['dog','pedestrian','bag'],1):
                import shutil
                shutil.copyfile(Path(tracking_fixtures)/(name+'.mp4'),folder/f'clip_{i}.mp4')
                (folder/f'clip_{i}.vtt').write_text('WEBVTT\n')
                clips.append({'start':0,'end':1.2 if name=='bag' else 5,'title':name,'clip_url':f'/clips/{subject_job}/clip_{i}.mp4','captions_url':f'/clips/{subject_job}/clip_{i}.vtt'})
            app1.save_json(folder/'results.json',{'clips':clips})
        stock_source=Path(directory)/'stock.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=green:size=320x180:rate=24:duration=8','-c:v','libx264','-pix_fmt','yuv420p',str(stock_source)],check=True)
        def stock_search(store,query,page=1):
            import shutil
            asset=broll.Asset(id='px-12-25',provider_id=12,creator='Browser stock fixture',creator_url='https://www.pexels.com/@fixture/',source_url='https://www.pexels.com/video/12/',duration=8,width=320,height=180)
            broll.write_json(store.folder/'assets.json',{asset.id:{'asset':asset.model_dump(),'video':'https://videos.pexels.com/fixture.mp4','image':'https://images.pexels.com/fixture.jpg'}})
            shutil.copyfile(stock_source,store.folder/(asset.id+'.mp4'))
            from PIL import Image
            Image.new('RGB',(160,90),'green').save(store.folder/(asset.id+'.jpg'))
            return {'results':[asset.model_dump()],'page':page,'query':query,'has_more':page<2}
        broll.Store.search=stock_search
        # Keep the Research Agent UI/persistence real without paid provider calls.
        def research_fixture(job_id,source,topic):
            integration.finish_feature(job_id,{'clips':[],'research':{'comparison':{'narrative':'Fixture research for '+topic,'matching_traits':['Clear topic'],'missing_traits':[]},'trending_summary':[]}})
        integration.research=research_fixture
        def ai(payload):
            text=payload['request'].lower()
            if any(phrase in text for phrase in ['follow the speaker','keep both','person on the left']):
                focus='both' if 'keep both' in text else 'left' if 'person on the left' in text else 'speaker'
                return editor.Proposal(message='Tracking requested',actions=[editor.Action(type='reframe_focus',focus=focus)])
            if 'find stock' in text:
                return editor.Proposal(message='Search',actions=[editor.Action(type='broll_search',query='mountains')])
            if 'add stock' in text:
                return editor.Proposal(message='Insert',actions=[editor.Action(type='broll_insert',asset_id=payload['broll_results'][0]['id'],start=4,duration=2)])
            if 'remove stock' in text:
                return editor.Proposal(message='Remove',actions=[editor.Action(type='broll_remove',segment_id=payload['selected_broll_segment'])])
            if 'failure' in payload['request']:

                raise HTTPException(502,'Fixture provider unavailable. No edits applied.')
            return editor.Proposal(message='Edited',actions=[editor.Action(type='trim_first',seconds=2),editor.Action(type='caption_color',color='#ffff00'),editor.Action(type='caption_position',position='top'),editor.Action(type='caption_bold',enabled=True)])
        editor.request_edit=ai
        @app1.app.post('/__editor_reset')
        def reset_fixture():
            import shutil
            shutil.rmtree(storage/'editor',ignore_errors=True)
            app1.save_json(storage/(pid+'.json'),project)
            if tracking_fixtures:
                app1.save_json(storage/(tracking_pid+'.json'),{**project,'id':tracking_pid,'name':'Real reframe fixture'})
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
        @app1.app.get('/__exports_flow.js')
        def export_flow_fixture():
            script=(app1.FRONTEND_DIR/'flow_C.js').read_text()
            bootstrap="""window.Clerk={session:{getToken:async()=>'editor-browser-fixture'},user:{id:'editor-browser-user',fullName:'Fixture User'},signOut:async()=>{}};
              userId='editor-browser-user';$('protected-page').hidden=false;showAccount();
              window.siteReady=(async()=>{await loadProject();if(page==='canvas')await initializeCanvas();else if(page==='exports')await initializeExports();else if(page==='editor')await initializeEditor();else if(page==='settings')await initializeSettings();})().catch(error=>{setStatus(error.message);throw error;});"""
            return Response(script.replace('  start();',bootstrap),media_type='application/javascript')
        original_serve=app1.serve_new_page
        def serve_fixture(filename):
            return export_flow_fixture() if filename=='flow_C.js' else original_serve(filename)
        app1.serve_new_page=serve_fixture
        @app1.app.get('/__exports_test/{view}',response_class=HTMLResponse)
        def exports_fixture(view:str):
            if view not in ('canvas','exports','editor','settings'):raise HTTPException(404)
            return '<base href="/">'+app1.frontend.render_page(view+'_C.html',app1.FRONTEND_DIR)
        uvicorn.run(app1.app,host='127.0.0.1',port=8767,log_level='warning')
