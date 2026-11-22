"""Local planner routing, follow-up tools, ownership and shared timing contracts."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import HTTPException
from backend.editor import ai
from backend.editor.models import Edit, Action
from backend.editor.advanced_models import Motion, AudioSegment, TimelineSpan, TextOverlay
from backend.editor.audio_assets import AudioStore
from backend.editor.reel import build_reel
from backend.editor.retiming import mapped_state


class OwnershipAndTimingTests(unittest.TestCase):
    def test_style_preserves_manual_tracks_and_reapplication_replaces_owned_events(self):
        with tempfile.TemporaryDirectory() as directory:
            audio=AudioStore(Path(directory));library=audio.library();track=next(a for a in library if a['name']=='Reel pulse')
            manual=Motion(start=1,duration=.4,scale_to=1.15)
            state=Edit(start=0,end=10,motion=[manual],text_overlays=[TextOverlay(start=2,duration=1,text='Manual title')],
                audio=[AudioSegment(id='a'*32,asset_id=track['id'],start=0,duration=10,volume=.12)])
            info={'has_video':True,'duration':10,'clip_title':'A conversation','scene_boundaries':[],
                  'cues':[{'start':.2,'end':2,'text':'Why now?'},{'start':3,'end':5,'text':'This is the key reaction.'},{'start':6,'end':9.5,'text':'Keep this whole ending.'}],
                  'editor_moments':[{'at':6,'description':'Visible reaction','importance':.95,'activity':'high'}]}
            result,report=build_reel(state,info,MagicMock(),audio,Action(type='high_energy_reel'),'Make a high-energy Reel; keep the entire duration')
            self.assertIn(manual,result.motion)
            self.assertEqual(result.text_overlays,state.text_overlays)
            self.assertEqual(result.audio[0],state.audio[0])
            self.assertTrue(result.reel.generated_motion)
            self.assertTrue(any('Visible moment' in row['message'] for row in report))
            again,_=build_reel(result,info,MagicMock(),audio,Action(type='high_energy_reel'),'Make a high-energy Reel; keep the entire duration')
            self.assertEqual(len(again.motion),len(result.motion))
            self.assertEqual(again.motion.count(manual),1)
            self.assertEqual(len(again.audio),len(result.audio))
            self.assertEqual(again.audio[0],state.audio[0])

    def test_retimed_audio_leading_trim_preserves_source_offset(self):
        segment=AudioSegment(id='a'*32,asset_id='aud-'+'b'*32,start=0,duration=10,offset=2)
        state=Edit(start=5,end=10,timeline=[TimelineSpan(start=5,end=10)],audio=[segment])
        mapped,_,_=mapped_state(state,{'cues':[],'duration':10})
        self.assertEqual(mapped.audio[0].start,0)
        self.assertEqual(mapped.audio[0].offset,7)
        self.assertEqual(mapped.audio[0].duration,5)
