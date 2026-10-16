"""Local multi-clip ranking and real audio/caption rendering; no API calls."""
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
from starlette.datastructures import UploadFile
from backend.video_search.selection import select_windows, select_matches


class LocalSelectionTests(unittest.TestCase):
    def test_clustered_speech_can_use_shorter_clips_for_four_distinct_moments(self):
        anchors = [{'time': i + 1, 'score': .8, 'match': str(i), 'evidence_start': i, 'evidence_end': i + 2}
                   for i in range(0, 36, 3)]
        self.assertLess(len(select_windows(anchors, 133, 30, 3)), 4)
        selected = sorted(select_matches(anchors, 133, 30, 3), key=lambda c: c['start'])
        self.assertEqual(len(selected), 4)
        self.assertTrue(all(8 <= c['end'] - c['start'] < 30 for c in selected))
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(selected, selected[1:])))

    def test_visual_selection_finds_four_without_greedy_middle_window_blocking(self):
        anchors = [{'time': i + .5, 'score': 1 if i == 45 else .2, 'match': str(i)} for i in range(0, 133, 3)]
        clips = sorted(select_windows(anchors, 133.5, 30, 5), key=lambda c: c['start'])
        self.assertEqual(len(clips), 4)
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(clips, clips[1:])))
        self.assertTrue(all(abs(c['end'] - c['start'] - 30) < .001 for c in clips))

    def test_speech_matches_remain_complete_and_clustered_matches_are_not_duplicated(self):
        anchors = [{'time': t + 1, 'score': .8, 'match': str(t), 'evidence_start': t, 'evidence_end': t + 2}
                   for t in (1, 32, 65, 98, 132)]
        clips = select_windows(anchors, 130, 30, 3)
        self.assertEqual(len(clips), 4)
        self.assertTrue(all(c['start'] <= c['evidence_start'] and c['end'] >= c['evidence_end'] for c in clips))
        self.assertEqual(len(select_windows(anchors[:1] * 4, 130, 30, 3)), 1)

    def test_short_source_and_nonfinite_scores_do_not_create_duplicate_clips(self):
        anchors = [{'time': 1, 'score': .9, 'match': 'one'}, {'time': 2, 'score': float('nan'), 'match': 'bad'}]
        self.assertEqual(len(select_windows(anchors, 12, 30, 5)), 1)
        self.assertEqual(select_windows(anchors, 0, 30, 5), [])


class LocalRenderingTests(unittest.TestCase):
    def test_both_engines_render_variable_distinct_clips_with_audio_and_local_caption_times(self):
        fake_speech = types.ModuleType('faster_whisper'); fake_speech.WhisperModel = Mock()
        fake_search = types.ModuleType('sentence_transformers'); fake_search.SentenceTransformer = Mock()
        with patch.dict(sys.modules, {'faster_whisper': fake_speech, 'sentence_transformers': fake_search}):
            router = importlib.import_module('backend.video_search.router')
        class Encoder:
            def encode(self, values, **kwargs):
                return np.array([1., 0.]) if isinstance(values, str) else np.array([[1., 0.]] * len(values))
            def similarity(self, query, embeddings):
                return np.array([[.9, .8, .7, .6, .55]])
        class Speech:
            def transcribe(self, path, **kwargs):
                starts = (0,) if Path(path).suffix == '.wav' else (1, 32, 65, 98, 132)
                return iter([types.SimpleNamespace(start=float(t), end=float(t + 2), text=f'Speech match {i}')
                             for i, t in enumerate(starts)]), None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=10:d=170',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=170', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(source)], check=True, timeout=45)
            for mode, count in [('visual',4),('speech',4),('visual',5),('speech',5)]:
                with self.subTest(mode=mode, count=count), patch.object(router, 'OUTPUTS', root), patch.object(router, 'load_models'), \
                     patch.object(router, 'visual_model', Encoder()), patch.object(router, 'search_model', Encoder()), \
                     patch.object(router, 'whisper_model', Speech()):
                    with source.open('rb') as file:
                        result = router.search_video(UploadFile(file, filename='source.mp4'), 'a spoken moment', mode, 30, requested_count=count)
                    self.assertEqual(len(result['clips']), count)
                    self.assertEqual(result['selection_note'], '')
                    ordered = sorted(result['clips'], key=lambda c: c['start'])
                    self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(ordered, ordered[1:])))
                    for clip in result['clips']:
                        output = root / Path(clip['clip_url']).name
                        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                                                 '-show_format', '-of', 'json', str(output)], timeout=30))
                        self.assertAlmostEqual(float(probe['format']['duration']), 30, delta=.15)
                        self.assertTrue(any(s['codec_type'] == 'audio' and s['codec_name'] == 'aac' for s in probe['streams']))
                        levels = subprocess.run(['ffmpeg', '-v', 'info', '-i', str(output), '-t', '2', '-vn',
                                                 '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True, timeout=30)
                        self.assertGreater(float(re.search(r'max_volume: ([-\d.]+)', levels.stderr).group(1)), -60)
                        cues = re.findall(r'(\d+):(\d+):(\d+)\.(\d+) --> (\d+):(\d+):(\d+)\.(\d+)', clip['captions_vtt'])
                        self.assertTrue(cues)
                        for cue in cues:
                            numbers = list(map(int, cue))
                            start = numbers[0] * 3600 + numbers[1] * 60 + numbers[2] + numbers[3] / 1000
                            end = numbers[4] * 3600 + numbers[5] * 60 + numbers[6] + numbers[7] / 1000
                            self.assertTrue(0 <= start < end <= 30)
