"""Tests for Deepgram transcription + segmenting. No network, models, or real audio."""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.cascade_stt import TRANSCRIPT_TAG, transcribe  # noqa: E402
from backend.agent.index import transcript_cache_paths  # noqa: E402


def w(word, start, end, speaker=0, punctuated=None):
    d = {"word": word, "start": start, "end": end, "speaker": speaker}
    if punctuated is not None:
        d["punctuated_word"] = punctuated
    return d


# ---------- words_to_segments ----------

def test_sentence_break_after_enough_words():
    words = [
        w("so", 0.0, 0.3, punctuated="So"),
        w("this", 0.3, 0.6),
        w("is", 0.6, 0.8),
        w("it", 0.8, 1.0, punctuated="it."),
        w("next", 1.1, 1.4, punctuated="Next"),
        w("one", 1.4, 1.7, punctuated="one."),
    ]
    segs = transcribe.words_to_segments(words)
    assert [s["text"] for s in segs] == ["So this is it.", "Next one."]
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 1.0
    assert segs[0]["speaker"] == 0


def test_short_fragment_is_not_its_own_segment():
    words = [
        w("yeah", 0.0, 0.3, punctuated="Yeah."),   # only 1 word: no break yet
        w("and", 0.4, 0.6),
        w("then", 0.6, 0.9, punctuated="then."),
    ]
    segs = transcribe.words_to_segments(words)
    assert [s["text"] for s in segs] == ["Yeah. and then."]


def test_speaker_change_always_breaks():
    words = [w("hello", 0.0, 0.4, speaker=0), w("hi", 0.5, 0.8, speaker=1)]
    segs = transcribe.words_to_segments(words)
    assert [(s["speaker"], s["text"]) for s in segs] == [(0, "hello"), (1, "hi")]


def test_gap_breaks():
    words = [w("a", 0.0, 0.3), w("b", 0.3, 0.6), w("c", 5.0, 5.3), w("d", 5.3, 5.6)]
    segs = transcribe.words_to_segments(words)
    assert [s["text"] for s in segs] == ["a b", "c d"]


