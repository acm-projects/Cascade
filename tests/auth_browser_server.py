"""Isolated authentication fixture: real frontend bootstrap/routes, fake Clerk only.
Never use real job storage or identity tokens. No external identity/AI requests.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi import HTTPException
from fastapi.responses import Response
import app1
from backend import integration

if __name__=='__main__':
 with tempfile.TemporaryDirectory(prefix='cascade-auth-browser-') as directory:
  app1.JOBS_DIR=Path(directory);os.environ['CASCADE_WARM_MODELS']='0'
  app1.uses_local_storage=lambda:True
  app1.authorized_parties=lambda:['http://127.0.0.1:8768']
  app1.clerk_configuration=lambda:('fixture-publishable-key','clerk.fixture.invalid')
  state={'active':True,'revocations':0,'settings_posts':0}
  @app1.app.middleware('http')
  async def audit(request,call_next):
   if request.url.path=='/api/settings' and request.method=='POST':state['settings_posts']+=1
   return await call_next(request)
  def verify(token):
   if token!='fixture-auth-token' or not state['active']:raise HTTPException(401,'Please sign in again.')
   return 'auth-fixture-user'
  app1.verify_clerk_token=verify
  user='auth-fixture-user';pid='d'*32;jid='a'*32
  storage=integration.project_dir(user);storage.mkdir(parents=True)
  app1.save_json(storage/(pid+'.json'),{'id':pid,'name':'Preserve this project','user_id':user,'created_at':1,'saved_clips':[]})
  folder=app1.JOBS_DIR/jid;folder.mkdir()
  app1.save_json(folder/'owner.json',{'user_id':user,'project_id':pid,'kind':'generation','created_at':1})
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=160x120:r=12:d=3','-c:v','libx264',str(folder/'clip_1.mp4')],check=True)
  (folder/'clip_1.vtt').write_text('WEBVTT\n\n00:00.000 --> 00:02.500\nPreserve my draft\n')
  app1.save_json(folder/'results.json',{'clips':[{'start':0,'end':3,'clip_url':f'/clips/{jid}/clip_1.mp4','captions_url':f'/clips/{jid}/clip_1.vtt'}]})
  @app1.app.post('/__auth/reset')
  def reset():state.update(active=True,revocations=0,settings_posts=0);return {'reset':True}
  @app1.app.get('/__auth/state')
  def status():return state
  @app1.app.post('/__auth/revoke')
  def revoke():state['active']=False;state['revocations']+=1;return {'revoked':True}
  @app1.app.get('/__auth/data')
  def data():
   path=storage/'editor'/pid/(jid+'-0.json')
   return {'project_preserved':(storage/(pid+'.json')).is_file(),'draft':json.loads(path.read_text()) if path.is_file() else None}
  original=app1.serve_new_page
  @app1.app.get('/__auth/session')
  def session():return {'active':state['active']}
  def serve(filename):
   if filename=='flow_C.js':
    mock=(Path(__file__).parent/'auth_clerk_fixture.js').read_text()
    script=(app1.FRONTEND_DIR/filename).read_text().replace('  function loadScript(url, publishableKey) {','  function loadScript(url, publishableKey) { return Promise.resolve();',1)
    return Response(mock+'\n'+script,media_type='application/javascript',headers={'Cache-Control':'no-store'})
   return original(filename)
  app1.serve_new_page=serve
  uvicorn.run(app1.app,host='127.0.0.1',port=8768,log_level='warning')
