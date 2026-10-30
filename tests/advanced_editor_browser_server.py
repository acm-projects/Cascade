"""Official React UI + isolated real backend. Providers and identity are fixtures."""
import os,sys,tempfile,subprocess,shutil,json,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app1
from backend.core import jobs as core_jobs
from backend.core import auth
from backend.editor import ai
from backend.editor.models import Proposal,Action
from backend.editor.storage import stock_store
from backend import broll
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
import uvicorn
from backend.editor import trends
from tests.test_clip_trends import fixture_result
if __name__=='__main__':
 port=int(os.getenv('CASCADE_FIXTURE_PORT','8771'))
 real_path=os.getenv('CASCADE_REAL_RESEARCH_FILE')
 real=json.loads(Path(real_path).read_text()) if real_path else None
 with tempfile.TemporaryDirectory(prefix='cascade-advanced-browser-') as directory,patch.object(core_jobs,'JOBS_DIR',Path(directory)),patch.object(auth,'DEV_AUTH',True),patch.dict(os.environ,{'CASCADE_METADATA_STORE':'local','SOCIAL_DATABASE_PATH':directory+'/social.sqlite3','CASCADE_WARM_MODELS':'0'}),patch.object(auth,'authorized_parties',return_value={f'http://127.0.0.1:{port}'}):
  client=TestClient(app1.app)
  pid='d'*32;jid='a'*32;user='dev-user'
  from backend.services.projects_store import project_dir
  folder=Path(directory)/jid;folder.mkdir()
  source=folder/'clip_1.mp4'
  subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=480x270:r=24:d=6','-f','lavfi','-i','sine=frequency=440:duration=6','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True)
  (folder/'clip_1.vtt').write_text('WEBVTT\n\n00:00.500 --> 00:01.500\nTeddy appears\n\n00:02.000 --> 00:04.500\nYou are my best friend\n')
  core_jobs.save_json(folder/'owner.json',{'user_id':user,'project_id':pid,'kind':'generation'})
  core_jobs.save_json(folder/'results.json',{'clips':[{'title':'Teddy fixture','start':0,'end':6,'clip_url':f'/clips/{jid}/clip_1.mp4','captions_url':f'/clips/{jid}/clip_1.vtt'}]})
  core_jobs.save_json(project_dir(user)/(pid+'.json'),{'id':pid,'name':'Teddy edit fixture','user_id':user,'created_at':1,'saved_clips':[],'studio':{'editor_clips':[{'job_id':jid,'clip_index':0}]}})
  if real:
   # Display the unchanged, previously verified real findings on a copy of the
   # identical source clip. Only ownership/IDs are isolated for UI regression.
   original=Path('video_jobs')/real['job_id']/f"clip_{real['clip_index']+1}.mp4"
   shutil.copyfile(original,source)
   if original.with_suffix('.vtt').exists():shutil.copyfile(original.with_suffix('.vtt'),source.with_suffix('.vtt'))
   else:source.with_suffix('.vtt').write_text('WEBVTT\n\n')
   title=json.loads((original.parent/'results.json').read_text())['clips'][real['clip_index']].get('title','Selected clip')
   original_owner=json.loads((original.parent/'owner.json').read_text())
   original_editor=Path('video_jobs/projects')/hashlib.sha256(original_owner['user_id'].encode()).hexdigest()/'editor'/real['project_id']
   for kind in ['audio','stock']:
    assets=original_editor/kind/(real['job_id']+'-'+str(real['clip_index']))
    if assets.exists():shutil.copytree(assets,trends.draft_path(pid,jid,0,user).parent/kind/(jid+'-0'),dirs_exist_ok=True)
   core_jobs.save_json(folder/'results.json',{'clips':[{'title':title,'start':0,'end':real['edit_state']['end'],'clip_url':f'/clips/{jid}/clip_1.mp4','captions_url':f'/clips/{jid}/clip_1.vtt'}]})
   real.update(project_id=pid,job_id=jid,clip_index=0)
   real.pop('applications',None)
   core_jobs.save_json(trends.draft_path(pid,jid,0,user),{'state':real['edit_state'],'chat':[],'updated_at':0})
   trends.put(trends.folder(pid,jid,0,user),real)
   Path('/tmp/cascade-guided-display-baseline.json').write_text(json.dumps(real['edit_state']))
   print('Display harness: saved REAL research and identical media copy; no fresh provider analysis is simulated.',flush=True)
  stock=stock_store(pid,jid,0,user);stock.folder.mkdir(parents=True,exist_ok=True)
  asset=broll.Asset(id='px-12-25',provider_id=12,creator='Fixture cutaway',creator_url='',source_url='',duration=6,width=480,height=270)
  subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:s=480x270:d=6','-c:v','libx264',str(stock.folder/(asset.id+'.mp4'))],check=True)
  broll.write_json(stock.folder/'assets.json',{asset.id:{'asset':asset.model_dump(),'video':'','image':''}})
  def planner(payload):
   if payload.get('style_request')=='high-energy-v1':return Proposal(message='Reel fixture plan',actions=[Action(type='high_energy_reel',query='toy bear')])
   return Proposal(message='Fixture plan',actions=[Action(type='broll_auto',query='toy bear',start=1,duration=.8),Action(type='audio_add',track='music',query='dramatic tension'),Action(type='audio_add',track='sfx',query='bell',start=2),Action(type='motion',motion={'start':3,'duration':1,'scale_to':1.3,'shake':.01}),Action(type='caption_animation',animation='karaoke')])
  app1.app.mount('/assets',StaticFiles(directory='frontend/dist/assets'))
  @app1.app.get('/projects/{project}/editor')
  def react_editor(project:str):return FileResponse('frontend/dist/index.html')
  @app1.app.get('/projects/{project}/export')
  def react_export(project:str):return FileResponse('frontend/dist/index.html')
  def collected(*args):
   if real:raise RuntimeError('Saved-report display harness: new research is disabled; this is a display test of real findings.')
   return fixture_result()
  with patch.object(ai,'request_edit',side_effect=planner),patch.object(trends,'collect',side_effect=collected),patch.object(broll.Store,'search',return_value={'query':'toy bear','page':1,'has_more':False,'results':[asset.model_dump()]}):
   uvicorn.run(app1.app,host='127.0.0.1',port=port,access_log=False)
