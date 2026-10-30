"""Offline, isolated Teddy research→chat→save→render demonstration.
Research/search/AI providers are fixtures; all media rendering and edit execution are real.
Never changes existing projects or calls external services.
"""
import json,os,shutil,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['CASCADE_WARM_MODELS']='0'
import app1
from fastapi.testclient import TestClient
from backend.core import jobs,auth
from backend.editor import trends
from backend.editor.storage import stock_store
from backend import broll,cascade_llm
from backend.trends import pipeline,youtube_trends
from tests.test_clip_trends import findings

def main():
 output=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/cascade-trends-demo')
 if output.exists():raise SystemExit('Choose a new output directory; existing files are not overwritten.')
 source=Path('video_jobs/cd732c335cf041cda6e27f5169a1bf32/clip_1.mp4')
 cutaway=source.with_name('clip_3.mp4')
 if not source.is_file() or not cutaway.is_file():raise SystemExit('The local Teddy fixture is unavailable.')
 output.mkdir()
 with tempfile.TemporaryDirectory(prefix='cascade-trends-demo-') as directory,patch.object(jobs,'JOBS_DIR',Path(directory)),patch.object(auth,'verify_clerk_token',return_value='demo-owner'),patch.dict(os.environ,{'CASCADE_METADATA_STORE':'local','CASCADE_STORAGE':'local'}):
  client=TestClient(app1.app);headers={'Authorization':'Bearer demo'}
  pid=client.post('/api/projects',headers=headers,json={'name':'Isolated Trends demonstration'}).json()['id'];jid='a'*32
  folder=Path(directory)/jid;folder.mkdir()
  shutil.copyfile(source,folder/'clip_1.mp4');shutil.copyfile(source.with_suffix('.vtt'),folder/'clip_1.vtt')
  jobs.save_json(folder/'owner.json',{'user_id':'demo-owner','project_id':pid,'kind':'generation'})
  jobs.save_json(folder/'results.json',{'clips':[{'title':'Teddy and John comedy dialogue','start':0,'end':36.83,'clip_url':f'/clips/{jid}/clip_1.mp4','captions_url':f'/clips/{jid}/clip_1.vtt'}]})
  url=f'/api/projects/{pid}/editor/{jid}/0';state=client.get(url,headers=headers).json()['draft']['state']
  shutil.copyfile(source,output/'original.mp4')
  stock=stock_store(pid,jid,0,'demo-owner');stock.folder.mkdir(parents=True,exist_ok=True)
  asset=broll.Asset(id='px-1-1',provider_id=1,creator='Local user-provided Teddy cutaway (fixture)',creator_url='',source_url='',duration=10,width=640,height=344)
  shutil.copyfile(cutaway,stock.folder/(asset.id+'.mp4'))
  broll.write_json(stock.folder/'assets.json',{asset.id:{'asset':asset.model_dump(),'video':'','image':''}})
  video={'video_id':'abcdefghijk','title':'OFFLINE MOCK YouTube example','channel':'Test fixture','url':'https://www.youtube.com/watch?v=abcdefghijk','published_at':'2026-10-29T00:00:00Z','view_count':100}
  data=findings()
  # This demonstration's complete opening starts at 3.18s, not in the unrelated test source.
  data['suggestions'][0]['at']=3.18;data['suggestions'][1]['at']=9.5
  def search(query,limit):return [video] if 'tutorial' not in query else []
  with patch.object(youtube_trends,'get_trending_videos',side_effect=search),patch.object(pipeline,'extract_tags',return_value={'pacing':'medium','tone':'humorous'}),patch.object(pipeline,'analyze_youtube_video',return_value={'tags':{'pacing':'fast','tone':'humorous','visual_style':['short captions','reaction punch-ins']}}),patch.object(cascade_llm,'structured_json',return_value=SimpleNamespace(data=data)),patch.object(broll.Store,'search',return_value={'results':[asset.model_dump()]}):
   # Exercise the real background API, including edited-input rendering and persistence.
   response=client.post(url+'/trends',headers=headers,json={'state':state,'topic':'comedy dialogue teddy bear'})
   assert response.status_code==202,response.text
   rid=response.json()['id']
   for _ in range(240):
    record=client.get(url+'/trends?research_id='+rid,headers=headers).json()
    if record['status']!='running':break
    time.sleep(.25)
   assert record['status']=='done',record.get('message')
   assert client.get(url,headers=headers).json()['draft']['state']==state
   response=client.post(url+'/chat',headers=headers,json={'state':state,'message':'Apply suggested edits from YouTube research.','research_id':rid})
   assert response.status_code==200,response.text
   edited=response.json();state=edited['state']
   assert client.put(url,headers=headers,json={'state':state}).status_code==200
   assert client.get(url,headers=headers).json()['draft']['state']==state
   result=client.post(url+'/export',headers=headers,json=state);assert result.status_code==200,result.text
   (output/'edited.mp4').write_bytes(result.content)
   (output/'report.json').write_text(json.dumps({'mode':'OFFLINE MOCK research/AI/search; REAL selected-media analysis rendering, execution, persistence and MP4 export','research':record,'execution':edited},indent=2))
   print(edited['message']);print('Playable before/after:',output)
 return 0
if __name__=='__main__':raise SystemExit(main())
