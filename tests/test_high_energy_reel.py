"""Measured beats, phrase-safe clocks, real retimed AV and complete style execution."""
import array
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from backend.editor.models import Edit,Action,Proposal
from backend.editor.advanced_models import TimelineSpan,SpeedRamp
from backend.editor.retiming import Clock,validate_timing,mapped_state,phrases
from backend.editor.beats import analyze
from backend.editor.audio_assets import AudioStore
from backend.editor import ai
from tests.test_editor import EditorTests as Fixture

class ReelClockTests(unittest.TestCase):
    def test_shared_clock_exact_inverse_and_speech_guard(self):
        state=Edit(start=0,end=10,timeline=[TimelineSpan(start=2,end=10)],speed=[SpeedRamp(start=4,end=6,rate_from=1,rate_to=2)])
        cues=[{'start':2,'end':3.8,'text':'First complete phrase.'},{'start':6.2,'end':9,'text':'Second full phrase!'}]
        validate_timing(state,cues,10);clock=Clock(state)
        self.assertLess(clock.duration,8)
        for t in [2,3,4.1,5.5,6.2,8,9.9]:self.assertAlmostEqual(clock.source(clock.output(t)),t,places=6)
        unsafe=state.model_copy(update={'speed':[SpeedRamp(start=3,end=5)]})
        with self.assertRaisesRegex(HTTPException,''):validate_timing(unsafe,cues,10)
        cut=state.model_copy(update={'timeline':[TimelineSpan(start=3,end=10)]})
        with self.assertRaises(HTTPException):validate_timing(cut,cues,10)
        with self.assertRaises(HTTPException):validate_timing(state,[],10)
    def test_complete_phrases_not_individual_cue_words(self):
        cues=[{'start':0,'end':1,'text':'You are'},{'start':1.01,'end':2,'text':'my best friend.'},{'start':3,'end':4,'text':'Wait!'}]
        self.assertEqual(len(phrases(cues)),2)
        with self.assertRaises(HTTPException):validate_timing(Edit(start=0,end=4,timeline=[TimelineSpan(start=1.01,end=4)]),cues,4)
    def test_measured_beats_and_no_fake_silence_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            store=AudioStore(Path(directory));assets=store.library();music=next(a for a in assets if a['name']=='Reel pulse')
            result=analyze(store.media(music['id']))
            self.assertGreater(len(result['beats']),25);self.assertGreater(result['confidence'],.18)
            self.assertAlmostEqual(result['bpm'],120,delta=5)
            path=Path(directory)/'silence.wav'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','anullsrc=r=22050:cl=mono','-t','3',str(path)],check=True)
            self.assertEqual(analyze(path)['beats'],[])

class ReelRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):Fixture.setUpClass()
    @classmethod
    def tearDownClass(cls):Fixture.tearDownClass()
    def setUp(self):
        self.fx=Fixture();self.fx.setUp();self.client=self.fx.client;self.url=self.fx.url;self.headers=self.fx.headers
        from backend.core import jobs
        self.jobs=jobs
        source=jobs.JOBS_DIR/self.fx.jid/'clip_1.mp4'
        # The gap at 2–4s is confirmed non-speech and suitable for a speed ramp.
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=10','-f','lavfi','-i','sine=frequency=440:duration=10','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True)
        (source.with_suffix('.vtt')).write_text('WEBVTT\n\n00:00.300 --> 00:02.000\nWhy is Teddy your best friend?\n\n00:04.000 --> 00:05.800\nWait for the whole story.\n\n00:06.000 --> 00:09.300\nThis is the final complete phrase!\n')
    def tearDown(self):self.fx.tearDown()
    def get(self):return self.fx.get()['draft']['state']
    def test_style_plan_save_real_export_and_speech_pitch(self):
        actions=[Action(type='high_energy_reel')]
        with patch.object(ai,'request_edit',return_value=Proposal(message='Plan',actions=actions)):
            response=self.client.post(self.url+'/chat',headers=self.headers,json={'state':self.get(),'message':'Make this a polished high-energy Reel with a strong opening, beat-synced edits, bold animated captions, selective punch-in zooms, relevant B-roll, and music that stays beneath the dialogue.'})
        self.assertEqual(response.status_code,200,response.text);data=response.json();state=data['state']
        self.assertTrue(state['speed']);self.assertTrue(state['timeline']);self.assertTrue(state['reel']['beats'])
        self.assertLessEqual(len(state['motion']),3);self.assertLessEqual(sum(m['shake']>0 for m in state['motion']),1)
        beat_clock=Clock(Edit(**state))
        for motion in state['motion']:
            self.assertLess(min(abs(beat_clock.output(motion['start'])-beat) for beat in state['reel']['beats']),.002)
        self.assertEqual(state['captions']['max_words'],4)
        self.assertEqual(self.client.put(self.url,headers=self.headers,json={'state':state}).status_code,200)
        self.assertEqual(self.get(),state)
        result=self.client.post(self.url+'/export',headers=self.headers,json=state)
        self.assertEqual(result.status_code,200,result.text[:300] if result.status_code!=200 else '')
        path=Path(self.fx.temp.name)/'reel.mp4';path.write_bytes(result.content)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type','-of','json',str(path)]))
        clock=Clock(Edit(**state));self.assertAlmostEqual(float(probe['format']['duration']),clock.duration,delta=.12)
        self.assertTrue(any(s['codec_type']=='audio' for s in probe['streams']))
        # The 440Hz source/dialogue tone is not pitch-shifted by ramping a silent region.
        pcm=array.array('f');pcm.frombytes(subprocess.check_output(['ffmpeg','-v','error','-ss','0.5','-i',str(path),'-t','0.5','-ar','16000','-ac','1','-f','f32le','-']))
        def amplitude(f):return abs(sum(x*complex(math.cos(2*math.pi*f*i/16000),-math.sin(2*math.pi*f*i/16000)) for i,x in enumerate(pcm)))/len(pcm)
        self.assertGreater(amplitude(440),amplitude(660)*3)
        self.assertEqual(self.client.get(self.url,headers={'Authorization':'Bearer intruder'}).status_code,404)
        shutil.copyfile(path,'/tmp/cascade-reel-test.mp4')
    def test_invalid_speed_does_not_destroy_partial_success(self):
        with patch.object(ai,'request_edit',return_value=Proposal(message='Plan',actions=[Action(type='caption_color',color='#ffff00'),Action(type='speed_ramp',speed={'start':.5,'end':1.5,'rate_from':1,'rate_to':2})])):
            r=self.client.post(self.url+'/chat',headers=self.headers,json={'state':self.get(),'message':'Make captions yellow and add a speed ramp.'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['state']['speed'],[])
        self.assertEqual(r.json()['state']['captions']['color'],'#ffff00')
        self.assertEqual(r.json()['report'][1]['status'],'failed')
