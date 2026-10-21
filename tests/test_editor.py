"""Editor tests: real owner-checked persistence and FFmpeg, mocked paid AI."""
import json
import io
import base64
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import app1
from backend import editor_backend as editor


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_temp = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.media_temp.name) / 'fixture.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=320x180:d=3', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(cls.fixture)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.media_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app1, 'JOBS_DIR', Path(self.temp.name)), patch.object(app1, 'verify_clerk_token', side_effect=lambda token: token)]
        for p in self.patches: p.start()
        self.client = TestClient(app1.app)
        self.headers = {'Authorization':'Bearer editor-user'}
        self.pid = self.client.post('/api/projects',headers=self.headers,json={'name':'Editor'}).json()['id']
        self.base = '/api/projects/'+self.pid+'/editor'
        self.jid = self.job(1, 'a'*32)
        self.url = self.base+'/'+self.jid+'/0'

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()
        app1.jobs.clear()

    def job(self, count, jid, kind='generation', parent=None):
        folder = app1.JOBS_DIR / jid
        folder.mkdir()
        app1.save_json(folder/'owner.json', {'user_id':'editor-user','project_id':self.pid,'kind':kind,'parent_job':parent})
        clips = []
        for i in range(count):
            shutil.copyfile(self.fixture, folder/f'clip_{i+1}.mp4')
            (folder/f'clip_{i+1}.vtt').write_text('WEBVTT\n\n00:00.500 --> 00:02.500\nHello world\n\n')
            clips.append({'start':101,'end':104,'title':'Clip','clip_url':f'/clips/{jid}/clip_{i+1}.mp4','captions_url':f'/clips/{jid}/clip_{i+1}.vtt'})
        app1.save_json(folder/'results.json',{'clips':clips})
        return jid

    def get(self,url=None):
        result=self.client.get(url or self.url,headers=self.headers)
        self.assertEqual(result.status_code,200,result.text[:500])
        return result.json()

    def test_effects_persist_validate_and_change_real_export(self):
        draft=self.get()['draft']
        draft['state']['captions']['enabled']=False
        original=self.client.post(self.url+'/export',headers=self.headers,json=draft['state'])
        self.assertEqual(original.status_code,200)
        draft['state']['effects']={'brightness':1.1,'contrast':1.2,'saturation':0,'grayscale':True}
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,200)
        self.assertEqual(self.get()['draft']['state']['effects'],draft['state']['effects'])
        result=self.client.post(self.url+'/export',headers=self.headers,json=draft['state'])
        self.assertEqual(result.status_code,200,result.text[:100] if result.status_code!=200 else '')
        colors=[]
        for number,data in enumerate([original.content,result.content]):
            path=Path(self.temp.name)/f'effect-{number}.mp4';path.write_bytes(data)
            rgb=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
            colors.append(list(rgb))
        self.assertGreater(max(colors[0])-min(colors[0]),100)
        self.assertLess(max(colors[1])-min(colors[1]),5)
        draft['state']['effects']['brightness']=2
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,422)

    def test_selected_zip_renders_exact_selection_and_rejects_duplicates(self):
        import zipfile
        self.job(2,'b'*32)
        edit=self.get()['draft']['state'];edit.update(start=.5,end=1.5)
        edit['captions']['enabled']=False
        entries=[{'job_id':self.jid,'clip_index':0,'edit':edit},{'job_id':'b'*32,'clip_index':1,'edit':edit}]
        result=self.client.post(self.base+'/export-selected',headers=self.headers,json={'clips':entries})
        self.assertEqual(result.status_code,200,result.text[:200] if result.status_code!=200 else '')
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            self.assertEqual(len(archive.namelist()),2)
            self.assertIn('clip-2-bbbbbbbb',archive.namelist()[1])
            for name in archive.namelist():
                path=Path(self.temp.name)/name;path.write_bytes(archive.read(name))
                duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]))
                self.assertAlmostEqual(duration,1,delta=.12)
        duplicate=self.client.post(self.base+'/export-selected',headers=self.headers,json={'clips':[entries[0],entries[0]]})
        self.assertEqual(duplicate.status_code,422)
        denied=self.client.post(self.base+'/export-selected',headers={'Authorization':'Bearer other'},json={'clips':entries})
        self.assertEqual(denied.status_code,404)

    def test_detailed_caption_chat_action_keeps_effects_and_history(self):
        state=editor.Edit(start=0,end=3,effects=editor.Effects(contrast=1.2))
        style=state.captions.model_copy(update={'font':'Georgia','size':60,'opacity':.5})
        with patch.object(editor,'request_edit',return_value=editor.Proposal(message='Style',actions=[editor.Action(type='caption_settings',settings=style)])):
            result=self.client.post(self.url+'/chat',headers=self.headers,json={'message':'Make the text larger with Georgia and a background','state':state.model_dump()})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['state']['captions']['size'],60)
        self.assertEqual(result.json()['state']['effects']['contrast'],1.2)

    def test_one_and_variable_sessions_and_derived_styles(self):
        listing=self.get(self.base)
        self.assertEqual([len(s['clips']) for s in listing['sessions']],[1])
        self.job(5,'b'*32)
        self.job(2,'c'*32,'caption-styles',self.jid)
        listing=self.get(self.base)
        self.assertEqual([len(s['clips']) for s in listing['sessions']],[3,5])
        self.assertEqual(listing['sessions'][0]['clips'][1]['job_id'],'c'*32)
        self.assertTrue(self.get(self.base+'/'+'c'*32+'/0')['burned_in'])
        self.assertEqual(self.client.post(self.base+'/'+'b'*32+'/4/save-clip',headers=self.headers).status_code,200)
        self.assertIn({'job_id':'b'*32,'clip_index':4},self.client.get('/api/projects/'+self.pid,headers=self.headers).json()['saved_clips'])
        result=self.client.get(self.base+'/'+'b'*32+'/4/media',headers=self.headers)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.content,self.fixture.read_bytes())

    def test_drafts_independent_restore_and_selection(self):
        self.job(2,'b'*32)
        draft=self.get()['draft']
        self.assertEqual(draft['state']['start'],0)  # Never the source's 101s offset.
        draft['state']['start']=1
        draft['state']['captions']['color']='#ffff00'
        draft['chat']=[{'role':'user','text':'Make captions yellow'}]
        draft['updated_at']=123
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,200)
        app1.jobs.clear()
        self.assertEqual(self.get()['draft'],draft)
        other=self.get(self.base+'/'+'b'*32+'/1')['draft']
        self.assertEqual(other['state']['start'],0)
        self.assertEqual(other['chat'],[])
        self.assertEqual(self.get(self.base)['selection'],{'job_id':self.jid,'clip_index':0})

    def test_ownership_missing_and_invalid_state(self):
        self.assertEqual(self.client.get(self.url).status_code,401)
        self.assertEqual(self.client.get(self.url,headers={'Authorization':'Bearer other'}).status_code,404)
        self.assertEqual(self.client.get(self.base+'/'+self.jid+'/9',headers=self.headers).status_code,404)
        self.assertIsNotNone(editor.validate_edit(editor.Edit(start=1.99,end=2.04),3))
        draft=self.get()['draft']
        for start,end in [(-1,2),(2,1),(0,999),(1,1.01)]:
            draft['state'].update(start=start,end=end)
            self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,422)
        draft=self.get()['draft']; draft['state']['captions']['color']='red; execute'
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,422)
        with patch.object(app1,'save_json',side_effect=OSError('disk unavailable')):
            client=TestClient(app1.app,raise_server_exceptions=False)
            self.assertEqual(client.put(self.url,headers=self.headers,json=self.get()['draft']).status_code,500)

    def test_chat_validated_transaction_provider_failure_and_no_key(self):
        state=self.get()['draft']['state']
        proposal=editor.Proposal(message='Trimmed one second and made captions yellow.', actions=[editor.Action(type='trim_first',seconds=1),editor.Action(type='caption_color',color='#ffff00')])
        with patch.object(editor,'request_edit',return_value=proposal) as ai:
            result=self.client.post(self.url+'/chat',headers=self.headers,json={'state':state,'message':'trim and yellow','chat':[]})
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['state']['start'],1)
            self.assertEqual(result.json()['state']['captions']['color'],'#ffff00')
            self.assertEqual(ai.call_args.args[0]['transcript'][0]['start'],.5)
        with patch.object(editor,'request_edit',return_value=editor.Proposal(message='Bad',actions=[editor.Action(type='trim_first',seconds=99)])):
            self.assertEqual(self.client.post(self.url+'/chat',headers=self.headers,json={'state':state,'message':'bad'}).status_code,422)
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            self.assertEqual(self.client.post(self.url+'/chat',headers=self.headers,json={'state':state,'message':'hello'}).status_code,503)
        with patch.dict(os.environ,{'OPENAI_API_KEY':'mock'}), patch.object(editor.httpx,'post',side_effect=editor.httpx.ConnectError('private info')):
            result=self.client.post(self.url+'/chat',headers=self.headers,json={'state':state,'message':'hello'})
            self.assertEqual(result.status_code,502)
            self.assertNotIn('private info',result.text)
        with self.assertRaises(ValidationError): editor.Action(type='shell',command='anything')
        with self.assertRaises(HTTPException): editor.apply_actions(editor.Edit(**state),[editor.Action(type='caption_color')],3)

    def test_ai_request_schema_and_response_validation(self):
        from types import SimpleNamespace
        valid = {'message':'Which part should I keep?', 'actions':[]}
        mock_response = SimpleNamespace(status_code=200, json=lambda: {'status':'completed', 'output':[{'content':[{'type':'output_text','text':json.dumps(valid)}]}]})
        with patch.dict(os.environ, {'OPENAI_API_KEY':'mock-key'}), patch.object(editor.httpx, 'post', return_value=mock_response) as post:
            proposal = editor.request_edit({'request':'make it shorter'})
            self.assertEqual(proposal.actions, [])
            payload = post.call_args.kwargs['json']
            self.assertEqual(payload['text']['format']['type'], 'json_schema')
            self.assertTrue(payload['text']['format']['strict'])
            self.assertFalse(payload['store'])
            self.assertNotIn('mock-key', json.dumps(payload))
        invalid = SimpleNamespace(status_code=200, json=lambda: {'status':'completed', 'output':[{'content':[{'type':'output_text','text':'{"message":"ok","actions":[{"type":"shell"}]}'}]}]})
        with patch.dict(os.environ, {'OPENAI_API_KEY':'mock-key'}), patch.object(editor.httpx, 'post', return_value=invalid):
            with self.assertRaises(HTTPException) as error:
                editor.request_edit({})
            self.assertEqual(error.exception.status_code,502)
        for actions, expected in [([editor.Action(type='keep_first',seconds=1)], (0,1)),
                                  ([editor.Action(type='trim_first',seconds=1), editor.Action(type='reset_trim')], (0,3))]:
            result=editor.apply_actions(editor.Edit(start=0,end=3),actions,3)
            self.assertEqual((result.start,result.end),expected)

    def test_vtt_entities_are_plain_text_without_mutating_manual_edits(self):
        text="Let's say <that> & \"again\"."
        path=Path(self.temp.name)/'escaped.vtt'
        app1.write_captions(path,[{'start':100,'end':102,'text':text}],100,103)
        self.assertNotIn('&#x27;',path.read_text())
        cues=editor.parse_vtt(path.read_text())
        self.assertEqual(cues,[{'start':0,'end':2,'text':text}])
        legacy=editor.parse_vtt('WEBVTT\n\n00:00.500 --> 00:02.500\n<b>Let&#x27;s</b> &amp; &lt;tag&gt; &#39;again&#39;\n')
        self.assertEqual(legacy[0]['text'],"Let's & <tag> 'again'")
        state=editor.Edit(start=1,end=2,texts={'0':'Keep literal &#x27; if typed'})
        self.assertEqual(editor.trimmed_cues(legacy,state)[0],{'start':0,'end':1,'text':'Keep literal &#x27; if typed'})
        self.assertIn("Let's",editor.make_ass(legacy,state.captions,320,180))

    def test_trimmed_caption_timing_and_real_export(self):
        state=editor.Edit(start=1,end=2,captions=editor.Captions(color='#ffff00',bold=True,position='top',background='#ff0000',opacity=.5))
        cues=editor.trimmed_cues([{'start':.5,'end':2.5,'text':'Hello {tag} \\bad'}],state)
        self.assertEqual((cues[0]['start'],cues[0]['end']),(0,1))
        ass=editor.make_ass(cues,state.captions,320,180)
        self.assertNotIn('{tag}',ass)
        self.assertIn('Background',ass)
        before=self.fixture.read_bytes()
        response=self.client.post(self.url+'/export',headers=self.headers,json=state.model_dump())
        self.assertEqual(response.status_code,200,response.text[:200] if response.status_code!=200 else '')
        exported=Path(self.temp.name)/'exported.mp4'; exported.write_bytes(response.content)
        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(exported)]))
        self.assertAlmostEqual(duration,1,delta=.1)
        self.assertEqual((app1.JOBS_DIR/self.jid/'clip_1.mp4').read_bytes(),before)
        # Caption controls must affect encoded pixels, not merely metadata.
        state.captions.enabled=False
        clean=self.client.post(self.url+'/export',headers=self.headers,json=state.model_dump())
        plain=Path(self.temp.name)/'plain.mp4'; plain.write_bytes(clean.content)
        def frame(path):
            return subprocess.check_output(['ffmpeg','-v','error','-ss','0.5','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        self.assertNotEqual(frame(exported),frame(plain))

    def test_caption_text_state_export_and_invalid_rasters(self):
        from PIL import Image
        draft=self.get()['draft']; draft['state']['texts']={'0':'Changed caption'}
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,200)
        self.assertEqual(self.get()['draft']['state']['texts'],{'0':'Changed caption'})
        state=editor.Edit(**draft['state'])
        cues=editor.trimmed_cues([{'start':.5,'end':2.5,'text':'Original'}],state)
        self.assertEqual(cues[0]['text'],'Changed caption')
        self.assertIn('Changed caption',editor.make_ass(cues,state.captions,320,180))
        good=editor.apply_actions(state,[editor.Action(type='caption_text',cue_index=0,text='AI text')],3,1)
        self.assertEqual(good.texts['0'],'AI text')
        with self.assertRaises(HTTPException):
            editor.apply_actions(state,[editor.Action(type='caption_text',cue_index=9,text='Missing')],3,1)
        buffer=io.BytesIO(); Image.new('RGBA',(320,180),(255,255,0,128)).save(buffer,format='PNG')
        overlay={'start':.5,'end':2.5,'png':base64.b64encode(buffer.getvalue()).decode()}
        payload={**draft['state'],'overlays':[overlay]}
        result=self.client.post(self.url+'/export',headers=self.headers,json=payload)
        self.assertEqual(result.status_code,200,result.text[:100] if result.status_code!=200 else '')
        for invalid in [{'start':0,'end':2.5,'png':overlay['png']}, {'start':.5,'end':2.5,'png':'invalid'}, {'start':.5,'end':2.5,'png':base64.b64encode(b'not a PNG').decode()}]:
            result=self.client.post(self.url+'/export',headers=self.headers,json={**draft['state'],'overlays':[invalid]})
            self.assertEqual(result.status_code,422,result.text)

    def test_aspect_ratios_persist_validate_and_export_even_frames(self):
        draft=self.get()['draft']
        draft['state']['composition']={'ratio':'9:16','mode':'fill','x':1,'y':.5,'background':'#334455'}
        self.assertEqual(self.client.put(self.url,headers=self.headers,json=draft).status_code,200)
        self.assertEqual(self.get()['draft']['state']['composition'],draft['state']['composition'])
        for ratio in ['original','9:16','1:1','4:5','16:9','4:3']:
            with self.subTest(ratio=ratio):
                state=editor.Edit(start=.5,end=1,captions=editor.Captions(enabled=False),composition=editor.Composition(ratio=ratio))
                response=self.client.post(self.url+'/export',headers=self.headers,json=state.model_dump())
                self.assertEqual(response.status_code,200,response.text[:100] if response.status_code!=200 else '')
                output=Path(self.temp.name)/'aspect.mp4';output.write_bytes(response.content)
                probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(output)]))['streams'][0]
                self.assertEqual(probe['width']%2,0);self.assertEqual(probe['height']%2,0)
                if ratio!='original':
                    a,b=map(int,ratio.split(':'));self.assertEqual(probe['width']/probe['height'],a/b)
        for invalid in [{'ratio':'17:4'}, {'mode':'stretch'}, {'x':2}, {'background':'bad'}]:
            bad={**draft,'state':{**draft['state'],'composition':{**draft['state']['composition'],**invalid}}}
            self.assertEqual(self.client.put(self.url,headers=self.headers,json=bad).status_code,422)
        state=editor.Edit(start=0,end=3,composition=editor.Composition(ratio='4:5',mode='fill',x=.2))
        result=editor.apply_actions(state,[editor.Action(type='trim_first',seconds=1)],3)
        self.assertEqual(result.composition,state.composition)

    def test_static_assets_and_unchanged_canvas(self):
        for name in ['editor_broll.js','editor_C.js','editor_C.css','editor_state.js','editor_captions.js','editor_timeline.js','editor_C.html']:
            self.assertEqual(self.client.get('/'+name).status_code,200)
        self.assertNotIn('editor_C.js',self.client.get('/canvas_C.html').text)


if __name__=='__main__': unittest.main()
