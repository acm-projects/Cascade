import tempfile
import unittest
from pathlib import Path
from fastapi import HTTPException
from backend.editor.models import Edit
from backend.editor.sequence_models import FablecutSequence, SequenceShot
from backend.editor.fablecut_render import sequence_pieces, project_document
from backend.editor.audio_assets import AudioStore
from backend.editor.validation import validate_media_edit


class SequenceTests(unittest.TestCase):
    def state(self):
        return Edit(start=0,end=20,fablecut=FablecutSequence(shots=[
            SequenceShot(start=10,end=12,zoom=1.2,shake=4),
            SequenceShot(start=2,end=6,rate_from=1.5,rate_to=.5,transition='whip')]))

    def test_clock_and_trim_intersection(self):
        state=self.state();pieces=sequence_pieces(state)
        self.assertEqual([p['start'] for p in pieces],[0,2])
        self.assertEqual(sum(p['duration'] for p in pieces),6)
        state.start=3
        self.assertEqual(sequence_pieces(state)[1]['duration'],3)
        state.start=15
        with self.assertRaises(HTTPException):sequence_pieces(state)

    def test_real_project_mutes_ramped_audio_and_maps_captions(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'media').mkdir();audio=AudioStore(folder/'audio')
            state=self.state();state.captions.animation='pop'
            project=project_document(state,{'width':960,'height':540,'cues':[{'start':10,'end':12,'text':'Keep this spoken hook'}]},audio,folder)
            self.assertEqual((project['width'],project['height']),(540,960))
            self.assertEqual(len([c for c in project['clips'] if c['id'].startswith('dialogue-')]),1)
            self.assertTrue(any(c['kind']=='text' and c['start']==0 for c in project['clips']))
            self.assertEqual(project['clips'][0]['in'],10)
            self.assertNotIn('http',str(project))

    def test_rejects_speed_or_cut_through_known_speech(self):
        state=self.state();info={'duration':20,'has_video':True,'cues':[{'start':3,'end':5,'text':'Do not warp this'}]}
        with self.assertRaises(HTTPException):validate_media_edit(state,info)

