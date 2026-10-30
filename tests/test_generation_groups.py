"""Project history/branching regressions; workers/providers are mocked."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import app1
from backend.core import jobs as core_jobs
from backend.core import auth
from backend.services import projects_store
from backend.generation import followup_windows
from backend.openai_scene import Proposal, choose_clips
from backend.video_search.selection import select_matches


class GenerationGroupsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for context in [patch.object(core_jobs, 'JOBS_DIR', self.root),
                        patch.object(auth, 'verify_clerk_token', side_effect=lambda t:t),
                        patch.dict(os.environ, {'CASCADE_STORAGE':'local','OPENAI_API_KEY':'fixture','DEEPGRAM_API_KEY':'fixture','ANTHROPIC_API_KEY':'fixture','LLM_PROVIDER':'anthropic'}),
                        patch.object(core_jobs.worker, 'submit')]:
            value=context.start();self.addCleanup(context.stop)
            if hasattr(value,'call_args_list'): self.worker=value
        self.client=TestClient(app1.app)
        self.headers={'Authorization':'Bearer groups-user'}
        self.project=self.client.post('/api/projects',headers=self.headers,json={'name':'First project'}).json()['id']
        self.other=self.client.post('/api/projects',headers=self.headers,json={'name':'Keep project'}).json()['id']
        self.addCleanup(core_jobs.jobs.clear)

    def upload(self,count=4, project=None):
        return self.client.post('/upload',headers=self.headers,data={'project_id':project or self.project,'search':'Interesting moments','engine':'openai','clip_count':count},files={'video':('original.mp4',b'original complete source','video/mp4')})

    def done(self, jid, count=5):
        clips=[{'start':10+i*20,'end':18+i*20,'title':f'Moment {i}','clip_url':f'/clips/{jid}/clip_{i+1}.mp4','captions_url':f'/clips/{jid}/clip_{i+1}.vtt'} for i in range(count)]
        for i in range(count):
            (self.root/jid/f'clip_{i+1}.mp4').write_bytes(b'generated')
            (self.root/jid/f'clip_{i+1}.vtt').write_text('WEBVTT\n\n00:00.000 --> 00:02.000\nParent transcript\n')
        core_jobs.save_json(self.root/jid/'results.json',{'clips':clips})
        core_jobs.jobs.pop(jid,None)
        return clips

    def generate(self,source,count=5,parent=None,index=0,request_id='request-1'):
        body={'source_job':source,'prompt':'Expand this moment with more explanation','clip_count':count,'request_id':request_id}
        if parent:body.update(parent_job=parent,parent_clip_index=index)
        return self.client.post(f'/api/projects/{self.project}/generations',headers=self.headers,json=body)

    def groups(self):return self.client.get(f'/api/projects/{self.project}/generations',headers=self.headers).json()['groups']

    def test_counts_bounds_old_defaults_and_fifth_clip_routes(self):
        for count in [0,-1,13,'5.5','invalid']:
            self.assertEqual(self.upload(count).status_code,422,count)
        for count in [1,5,12]:
            response=self.upload(count);self.assertEqual(response.status_code,202,response.text)
            jid=response.json()['job_id'];self.done(jid,count)
            owner=json.loads((self.root/jid/'owner.json').read_text())
            self.assertEqual(owner['requested_clip_count'],count)
            self.assertEqual(len(next(g for g in self.groups() if g['job_id']==jid)['clips']),count)
        self.assertEqual(self.client.get(f'/clips/{jid}/clip_5.mp4',headers=self.headers).status_code,200)
        self.assertEqual(self.client.post(f'/api/projects/{self.project}/saved-clips',headers=self.headers,json={'job_id':jid,'clip_index':4}).status_code,200)
        self.assertEqual(self.client.get(f'/clips/{jid}/clip_99.mp4',headers=self.headers).status_code,404)
        for invalid in [0,13,5.5,True,'5']:
            self.assertEqual(self.generate(jid,invalid).status_code,422)

    def test_ordinary_prompts_nested_followups_idempotency_and_reload(self):
        original=self.upload(5).json()['job_id'];self.done(original)
        ordinary=self.generate(original,2,request_id='ordinary').json()['job_id'];self.done(ordinary,2)
        child=self.generate(original,4,parent=original,index=4).json()['job_id'];self.done(child,2)
        owner=json.loads((self.root/child/'owner.json').read_text())
        self.assertEqual(owner['parent_clip']['clip_id'],original+':4')
        self.assertIn('Parent transcript',owner['parent_clip']['captions'])
        self.assertEqual(owner['parent_clip']['start'],90)
        self.assertEqual((self.root/child/'source.video').read_bytes(),b'original complete source')
        grand=self.generate(original,3,parent=child,index=1,request_id='child-request').json()['job_id']
        self.assertEqual(json.loads((self.root/grand/'owner.json').read_text())['parent_clip']['clip_id'],child+':1')
        self.done(grand,1)
        before=len(self.worker.call_args_list)
        self.assertEqual(self.generate(original,3,parent=child,index=1,request_id='child-request').json()['job_id'],grand)
        self.assertEqual(len(self.worker.call_args_list),before)
        core_jobs.jobs.clear()
        groups=self.groups()
        self.assertEqual([len(g['clips']) for g in groups],[5,2,2,1])
        self.assertEqual(groups[-1]['parent_clip']['job_id'],child)
        self.assertEqual(groups[1]['parent_clip'],None)
        self.assertEqual([g['order'] for g in groups],[1,2,3,4])
        # Existing editor metadata/persistence accepts clips across every group.
        from types import SimpleNamespace
        with patch('backend.editor.validation.subprocess.run',return_value=SimpleNamespace(stdout=json.dumps({'format':{'duration':8},'streams':[{'width':640,'height':360}]}))):
            for jid,index in [(original,4),(ordinary,1),(child,0),(grand,0)]:
                url=f'/api/projects/{self.project}/editor/{jid}/{index}'
                response=self.client.get(url,headers=self.headers)
                self.assertEqual(response.status_code,200,response.text)
                draft=response.json()['draft'];draft['state']['start']=1
                self.assertEqual(self.client.put(url,headers=self.headers,json=draft).status_code,200)
                self.assertEqual(self.client.get(url,headers=self.headers).json()['draft']['state']['start'],1)

    def test_delete_is_owner_scoped_persistent_and_preserves_other_source(self):
        jid=self.upload().json()['job_id'];self.done(jid)
        keep=self.upload(project=self.other).json()['job_id'];self.done(keep)
        foreign={'Authorization':'Bearer another-user'}
        url=f'/api/projects/{self.project}'
        self.assertEqual(self.client.delete(url,headers=foreign).status_code,404)
        self.assertEqual(self.client.get(url,headers=self.headers).status_code,200)
        # Shared source reference must prevent physical source removal.
        owner_path=self.root/keep/'owner.json';owner=json.loads(owner_path.read_text());owner['source_job']=jid;core_jobs.save_json(owner_path,owner)
        response=self.client.delete(url,headers=self.headers);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get(url,headers=self.headers).status_code,404)
        self.assertEqual(self.client.get(f'/api/projects/{self.other}',headers=self.headers).status_code,200)
        self.assertTrue((self.root/jid/'source.video').is_file())
        self.assertTrue((self.root/keep/'source.video').is_file())
        self.assertEqual(self.client.get('/api/projects',headers=self.headers).json()['projects'][0]['id'],self.other)
        self.assertEqual(self.client.get(f'/clips/{jid}/clip_1.mp4',headers=self.headers).status_code,404)
        self.assertFalse(any('/'+jid+'/' in c['clip_url'] for c in self.client.get('/api/my-clips',headers=self.headers).json()['clips']))

    def test_active_delete_failure_and_foreign_parent_preserve_project(self):
        jid=self.upload().json()['job_id']
        self.assertEqual(self.client.delete(f'/api/projects/{self.project}',headers=self.headers).status_code,409)
        self.done(jid)
        keep=self.upload(project=self.other).json()['job_id'];self.done(keep)
        self.assertEqual(self.generate(keep,parent=keep).status_code,404)
        original_rename=Path.rename
        calls=[]
        def fail_second(path,target):
            calls.append(path)
            if len(calls)==2:raise OSError('fixture failure after staging one job')
            return original_rename(path,target)
        with patch.object(Path,'rename',fail_second):
            self.assertEqual(self.client.delete(f'/api/projects/{self.project}',headers=self.headers).status_code,500)
        self.assertEqual(self.client.get(f'/api/projects/{self.project}',headers=self.headers).status_code,200)
        self.assertTrue((self.root/jid/'results.json').is_file())

    def test_expansion_uses_original_surroundings_without_overlapping_duplicates(self):
        parent={'start':20,'end':28,'title':'Parent'}
        selected=[{'start':21,'end':29},{'start':70,'end':80}]
        result=followup_windows(selected,parent,'Expand this clip',100,30,5)
        self.assertLess(result[0]['start'],20);self.assertGreater(result[0]['end'],28)
        self.assertEqual(len(result),2)
        self.assertEqual(followup_windows(selected,{'start':0,'end':100},'Expand this clip',100,30,5),[])
        self.assertEqual(followup_windows(selected,parent,'Find related moments',100,30,5),selected)

    def test_selection_supports_five_and_returns_only_qualifying_matches(self):
        proposal=Proposal(candidates=[{'start':i*20,'end':i*20+10,'score':8,'title':'Match','explanation':'Supported'} for i in range(7)],insufficient_material_reason='')
        self.assertEqual(len(choose_clips(proposal,150,30,5)),5)
        self.assertEqual(len(choose_clips(proposal,150,30,12)),7)

    def test_history_is_saved_before_queue_and_missing_configuration_fails_early(self):
        seen=[]
        def queued(function,jid,source,*args):
            owner=json.loads((self.root/jid/'owner.json').read_text())
            seen.append(owner)
            self.assertEqual(owner['history_id'],jid)
            self.assertEqual(owner['requested_clip_count'],5)
            self.assertEqual(json.loads((self.root/jid/'progress.json').read_text())['state'],'queued')
        self.worker.side_effect=queued
        first=self.upload(5).json()['job_id']
        self.assertEqual(len(seen),1)
        with patch.dict(os.environ,{'DEEPGRAM_API_KEY':''}):
            response=self.upload(2)
        self.assertEqual(response.status_code,503)
        self.assertIn('DEEPGRAM_API_KEY',response.json()['detail'])
        groups=self.groups()
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['state'],'queued')
        self.assertEqual(groups[0]['history_id'],first)

    def test_retry_reuses_failed_group_and_context_without_duplicate_history(self):
        original=self.upload(5).json()['job_id'];self.done(original)
        child=self.generate(original,2,parent=original,index=1).json()['job_id']
        projects_store.fail_feature(child,'Fixture provider failure')
        before=json.loads((self.root/child/'owner.json').read_text())
        url=f'/api/projects/{self.project}/generations/{child}/retry'
        self.assertEqual(self.client.post(url,headers={'Authorization':'Bearer stranger'},json={'request_id':'retry-1'}).status_code,404)
        calls=len(self.worker.call_args_list)
        result=self.client.post(url,headers=self.headers,json={'request_id':'retry-1'})
        self.assertEqual(result.status_code,202,result.text)
        self.assertEqual(result.json()['job_id'],child)
        self.assertEqual(self.worker.call_args.args[1],child)
        self.assertEqual(self.worker.call_args.args[2],self.root/child/'source.video')
        self.assertEqual(len(self.worker.call_args_list),calls+1)
        self.assertEqual(len(self.groups()),2)
        owner=json.loads((self.root/child/'owner.json').read_text())
        for key in ['history_id','creation_order','created_at','prompt','requested_clip_count','parent_clip']:
            self.assertEqual(owner[key],before[key])
        self.assertEqual(len(owner['retry_attempts']),1)
        self.assertFalse((self.root/child/'failure.json').exists())
        self.assertEqual(self.client.post(url,headers=self.headers,json={'request_id':'retry-2'}).status_code,202)
        self.assertEqual(len(self.worker.call_args_list),calls+1)  # Active retry cannot enqueue twice.
        projects_store.fail_feature(child,'Second fixture failure')
        self.assertEqual(self.client.post(url,headers=self.headers,json={'request_id':'retry-1'}).status_code,202)
        self.assertEqual(len(self.worker.call_args_list),calls+1)
        self.assertEqual(self.client.post(url,headers=self.headers,json={'request_id':'retry-2'}).status_code,202)
        self.assertEqual(len(self.worker.call_args_list),calls+2)
        self.done(child,1);core_jobs.jobs.clear()
        self.assertEqual(len(self.groups()),2)
        self.assertEqual(self.groups()[1]['state'],'done')
        self.assertEqual(self.client.post(url,headers=self.headers,json={'request_id':'retry-3'}).status_code,409)

    def test_queue_failure_is_a_saved_failed_history_entry(self):
        self.worker.side_effect=RuntimeError('fixture executor unavailable')
        response=self.upload(3)
        self.assertEqual(response.status_code,202)
        history=self.groups()
        self.assertEqual(len(history),1)
        self.assertEqual(history[0]['requested_clip_count'],3)
        self.assertEqual(history[0]['state'],'error')
        self.assertIn('Could not queue generation',history[0]['message'])

    def test_retry_freezes_legacy_history_time_and_order(self):
        jid=self.upload(2).json()['job_id']
        path=self.root/jid/'owner.json';owner=json.loads(path.read_text())
        for key in ['created_at','history_id','creation_order']:owner.pop(key)
        core_jobs.save_json(path,owner)
        projects_store.fail_feature(jid,'Legacy fixture failure')
        before=self.groups()[0]
        url=f'/api/projects/{self.project}/generations/{jid}/retry'
        self.assertEqual(self.client.post(url,headers=self.headers,json={'request_id':'legacy-retry'}).status_code,202)
        after=self.groups()[0]
        self.assertEqual(before['created_at'],after['created_at'])
        self.assertEqual(before['order'],after['order'])
        self.assertEqual(before['history_id'],after['history_id'])
