"""Opt-in render on a COPY of user-specified media; real projects stay untouched.
Default local mode mocks the planner/search and uses a supplied local cutaway.
--live-ai sends transcript/edit context to configured AI and search terms to Pexels.
No OAuth/publishing calls. Do not use --live-ai without explicit egress approval.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--captions',required=True,type=Path)
    parser.add_argument('--cutaway',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--live-ai',action='store_true')
    parser.add_argument('--reel',action='store_true',help='Apply the coordinated High-Energy Reel style')
    parser.add_argument('--replay-plan',type=Path,help='Replay the validated planner response in an earlier demo report')
    args=parser.parse_args()
    if args.output.exists():parser.error('Choose a new output path; existing exports are never overwritten.')
    if not args.live_ai and not args.cutaway:parser.error('Local mode requires a permitted --cutaway video.')
    os.environ['CASCADE_WARM_MODELS']='0'
    import app1
    from backend.core import auth
    from backend.core import jobs as core_jobs
    from fastapi.testclient import TestClient
    from backend.editor import ai
    from backend.editor.models import Proposal,Action
    from backend.editor.storage import stock_store
    from backend import broll
    with tempfile.TemporaryDirectory(prefix='cascade-teddy-demo-') as directory, ExitStack() as stack:
        stack.enter_context(patch.object(core_jobs,'JOBS_DIR',Path(directory)))
        stack.enter_context(patch.object(auth,'verify_clerk_token',return_value='demo-owner'))
        stack.enter_context(patch.dict(os.environ,{'CASCADE_METADATA_STORE':'local','SOCIAL_DATABASE_PATH':directory+'/social.sqlite3'}))
        client=TestClient(app1.app);headers={'Authorization':'Bearer demo'}
        pid=client.post('/api/projects',headers=headers,json={'name':'Isolated Teddy demonstration'}).json()['id']
        jid='a'*32;folder=Path(directory)/jid;folder.mkdir()
        shutil.copyfile(args.source,folder/'clip_1.mp4');shutil.copyfile(args.captions,folder/'clip_1.vtt')
        core_jobs.save_json(folder/'owner.json',{'user_id':'demo-owner','project_id':pid,'kind':'generation'})
        core_jobs.save_json(folder/'results.json',{'clips':[{'title':'Teddy and John friendship argument','start':0,'end':40,'clip_url':f'/clips/{jid}/clip_1.mp4','captions_url':f'/clips/{jid}/clip_1.vtt'}]})
        base=f'/api/projects/{pid}/editor/{jid}/0'
        info=client.get(base,headers=headers)
        if info.status_code!=200:raise SystemExit('Could not inspect copied clip.')
        details=info.json();state=details['draft']['state'];duration=details['duration'];cues=details['cues']
        anchor=cues[len(cues)//2]['text'] if cues else None
        punch=cues[len(cues)//2]['start'] if cues else duration*.55
        punch=min(punch,duration-3)
        prompt=('Keep the FULL selected clip duration; do not trim. Automatically select and INSERT two relevant short toy-bear B-roll cutaways. '
            'Preserve original dialogue. Add dramatic Tension pulse music throughout, ducked during speech with fades. '
            'Add Impact hit and whoosh SFX at reactions. Add timed punch-ins, short shake, highlighted word captions and a TEDDY! text overlay. Fade in/out for .2s. Use dialogue timestamps.')
        if args.reel:
            prompt='Make this a polished high-energy Reel with a strong opening, beat-synced edits, bold animated captions, selective punch-in zooms, relevant B-roll, and music that stays beneath the dialogue.'
        if not args.live_ai:
            stock=stock_store(pid,jid,0,'demo-owner');stock.folder.mkdir(parents=True,exist_ok=True)
            asset=broll.Asset(id='px-1-1',provider_id=1,creator='Local user-provided cutaway (demo fixture, not Pexels)',creator_url='',source_url='',duration=10,width=640,height=344)
            shutil.copyfile(args.cutaway,stock.folder/(asset.id+'.mp4'))
            broll.write_json(stock.folder/'assets.json',{asset.id:{'asset':asset.model_dump(),'video':'','image':''}})
            actions=[
                Action(type='broll_auto',query='toy bear reaction',start=min(5,duration*.2),duration=1),
                Action(type='broll_auto',query='toy bear fight',start=min(24,duration-4),duration=.8,offset=3),
                Action(type='audio_add',track='music',query='dramatic tension',volume=.24),
                Action(type='audio_add',track='sfx',query='impact hit',start=punch,volume=.65),
                Action(type='audio_add',track='sfx',query='whoosh',start=max(0,punch-1),volume=.45),
                Action(type='motion',motion={'start':max(0,punch-1),'duration':2,'scale_from':1,'scale_to':1.3,'shake':.008}),
                Action(type='motion',motion={'start':min(duration-3,punch+4),'duration':1.5,'scale_from':1.12,'scale_to':1.3,'shake':0}),
                Action(type='caption_animation',animation='karaoke'),
                Action(type='text_overlay',overlay={'start':punch,'duration':1,'text':'TEDDY!'}),
                Action(type='transition',transition={'fade_in':.2,'fade_out':.2}),
            ]
            if args.reel: actions=[Action(type='high_energy_reel',query='toy teddy bear reaction')]
            stack.enter_context(patch.object(ai,'request_edit',return_value=Proposal(message='Local fixture plan',actions=actions)))
            stack.enter_context(patch.object(broll.Store,'search',return_value={'results':[asset.model_dump()],'query':'local supplied cutaway','page':1,'has_more':False}))
        if args.replay_plan:
            prior=json.loads(args.replay_plan.read_text())
            stack.enter_context(patch.object(ai,'request_edit',return_value=Proposal.model_validate(prior['plan'])))
        result=client.post(base+'/chat',headers=headers,json={'state':state,'message':prompt})
        if result.status_code!=200:
            print('Chat failed:',result.status_code,result.json().get('detail'));return 1
        data=result.json()
        args.output.with_suffix('.report.json').write_text(json.dumps({'mode':'live' if args.live_ai else 'local mocked planner/search; real user media/render', 'prompt':prompt,**data},indent=2))
        print(data['message'])
        saved=client.put(base,headers=headers,json={'state':data['state'],'chat':[{'role':'assistant','text':data['message']}]})
        if saved.status_code!=200:raise SystemExit('Demo draft could not be saved.')
        restored=client.get(base,headers=headers).json()['draft']['state']
        if restored!=data['state']:raise SystemExit('Persistence verification failed.')
        response=client.post(base+'/export',headers=headers,json=restored)
        if response.status_code!=200:
            print('Render failed:',response.status_code,response.json().get('detail'));return 1
        args.output.write_bytes(response.content)
        print('Saved isolated demo:',args.output)
        return 0

if __name__=='__main__':raise SystemExit(main())
