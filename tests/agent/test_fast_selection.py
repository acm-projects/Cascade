"""Fast spoken selection and parallel indexing: no paid services or model downloads."""
import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
from PIL import Image

from backend.agent import index as indexing
from backend.agent import fast_selection
from backend.agent.index import VideoIndex
from backend.agent.tools import ToolBox
from backend.agent.website import transcript_first_request
from backend.cascade_llm.structured import StructuredResult
from backend.generation import reuse_source


def long_index():
    # A 2h10m timeline with distinct topics and speaker turns, including material after hour two.
    transcript = [{'start': float(t), 'end': float(t + 18), 'speaker': (t // 20) % 2,
                   'text': f'Archive chapter {t // 1200}: public health history and reporting. ' * 3}
                  for t in range(0, 7800, 20)]
    return VideoIndex(7800, 2, [], np.zeros((0, 1)), transcript, np.zeros((len(transcript), 1)))


def candidate(start, **extra):
    return {'start_time': start, 'end_time': start + 18, 'title': 'Archive turning point',
            'reason': 'Explains the historical change in context', 'score': .9, 'reference_matches': [], **extra}


def test_fast_selection_handles_two_hours_plus_and_late_moments(monkeypatch):
    box = ToolBox(long_index(), Path('unused'), target_clips=4)
    calls = []
    def structured(prompt, schema, **kwargs):
        calls.append(prompt)
        return StructuredResult({'candidates': [candidate(t) for t in [40, 2000, 4000, 7500]]}, 100, 200)
    monkeypatch.setattr(fast_selection, 'structured_json', structured)
    result = fast_selection.run_transcript_selection(box, 'History documentary highlights', lambda _: None)
    assert len(calls) == 1
    assert len(result['suggestions']) == 4
    assert result['suggestions'][-1]['start'] > 7200
    assert '[7780.0-7798.0s]' in calls[0]  # The end of the source is not truncated.


def test_fast_selection_retries_rejected_old_and_out_of_range_candidates(monkeypatch):
    box = ToolBox(long_index(), Path('unused'), target_clips=2, intent='specific', exclude_windows=[[40, 80]])
    replies = iter([[candidate(40), candidate(7900), candidate(2000)], [candidate(7500)]])
    monkeypatch.setattr(fast_selection, 'structured_json', lambda *a, **kw:
                        StructuredResult({'candidates': next(replies)}, 10, 20))
    result = fast_selection.run_transcript_selection(box, 'Find historical reforms', lambda _: None)
    assert result['iterations'] == 2
    assert [clip['start'] for clip in result['suggestions']] == [2000, 7500]


def test_spoken_fast_path_preserves_explicit_visual_requests():
    assert transcript_first_request('Find key public healthcare explanations in this documentary')
    assert transcript_first_request('Find the historical turning points discussed in this interview')
    assert not transcript_first_request('Find battle footage in this history documentary')
    assert not transcript_first_request('Find funny moments')


def test_video_indexes_overlap_and_progress_callbacks_stay_on_caller(monkeypatch, tmp_path):
    import backend.video_search as package
    barrier = threading.Barrier(2, timeout=3)
    caller = threading.get_ident()
    progress_threads = []
    fake = SimpleNamespace(load_models=lambda *a: None,
        search_model=SimpleNamespace(encode=lambda values, **kw: np.ones((len(values), 2))),
        visual_model=SimpleNamespace(encode=lambda values, **kw: np.ones((len(values), 2))))
    monkeypatch.setattr(package, 'router', fake, raising=False)
    monkeypatch.setattr(indexing, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(indexing, 'file_sha256', lambda _: 'fixture')
    monkeypatch.setattr('backend.media.probe_media', lambda _: {'duration': 7800., 'has_video': True})
    def transcribe(*a, **kw):
        barrier.wait()
        kw['progress']('Transcription started')
        return [{'start': 7500., 'end': 7518., 'text': 'Late history chapter'}]
    def frames(path, folder, duration, interval):
        barrier.wait()
        folder.mkdir()
        image = folder / 'frame.jpg'
        Image.new('RGB', (16, 16)).save(image)
        return [7500.], [image]
    monkeypatch.setattr(indexing, 'transcribe_media', transcribe)
    monkeypatch.setattr(indexing, '_sample_frames', frames)
    index = indexing.build_index(Path('unused'), tmp_path, progress=lambda _: progress_threads.append(threading.get_ident()))
    assert index.duration == 7800
    assert index.transcript[0]['start'] == 7500
    assert all(thread == caller for thread in progress_threads)
    assert set(index.timings) == {'transcript_index_seconds', 'visual_index_seconds', 'index_wall_seconds'}


def test_reuse_source_falls_back_when_hard_links_are_unavailable(monkeypatch, tmp_path):
    source, destination = tmp_path / 'original', tmp_path / 'followup'
    source.write_bytes(b'owned source')
    monkeypatch.setattr('backend.generation.os.link', Mock(side_effect=OSError('different volume')))
    digest = reuse_source(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert digest.hexdigest() == hashlib.sha256(source.read_bytes()).hexdigest()
