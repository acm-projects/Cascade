"""Latency contracts using local fixtures, blocked fake storage, and mocked AI."""
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent import index, transcript_context, website
from backend.services import followup_edit, source_backup


def test_deferred_progress_cannot_overwrite_final_success(monkeypatch, tmp_path):
    from backend.core import jobs
    started, release = threading.Event(), threading.Event()
    persisted = []
    jid = 'progress-race'
    (tmp_path/jid).mkdir()
    instance = {'state': 'queued'}
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    monkeypatch.setitem(jobs.jobs, jid, instance)
    def write(path, value):
        if value['state'] == 'processing':
            started.set()
            assert release.wait(3)
        persisted.append(dict(value))
    monkeypatch.setattr(jobs, 'metadata_store', lambda: SimpleNamespace(write=write))
    jobs.update_job(jid, state='processing', defer_persistence=True)
    assert started.wait(2)
    final = threading.Thread(target=lambda: jobs.update_job(jid, state='done'))
    final.start()
    try:
        deadline = __import__('time').monotonic()+2
        while instance['state'] != 'done' and __import__('time').monotonic() < deadline:
            __import__('time').sleep(.01)
        assert instance['state'] == 'done'
    finally:
        release.set()
        final.join(3)
    assert not final.is_alive()
    assert persisted[-1]['state'] == 'done'


def test_transcript_only_does_not_load_models_and_reuses_transcription(monkeypatch, tmp_path):
    import backend.video_search as package
    def forbidden(*args, **kwargs):
        raise AssertionError('Batch selection must not load embedding models')
    monkeypatch.setattr(package, 'router', SimpleNamespace(load_models=forbidden), raising=False)
    monkeypatch.setattr(index, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(index, 'file_sha256', lambda _: 'abc')
    monkeypatch.setattr('backend.media.probe_media', lambda _: {'duration': 120, 'has_video': True})
    calls = []
    transcript = [{'start': 0, 'end': 20, 'text': 'A complete historical explanation.'}]
    monkeypatch.setattr(index, 'transcribe_media', lambda *a, **k: calls.append(1) or transcript)
    for _ in range(2):
        built = index.build_index(Path('unused'), tmp_path, visual=False, embed_transcript=False)
        assert built.transcript == transcript
        assert built.encode_text_query is None
    assert calls == [1]
    assert not list(tmp_path.glob('*.npy'))


def test_long_context_is_bounded_relevant_and_spans_the_timeline():
    transcript = [{'start': i * 20., 'end': i * 20. + 18, 'text': ('Healthcare reforms. ' if i > 360 else 'Archive accounts. ') * 40}
                  for i in range(390)]
    context, intervals = transcript_context.selection_context(transcript, 'healthcare reforms', limit=14000)
    assert len(context) <= 14000
    assert 'Healthcare reforms' in context
    assert any(start > 7200 for start, end in intervals)
    assert any(start < 1800 for start, end in intervals)
    assert len(intervals) < 44


def test_default_mood_requests_are_fast_but_visual_evidence_is_preserved():
    for prompt in ('Find emotional moments', 'Find funny clips', 'More like these clips'):
        assert website.transcript_first_request(prompt)
    for prompt in ('Find battle footage', 'Find gestures on screen', 'Find a silent scene'):
        assert not website.transcript_first_request(prompt)


def test_source_backup_does_not_block_and_merges_owner_updates(monkeypatch, tmp_path):
    pending, release = threading.Event(), threading.Event()
    saved = {'user_id': 'a', 'project_id': 'b'}
    def write(path, value):
        saved.clear()
        saved.update(value)
    store = SimpleNamespace(read=lambda _: dict(saved), write=write, exists=lambda _: True)
    monkeypatch.setattr(source_backup.jobs, 'metadata_store', lambda: store)
    monkeypatch.setattr(source_backup.storage, 'uses_local_storage', lambda: False)
    def upload(*args):
        pending.set()
        assert release.wait(3)
        return {'source_s3_key': 'owned/source', 'source_s3_bucket': 'test'}
    monkeypatch.setattr(source_backup.storage, 'upload_source_media', upload)
    future = source_backup.schedule(tmp_path, 'job', dict(saved))
    try:
        assert pending.wait(2)
        assert not future.done()
        assert saved['source_backup_state'] == 'pending'
        saved['new_field'] = 'written while upload runs'
    finally:
        release.set()
    future.result(timeout=3)
    assert saved['source_backup_state'] == 'complete'
    assert saved['new_field'] == 'written while upload runs'


def test_backup_failure_keeps_local_source_and_records_failure(monkeypatch, tmp_path):
    source = tmp_path / 'source.video'
    source.write_bytes(b'private video')
    saved = {}
    def write(path, value):
        saved.clear(); saved.update(value)
    store = SimpleNamespace(read=lambda _: dict(saved), write=write, exists=lambda _: True)
    monkeypatch.setattr(source_backup.jobs, 'metadata_store', lambda: store)
    monkeypatch.setattr(source_backup.storage, 'uses_local_storage', lambda: False)
    monkeypatch.setattr(source_backup.storage, 'upload_source_media', lambda *a: (_ for _ in ()).throw(OSError('offline')))
    source_backup.schedule(tmp_path, 'job', {}).result(timeout=3)
    assert saved['source_backup_state'] == 'failed'
    assert source.read_bytes() == b'private video'


@pytest.mark.parametrize('direction,start,end', [('first', 100, 108), ('last', 122, 130)])
def test_explicit_followup_trims_use_cached_source_timestamps(monkeypatch, tmp_path, direction, start, end):
    cache = tmp_path / 'transcript.json'
    cache.write_text(json.dumps([{'start': 100, 'end': 130, 'text': 'Original context.'}]))
    monkeypatch.setattr(index, 'file_sha256', lambda _: 'key')
    monkeypatch.setattr(index, 'transcript_cache_paths', lambda *a: (cache, tmp_path/'unused'))
    result = followup_edit.select(Path('unused'), f'keep the {direction} 8 seconds',
                                  {'start': 100, 'end': 130}, 1, 200)
    assert result[0][0]['start'] == start
    assert result[0][0]['end'] == end
    assert result[2]['selection_mode'] == 'timestamp-edit'
    assert result[2]['usage']['estimated_cost_usd'] == 0


def test_similarity_multiple_outputs_and_missing_cache_never_become_local_edits(tmp_path, monkeypatch):
    parent = {'start': 10, 'end': 40}
    for prompt, count, ref in [('more like this', 1, parent), ('keep first 8 seconds', 2, parent),
                                ('keep first 8 seconds', 1, {'references': [parent, parent]}),
                                ('keep first 8 seconds but add a joke', 1, parent)]:
        assert followup_edit.select(Path('unused'), prompt, ref, count, 100) is None
    monkeypatch.setattr(index, 'file_sha256', lambda _: 'key')
    monkeypatch.setattr(index, 'transcript_cache_paths', lambda *a: (tmp_path/'missing', tmp_path/'unused'))
    assert followup_edit.select(Path('unused'), 'keep first 8 seconds', parent, 1, 100) is None
