"""Opt-in REAL provider demo on an isolated copy. No provider mocks or publishing.
Identity is a local fixture only; all research, stock and AI calls use configured services.
"""
import os,sys,json,shutil,tempfile,logging,argparse,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['CASCADE_WARM_MODELS']='0'
import app1
from fastapi.testclient import TestClient
from backend.core import jobs,auth

def main():
 parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--reuse-research',type=Path,help='Reuse a real report for the identical original media and edit; no new discovery calls')
 args=parser.parse_args();root=args.output;source=Path('video_jobs/cd732c335cf041cda6e27f5169a1bf32/clip_1.mp4')
 if root.exists():raise SystemExit('Choose a new output directory.')
 root.mkdir();logging.basicConfig(level=logging.INFO)
 # HTTP SDK request logs can contain query credentials: only our sanitized stage logger is enabled.
 logging.getLogger('httpx').setLevel(logging.WARNING);logging.getLogger('httpcore').setLevel(logging.WARNING)
 with tempfile.TemporaryDirectory(prefix='cascade-live-trends-') as d,patch.object(jobs,'JOBS_DIR',Path(d)),patch.object(auth,'verify_clerk_token',return_value='live-demo-owner'),patch.dict(os.environ,{'CASCADE_METADATA_STORE':'local','CASCADE_STORAGE':'local'}):
  client=TestClient(app1.app);headers={'Authorization':'Bearer local-demo'}
  pid=client.post('/api/projects',headers=headers,json={'name':'Isolated real research demonstration'}).json()['id'];jid='a'*32
  folder=Path(d)/jid;folder.mkdir();shutil.copyfile(source,folder/'clip_1.mp4');shutil.copyfile(source.with_suffix('.vtt'),folder/'clip_1.vtt')
  jobs.save_json(folder/'owner.json',{'user_id':'live-demo-owner','project_id':pid,'kind':'generation'})
  jobs.save_json(folder/'results.json',{'clips':[{'title':'Teddy and John comedy dialogue','start':0,'end':36.83,'clip_url':f'/clips/{jid}/clip_1.mp4','captions_url':f'/clips/{jid}/clip_1.vtt'}]})
  url=f'/api/projects/{pid}/editor/{jid}/0';state=client.get(url,headers=headers).json()['draft']['state']
  shutil.copyfile(source,root/'original.mp4')
  extra={}
  if args.reuse_research:
   from backend.editor import trends
   from backend.editor.models import Edit
   prior=json.loads(args.reuse_research.read_text())
   assert hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256((args.reuse_research.parent/'original.mp4').read_bytes()).digest(),'Original media differs.'
   assert trends.fresh(prior) and prior['edit_version']==trends.version(Edit(**state)),'Research expired or edit differs.'
   prior.update(project_id=pid,job_id=jid,clip_index=0,reused_from=str(args.reuse_research))
   trends.put(trends.folder(pid,jid,0,'live-demo-owner'),prior);extra={'research_id':prior['id']}
  response=client.post(url+'/chat',headers=headers,json={'state':state,'message':'Make this a crazy, flashy TikTok-style edit with a strong opening, tight pacing, beat-sync, animated captions, punch-ins, relevant B-roll and music beneath clear dialogue.',**extra})
  if response.status_code!=200:
   (root/'error.json').write_text(json.dumps(response.json(),indent=2));raise SystemExit('Chat failed: '+str(response.status_code))
  edited=response.json();record=client.get(url+'/trends',headers=headers).json()
  (root/'research.json').write_text(json.dumps(record,indent=2));(root/'execution.json').write_text(json.dumps(edited,indent=2))
  print('REAL RESEARCH STATUS:',record['status'],record.get('message'))
  for ref in record.get('result',{}).get('references',[]):print('ANALYZED SOURCE:',ref['url'],ref['published_at'],ref['title'])
  print(edited['message'])
  state=edited['state'];assert client.put(url,headers=headers,json={'state':state}).status_code==200
  assert client.get(url,headers=headers).json()['draft']['state']==state
  result=client.post(url+'/export',headers=headers,json=state)
  if result.status_code!=200:raise SystemExit('Export failed: '+str(result.status_code))
  (root/'edited.mp4').write_bytes(result.content);print('Playable MP4:',root/'edited.mp4')
  return 0 if record['status']=='done' and record.get('result',{}).get('references') else 2
if __name__=='__main__':raise SystemExit(main())
