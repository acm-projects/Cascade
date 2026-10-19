"""Merge regression: main's agent/parallel renderer feeds the owner-scoped editor."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import app1
from backend import editor_backend as editor
from backend.agent.tools import ToolBox


class MainEditorIntegrationTests(unittest.TestCase):
    def test_agent_count_and_audio_continue_through_editor_chat_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=160x120:r=12:d=40',
                            '-f','lavfi','-i','sine=frequency=440:duration=40','-c:v','libx264',
                            '-c:a','aac','-shortest',str(source)],check=True)
            with patch.object(app1,'JOBS_DIR',root),patch.object(app1,'verify_clerk_token',side_effect=lambda token:token), \
                 patch.dict(os.environ,{'CASCADE_STORAGE':'local','CASCADE_WARM_MODELS':'0'}), \
                 patch.object(app1,'requirements_error',return_value=None),patch.object(app1.worker,'submit') as submit:
                client=TestClient(app1.app);headers={'Authorization':'Bearer merge-fixture'}
                pid=client.post('/api/projects',headers=headers,json={'name':'Merged pipeline'}).json()['id']
                response=client.post('/upload',headers=headers,data={'project_id':pid,'search':'Useful explanations','clip_count':5},
                                     files={'video':('source.mp4',source.read_bytes(),'video/mp4')})
                self.assertEqual(response.status_code,202,response.text)
                jid=response.json()['job_id'];self.assertIs(submit.call_args.args[0],app1.process_upload)
                def agent(path,duration,prompt,target,progress,stage,requested_count=4):
                    self.assertEqual(requested_count,5)
                    progress('Mocked agent selection; real parallel media renders')
                    return ([{'start':i*7.,'end':i*7.+5,'title':f'Moment {i}','explanation':'Fixture'} for i in range(5)],
                            [{'start':i*7.,'end':i*7.+4,'text':f'Caption {i}'} for i in range(5)],{'provider':'fixture','model':'mock','selection_note':''})
                with patch.object(app1,'select_with_agent',side_effect=agent):
                    submit.call_args.args[0](*submit.call_args.args[1:])
                self.assertEqual(app1.jobs[jid]['state'],'done');self.assertEqual(len(app1.jobs[jid]['clips']),5)
                self.assertEqual(app1.jobs[jid]['clips'][4]['clip_id'],jid+':4')
                url=f'/api/projects/{pid}/editor/{jid}/4'
                info=client.get(url,headers=headers).json();state=info['draft']['state']
                self.assertIn('Caption 4',info['cues'][0]['text'])
                original=(root/jid/'clip_5.mp4').read_bytes()
                proposal=editor.Proposal(message='Trim and captions',actions=[editor.Action(type='trim_first',seconds=1),editor.Action(type='caption_color',color='#ffff00')])
                with patch.object(editor,'request_edit',return_value=proposal):
                    response=client.post(url+'/chat',headers=headers,json={'state':state,'message':'Trim first second and make captions yellow'})
                self.assertEqual(response.status_code,200,response.text);state=response.json()['state']
                self.assertEqual(state['start'],1);self.assertEqual(state['captions']['color'],'#ffff00')
                state['composition']['ratio']='9:16'
                draft={'state':state,'chat':[{'role':'user','text':'Trim first second'}],'updated_at':1}
                self.assertEqual(client.put(url,headers=headers,json=draft).status_code,200)
                self.assertEqual(client.get(url,headers=headers).json()['draft'],draft)
                response=client.post(url+'/export',headers=headers,json=state)
                self.assertEqual(response.status_code,200)
                output=root/'edited.mp4';output.write_bytes(response.content)
                probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(output)]))
                self.assertAlmostEqual(float(probe['format']['duration']),4,delta=.15)
                video=next(s for s in probe['streams'] if s['codec_type']=='video')
                self.assertAlmostEqual(video['width']/video['height'],9/16)
                self.assertTrue(any(s['codec_type']=='audio' for s in probe['streams']))
                self.assertEqual((root/jid/'clip_5.mp4').read_bytes(),original)
                self.assertEqual(client.get(url,headers={'Authorization':'Bearer another-user'}).status_code,404)
                self.assertNotIn('broll',state)
            app1.jobs.clear()

    def test_agent_count_is_per_request_and_defaults_stay_four(self):
        five=ToolBox(SimpleNamespace(duration=200),Path('fixture.mp4'),target_clips=5)
        four=ToolBox(SimpleNamespace(duration=200),Path('fixture.mp4'))
        candidates=[{'id':i,'start':i*25.,'end':i*25.+8,'score':.9,'title':'Fixture','reason':'Supported'} for i in range(7)]
        five.candidates=candidates;four.candidates=candidates
        self.assertEqual(len(five.final_selection()),5);self.assertEqual(len(four.final_selection()),4)
        with self.assertRaises(ValueError):ToolBox(SimpleNamespace(duration=200),Path('fixture.mp4'),target_clips=13)


if __name__=='__main__':unittest.main()