def test_long_run_is_capped():
    words = [w(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(200)]  # 100s, no punctuation
    segs = transcribe.words_to_segments(words)
    assert len(segs) >= 4
    assert all(s["end"] - s["start"] <= transcribe.MAX_SEGMENT_SECONDS for s in segs)
    # nothing lost, nothing duplicated
    assert sum(len(s["text"].split()) for s in segs) == 200


def test_missing_speaker_and_empty_input():
    segs = transcribe.words_to_segments([{"word": "hi", "start": 0.0, "end": 0.2}])
    assert segs == [{"start": 0.0, "end": 0.2, "text": "hi", "speaker": None}]
    assert transcribe.words_to_segments([]) == []


def test_segments_from_deepgram_and_malformed():
    response = {"results": {"channels": [{"alternatives": [{"words": [w("hi", 0.0, 0.2)]}]}]}}
    assert transcribe.segments_from_deepgram(response)[0]["text"] == "hi"
    with pytest.raises(transcribe.TranscriptionError):
        transcribe.segments_from_deepgram({"results": {}})


# ---------- deepgram_request (httpx MockTransport) ----------

def audio_file(tmp_path):
    p = tmp_path / "audio.mp3"
    p.write_bytes(b"fake-audio-bytes")
    return p


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_request_shape(tmp_path):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["params"] = dict(request.url.params)
        seen["body"] = request.content
        seen["ctype"] = request.headers["content-type"]
        return httpx.Response(200, json={"ok": True})

    out = transcribe.deepgram_request(audio_file(tmp_path), "KEY123", client=mock_client(handler))
    assert out == {"ok": True}
    assert seen["auth"] == "Token KEY123"
    assert seen["params"]["model"] == "nova-3"
    assert seen["params"]["diarize_model"] == "latest"
    assert "diarize" not in seen["params"]  # sending both is rejected by Deepgram
    assert seen["body"] == b"fake-audio-bytes"
    assert seen["ctype"] == "audio/mpeg"


def test_400_retries_without_diarization(tmp_path):
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        if "diarize_model" in request.url.params:
            return httpx.Response(400, json={"err": "bad param"})
        return httpx.Response(200, json={"ok": True})

    out = transcribe.deepgram_request(audio_file(tmp_path), "K", client=mock_client(handler))
    assert out == {"ok": True}
    assert len(calls) == 2 and "diarize_model" not in calls[1]


@pytest.mark.parametrize(
    "status,needle",
    [(401, "API key"), (402, "credit"), (429, "rate limiting"), (504, "timed out"), (500, "HTTP 500")],
)
def test_http_errors_become_clear_messages(tmp_path, status, needle):
    client = mock_client(lambda request: httpx.Response(status, json={}))
    with pytest.raises(transcribe.TranscriptionError) as exc:
        transcribe.deepgram_request(audio_file(tmp_path), "SECRETKEY", client=client)
    assert needle in str(exc.value)
    assert "SECRETKEY" not in str(exc.value)


def test_timeout_and_bad_json(tmp_path):
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(transcribe.TranscriptionError, match="timed out"):
        transcribe.deepgram_request(audio_file(tmp_path), "K", client=mock_client(boom))

    client = mock_client(lambda request: httpx.Response(200, content=b"not json"))
    with pytest.raises(transcribe.TranscriptionError, match="unreadable"):
        transcribe.deepgram_request(audio_file(tmp_path), "K", client=client)


# ---------- transcribe_video orchestration ----------

def test_no_audio_track_skips_deepgram(monkeypatch, tmp_path):
    monkeypatch.setattr(transcribe, "has_audio_stream", lambda p: False)
    monkeypatch.setattr(transcribe, "deepgram_request", lambda *a, **k: pytest.fail("called"))
    steps = []
    assert transcribe.transcribe_media(Path("x.mp4"), tmp_path, progress=steps.append) == []
    assert any("No audio track" in s for s in steps)


def test_missing_key_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(transcribe, "has_audio_stream", lambda p: True)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    with pytest.raises(transcribe.TranscriptionError, match="DEEPGRAM_API_KEY is not set"):
        transcribe.transcribe_media(Path("x.mp4"), tmp_path)


def _fake_pipeline(monkeypatch, seen):
    """Stub the ffmpeg + HTTP steps; record what each was given."""
    monkeypatch.setattr(transcribe, "has_audio_stream", lambda p: True)

    def fake_extract(media, dest):
        seen["media"], seen["dest"] = Path(media), Path(dest)
        out = Path(dest) / "audio.mp3"
        out.write_bytes(b"mp3")
        seen["audio"] = out
        return out

    monkeypatch.setattr(transcribe, "extract_audio", fake_extract)
    monkeypatch.setattr(
        transcribe,
        "deepgram_request",
        lambda path, key, client=None, info=None: {
            "metadata": {"duration": 3600.0},
            "results": {"channels": [{"alternatives": [{"words": [w("hi", 0.0, 0.2)]}]}]},
        },
    )
    monkeypatch.setenv("DEEPGRAM_API_KEY", "k")


def test_happy_path_cost_and_no_leftover_mp3_in_the_callers_folder(monkeypatch, tmp_path):
    seen, info = {}, {}
    _fake_pipeline(monkeypatch, seen)
    segs = transcribe.transcribe_media(Path("x.mp4"), tmp_path, info=info)
    assert segs[0]["text"] == "hi" and segs[0]["speaker"] == 0
    assert seen["dest"] == tmp_path
    assert not list(tmp_path.glob("*.mp3"))  # the temporary MP3 is cleaned up
    assert info["cost_usd"] == pytest.approx(60 * 0.0043)  # one hour of audio


def test_without_a_work_dir_it_uses_and_removes_its_own_temp_folder(monkeypatch):
    seen = {}
    _fake_pipeline(monkeypatch, seen)
    assert transcribe.transcribe_media(Path("x.mp4"))[0]["text"] == "hi"
    assert not seen["dest"].exists()


def test_any_media_type_is_accepted_wav_is_converted_to_mp3_first(monkeypatch, tmp_path):
    seen = {}
    _fake_pipeline(monkeypatch, seen)
    transcribe.transcribe_media(Path("selected_1.wav"), tmp_path)
    assert seen["media"].suffix == ".wav"  # extract_audio re-encodes whatever it is given
    assert seen["audio"].suffix == ".mp3"


def test_diarization_drop_is_reported_as_a_step(monkeypatch, tmp_path):
    monkeypatch.setattr(transcribe, "has_audio_stream", lambda p: True)

    def fake_extract(media, dest):
        out = Path(dest) / "a.mp3"
        out.write_bytes(b"x")
        return out

    monkeypatch.setattr(transcribe, "extract_audio", fake_extract)

    def fake_request(path, key, client=None, info=None):
        info["diarization_dropped"] = True
        return {"results": {"channels": [{"alternatives": [{"words": [w("hi", 0.0, 0.2)]}]}]}}

    monkeypatch.setattr(transcribe, "deepgram_request", fake_request)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "k")
    steps = []
    transcribe.transcribe_media(Path("x.mp4"), tmp_path, progress=steps.append)
    assert any("without speaker labels" in s for s in steps)


def test_diarization_drop_is_reported(tmp_path):
    def handler(request):
        if "diarize_model" in request.url.params:
            return httpx.Response(400, json={"err": "bad param"})
        return httpx.Response(200, json={"ok": True})

    info = {}
    transcribe.deepgram_request(audio_file(tmp_path), "K", client=mock_client(handler), info=info)
    assert info["diarization_dropped"] is True

    ok_info = {}
    transcribe.deepgram_request(
        audio_file(tmp_path), "K", client=mock_client(lambda r: httpx.Response(200, json={})), info=ok_info
    )
    assert "diarization_dropped" not in ok_info


def test_there_is_no_local_whisper_path_left():
    assert not hasattr(transcribe, "_transcribe_whisper") and not hasattr(transcribe, "provider")
    source = Path(transcribe.__file__).read_text(encoding="utf-8").lower()
    assert "import whisper" not in source and "faster_whisper" not in source


def test_transcript_cache_key_carries_the_model(tmp_path):
    assert "nova-3" in TRANSCRIPT_TAG and TRANSCRIPT_TAG.startswith("deepgram")
    assert transcript_cache_paths("abc", TRANSCRIPT_TAG) != transcript_cache_paths("abc", "deepgram-other")
