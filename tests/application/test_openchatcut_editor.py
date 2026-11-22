"""OpenChatCut sequences: settings validation and the render spec (no network)."""
import json
import tempfile
import unittest
from pathlib import Path

from backend.editor.audio_assets import AudioStore
from backend.editor.models import Edit
from backend.editor.openchatcut_render import build_spec
from backend.editor.sequence_models import OPENCHATCUT_ENGINE, FablecutSequence, SequenceShot


class OpenChatCutSequenceTests(unittest.TestCase):
    def test_engine_specific_settings_are_validated(self):
        with self.assertRaises(ValueError):  # OpenChatCut never claims an unexecuted ramp
            FablecutSequence(engine=OPENCHATCUT_ENGINE, shots=[SequenceShot(start=0, end=2, rate_from=1.5, rate_to=.5)])
        with self.assertRaises(ValueError):  # FableCut cannot execute OpenChatCut-only transitions
            FablecutSequence(shots=[SequenceShot(start=0, end=2), SequenceShot(start=3, end=5, transition='flash')])
        legacy = FablecutSequence.model_validate({'shots': [{'start': 0, 'end': 2}]})
        self.assertEqual((legacy.engine, legacy.look, legacy.framing), ('fablecut-1.18.0', 'none', 'blur'))

    def test_spec_uses_only_verified_assets_and_maps_captions(self):
        state = Edit(start=0, end=20, fablecut=FablecutSequence(engine=OPENCHATCUT_ENGINE, look='teal-orange', title='Go', shots=[
            SequenceShot(start=0, end=2, zoom=1.2, zoom_style='punch', shake=2.5),
            SequenceShot(start=6, end=8, transition='whip', rate_from=.6, rate_to=.6)]))
        state.captions.enabled = True
        info = {'duration': 20, 'width': 960, 'height': 540, 'cues': [{'start': .5, 'end': 1.5, 'text': 'keep this spoken line'}]}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            spec, total = build_spec(state, info, AudioStore(folder/'audio'), folder/'base.mp4', folder, folder/'out.mp4')
        self.assertEqual((spec['width'], spec['height']), (1080, 1920))
        self.assertAlmostEqual(total, 2 + 2/.6, places=3)
        ids = json.dumps(spec)
        for asset in ('library:zoom:punch', 'builtin:fx-shake', 'builtin:tr-whip-pan', 'builtin:look-teal-orange'):
            self.assertIn(asset, ids)
        self.assertTrue(spec['shots'][1]['mute'])
        self.assertEqual(spec['texts'][0]['text'], 'GO')
        self.assertTrue(any(t['text'].startswith('keep this') for t in spec['texts']))
        self.assertNotIn('http', ids)



if __name__ == '__main__':
    unittest.main()
