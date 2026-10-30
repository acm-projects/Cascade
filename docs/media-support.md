# Audio and video sources

Studio accepts MP4, MOV, WebM, MKV, MP3, WAV, M4A and FLAC. Existing AVI/M4V
uploads remain supported. Each session has one independent source; create a new
session to upload a different recording. The multipart field remains `video` for
backward compatibility, even for audio. No URLs or database tables were replaced.

## Processing and storage

`backend/media.py` validates names and probes actual streams with ffprobe. Attached
album art does not turn an audio recording into a video. Empty and unsupported
uploads fail immediately. Corrupted media fails the queued job's inspection step,
before paid transcription or ranking; the UI receives an actionable error.

The existing `source.video` path remains the internal source contract. Compatible
MP4/H.264/AAC and MP3 inputs do not need conversion. FFmpeg remuxes compatible
MOV/MKV streams into MP4, transcodes other video into H.264/AAC when necessary,
and normalizes other audio into MP3. The original is retained locally whenever
normalization changes the source. Normalization has a ten-minute command timeout.

The configured storage adapter is reused: media stays local in local mode; S3
mode stores normalized sources, originals when converted, MP4/MP3 clips and VTT
captions under owner-scoped keys. Original sources can be retrieved from S3 when
the local normalized copy is missing. Source and clip MIME types distinguish
`audio/mpeg` from `video/mp4`. Media kind/stream information is stored in the
existing owner/result JSON records, so Neon uses the current metadata schema.

## AI and editing

Audio follows the same Deepgram → transcript embeddings → summaries → agent
candidate/ranking path. It does not sample images or load CLIP for indexing.
Visual search requests fall back to transcript search; inspection returns spoken
context rather than invented frames. Audio highlight judgments use spoken content;
this change does not introduce acoustic emotion/music classification.

The React player uses an audio element with the existing playback and timeline
controls. Trims and transcript edits persist as before. Subject tracking, reframing,
video effects, B-roll, thumbnails and video publishing are unavailable for audio;
the backend enforces those restrictions even if an older client sends a request.

Audio clips/export downloads are MP3; video remains MP4. ZIP exports may contain
both, plus trimmed VTT sidecars for audio when captions are enabled. Audio preview
can show captions, but an MP3 cannot contain burned-in visual captions. Resolution
caps apply only to video. Other original audio formats are accepted as inputs,
not selectable output encodings. MP3 conversion is lossy; retained originals are
available for future export options.

## Files and validation

- Upload/normalization/storage: `app1.py`, `backend/media.py`,
  `backend/core/storage.py`, `backend/integration.py`.
- Indexing and ranking context: `backend/agent/index.py`, `tools.py`, `agent.py`.
- Playback, edit validation and export: the existing `backend/editor/` package,
  including the small new `audio.py` renderer; `backend/main.py` guards video posting.
- UI: Studio source picker/preview, editor player/framing guard, export download
  helpers/settings and shared media-format utilities under `frontend/src/`.
  The legacy Studio/editor/export assets remain supported too.
- Automated coverage: `tests/test_audio_media.py` and `frontend/src/utils/media.test.js`.
  The legacy local-storage fixture now mocks the shared media probe instead of its
  former video-only inspection function.

Run `python -m unittest discover -s tests -p 'test_*.py'` using local test metadata,
plus `npm test`, `npm run build`, and `npm run lint` from `frontend/`. The optional
`tests/audio_browser_server.py` serves a temporary, offline React audio fixture on
127.0.0.1:8768. Its identity/AI mocks are process-local and never enable dev auth
in the normal app.

Tests use real generated MP3/MP4 media, conversions for all supported containers,
real trim/ZIP encoding, ownership checks and mocked S3. Paid transcription/LLM
responses are mocked; live AWS/Neon connectivity is not exercised by the offline
suite. The user's existing podcast was read-only probed successfully and remains
untracked and untouched.
