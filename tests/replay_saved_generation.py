"""Replay a saved OpenAI proposal through real upload/render/API/editor routes.
No paid calls, no mutation of original jobs. Identity and storage are isolated.
Run: python3 tests/replay_saved_generation.py video_jobs/<job-id>
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app1
import openai_scene as scene


def main():
    original=Path(sys.argv[1]).resolve()
    saved=json.loads((original/'openai_selection.json').read_text())
    selected=json.loads((original/'selected_clips.json').read_text())
    proposal=scene.Proposal.model_validate(saved['proposal'])
    root=Path(tempfile.mkdtemp(prefix='cascade-four-clips-'))
    def replay_worker(function,jid,path,*args):
        transcript=original/'transcript.json'
        if transcript.is_file(): (path.parent/'transcript.json').write_bytes(transcript.read_bytes())
        function(jid,path,*args)
    with patch.object(app1,'JOBS_DIR',root), patch.object(app1,'verify_clerk_token',return_value='clip-replay-user'), \
         patch.dict(os.environ,{'CASCADE_STORAGE':'local','OPENAI_API_KEY':'replay-no-network'}), \
         patch.object(app1.worker,'submit',side_effect=replay_worker), \
         patch.object(scene,'request_proposal',return_value=(proposal,{'model':saved['metadata'].get('model'),'replayed':True})), \
         patch.object(scene.httpx,'Client',side_effect=AssertionError('Replay must never call OpenAI')):
        client=TestClient(app1.app);headers={'Authorization':'Bearer fixture'}
        pid=client.post('/api/projects',headers=headers,json={'name':'Four-clip replay verification'}).json()['id']
        with (original/'source.video').open('rb') as source:
            response=client.post('/upload',headers=headers,data={'project_id':pid,'engine':'openai','search':selected.get('query') or 'Find supported moments','mode':'both','clip_length':30},files={'video':('source.mp4',source,'video/mp4')})
        assert response.status_code==202,response.text
        jid=response.json()['job_id']; result=client.get('/api/features/'+jid,headers=headers).json()
        assert result['state']=='done' and len(result['clips'])==4,result
        probes=[]
        for index,clip in enumerate(result['clips']):
            assert client.get(clip['clip_url'],headers=headers).status_code==200
            detail=client.get(f'/api/projects/{pid}/editor/{jid}/{index}',headers=headers)
            assert detail.status_code==200,detail.text
            probes.append(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(root/jid/Path(clip['clip_url']).name)]))['format']['duration'])
        listing=client.get(f'/api/projects/{pid}/editor',headers=headers).json()
        assert len(listing['sessions'])==1 and len(listing['sessions'][0]['clips'])==4
        report={'project_id':pid,'job_id':jid,'source_job':original.name,'clips':4,'durations':probes,'diagnostics':result['selection_diagnostics'],
                'verification':'Actual saved source + replayed real provider proposal; real FFmpeg/HTTP/persistence; mocked identity and local storage; no new OpenAI call.'}
        (root/'verification.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({'artifacts':str(root),**report},indent=2))
    return root

if __name__=='__main__': main()
