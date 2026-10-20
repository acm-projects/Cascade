"""Isolated site fixture: real JSON/media, mocked identity and generation selection.
Run locally only. No production authentication or provider code is replaced on disk.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
import app1
import os
os.environ['CASCADE_WARM_MODELS']='0'
os.environ['CASCADE_METADATA_STORE']='local'
from backend import integration
from backend.generation import followup_windows, options

if __name__=='__main__':
 with tempfile.TemporaryDirectory(prefix='cascade-groups-browser-') as directory:
  app1.JOBS_DIR=Path(directory)
  app1.uses_local_storage=lambda:True
  app1.requirements_error=lambda:None
  app1.verify_clerk_token=lambda token:'groups-browser-user' if token=='groups-browser-fixture' else (_ for _ in ()).throw(HTTPException(401,'Fixture token required'))
  app1.authorized_parties=lambda:['http://127.0.0.1:8767']
  user='groups-browser-user';pid='e'*32;jid='c'*32
  storage=integration.project_dir(user);storage.mkdir(parents=True)
  project={'id':pid,'name':'Generation groups fixture','user_id':user,'created_at':1,'saved_clips':[]}
  app1.save_json(storage/(pid+'.json'),project)
  app1.save_json(storage/('f'*32+'.json'),{**project,'id':'f'*32,'name':'Keep this project','created_at':2})
  folder=app1.JOBS_DIR/jid;folder.mkdir()
  source=folder/'source.video'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=12:duration=8','-c:v','libx264','-pix_fmt','yuv420p','-f','mp4',str(source)],check=True)
  app1.save_json(folder/'owner.json',{'user_id':user,'project_id':pid,'source_job':jid,'source_name':'fixture.mp4','prompt':'First saved prompt','created_at':1,'requested_clip_count':1,'engine':'visual'})
  def render(job_id,video_path,prompt,mode,target):
   count,parent=options(video_path.parent)
   owner=json.loads((video_path.parent/'owner.json').read_text())
   if 'Fail fixture' in prompt and ('once' not in prompt or not owner.get('retry_attempts')):

    integration.fail_feature(job_id,'Fixture provider failure. Earlier groups are preserved.');return
   windows=[{'start':float(i),'end':float(i+1),'title':f'Real fixture clip {i+1}','explanation':'Selection mocked; actual media cut from original source.'} for i in range(min(count,8))]
   windows=followup_windows(windows,parent,prompt,8,3,count)
   clips=[]
   for i,w in enumerate(windows,1):
    output=video_path.parent/f'clip_{i}.mp4'
    subprocess.run(['ffmpeg','-v','error','-ss',str(w['start']),'-i',str(video_path),'-t',str(w['end']-w['start']),'-c:v','libx264','-pix_fmt','yuv420p',str(output)],check=True)
    (video_path.parent/f'clip_{i}.vtt').write_text('WEBVTT\n\n00:00.000 --> 00:00.800\nReal fixture caption\n')
    clips.append({**w,'clip_id':f'{job_id}:{i-1}','clip_url':f'/clips/{job_id}/clip_{i}.mp4','captions_url':f'/clips/{job_id}/clip_{i}.vtt'})
   result={'clips':clips,'requested_clip_count':count,'selection_note':f'Found {len(clips)} of {count} requested clips.'}
   app1.save_json(video_path.parent/'results.json',result)
   app1.jobs[job_id]={'state':'done',**result}
  render(jid,source,'First saved prompt','visual',30)
  keep_id='9'*32
  keep=app1.JOBS_DIR/keep_id;keep.mkdir()
  import shutil
  shutil.copyfile(source,keep/'source.video')
  app1.save_json(keep/'owner.json',{'user_id':user,'project_id':'f'*32,'source_job':keep_id,'source_name':'other.mp4','prompt':'Other project history','created_at':2,'requested_clip_count':1,'engine':'visual'})
  render(keep_id,keep/'source.video','Other project history','visual',30)
  pool=ThreadPoolExecutor(max_workers=2)
  def queued(function,*args):
   def work():
    time.sleep(.65)
    app1.update_job(args[0],state='processing',message='Fixture selection; real media cutting...')
    render(*args)
   return pool.submit(work)
  app1.worker.submit=queued
  @app1.app.post('/__remove_fixture_clip/{job_id}/{index}')
  def remove_fixture_clip(job_id:str,index:int):
   app1.require_job_owner(job_id,user)
   path=app1.JOBS_DIR/job_id/'results.json'
   result=json.loads(path.read_text())
   if index != len(result['clips'])-1:raise HTTPException(400,'Only the final fixture clip can be removed.')
   result['clips'].pop();app1.save_json(path,result);app1.jobs.pop(job_id,None)
   return {'removed':True}
  @app1.app.get('/__flow_test.js')
  def flow():
   script=(app1.FRONTEND_DIR/'flow_C.js').read_text()
   bootstrap="""window.Clerk={session:{getToken:async()=>'groups-browser-fixture'},user:{id:'groups-browser-user',fullName:'Fixture User'},openUserProfile:()=>{},signOut:async()=>{}};
     userId='groups-browser-user';if($('protected-page'))$('protected-page').hidden=false;
     if(page!=='login')showAccount();
     window.siteReady=(async()=>{if(page==='login'){$('sign-in').textContent='Clerk sign-in widget fixture';setStatus('');}else if(page==='projects')await initializeProjects();else if(page==='settings')await initializeSettings();else {await loadProject();if(page==='canvas')await initializeCanvas();else if(page==='editor')await initializeEditor();else if(page==='exports')await initializeExports();}})().catch(error=>{setStatus(error.message);throw error;});"""
   return Response(script.replace('  start();',bootstrap),media_type='application/javascript')
  original_serve=app1.serve_new_page
  def serve_fixture(filename):
   return flow() if filename=='flow_C.js' else original_serve(filename)
  app1.serve_new_page=serve_fixture
  @app1.app.get('/__site/{page}',response_class=HTMLResponse)
  def page(page:str,request:Request,baseline:bool=False):
   if page not in ('home','login','canvas','projects','editor','exports','settings'):raise HTTPException(404)
   filename='index_C.html' if page=='home' else page+'_C.html'
   if baseline:
    snapshot=Path('/tmp/cascade-consolidation-snapshot-path').read_text().strip()
    html=(Path(snapshot)/filename).read_text()
   else:
    html=app1.frontend.render_page(filename,app1.FRONTEND_DIR)
   return '<base href="/">'+html.replace('<script src="flow_C.js"></script>','<script src="/__flow_test.js"></script>')
  uvicorn.run(app1.app,host='127.0.0.1',port=8767,log_level='warning')
