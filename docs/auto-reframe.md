# Auto Reframe / Follow Speaker

Fill to Frame now supports saved, per-clip Auto Reframe. Under Aspect Ratio, choose Fill to Frame, select a target ratio, tracking starts automatically when cropping is necessary. Focus options are Auto, speaker, both people, the person initially on the left, and the person initially on the right. Chat supports the same choices through validated `reframe_focus` actions. Analysis must finish successfully before a new tracking edit is committed. Cancel stops waiting in the editor; already queued local processing can finish and be reused later.

## Local processing and setup

Install the application's requirements and download the public, checksum-verified weights:

```sh
python3 -m pip install -r requirements.txt
python3 scripts/setup_reframe.py
uvicorn app1:app --reload --host 127.0.0.1 --port 8000
```

`requirements-reframe.txt` is an equivalent setup entry point. Added dependencies are OpenCV headless and python_speech_features; Torch/Numpy/Scipy are already used by the app's existing local models. Weights default to `~/.cache/cascade/reframe`; override with `CASCADE_REFRAME_MODELS`. No `.env` changes or paid API calls are required for analysis. Missing dependencies, missing weights, no detected faces, interrupted jobs, and processing errors are surfaced explicitly. Analysis is serialized on a bounded local queue and currently supports generated clips up to five minutes.

Body, animal and object tracking plus manual selection are described in [subject-tracking.md](subject-tracking.md). The face detector is [OpenCV YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet). Active speaker inference uses the [Light-ASD](https://github.com/Junhua-Liao/Light-ASD) audio-visual network and TalkSet-finetuned weights. The vendored inference architecture includes its MIT license and revision in `backend/vendor/light_asd`. Downloads use fixed upstream revisions and SHA256 hashes; downloaded Python code is never executed. Model weights and test footage are not repository artifacts.

`backend/reframe.py` decodes a temporary analysis copy at 25 fps, detects faces, associates their boxes across frames, extracts stable face crops and synchronous 16 kHz audio MFCCs, and runs the real CPU audio-visual network. Face presence alone does not identify a speaker. The production media and its audio are never resampled or overwritten by analysis.

## Planning, preview, export and persistence

A sustained high-confidence speaker match (at least 0.65 seconds, with a 1.4-second minimum switch interval) can change the target. Mouth/audio evidence comes from the learned network, with an audible-energy gate. Overlap or ambiguity includes people together only when the fixed Fill crop can fit them with headroom; otherwise it holds. A sole visible person can be followed visually, but missing audio explicitly reports that speaker identity is unconfirmed. Left/right focus anchors an initially detected track, rather than switching to whichever face happens to occupy that side later.

The planner pads face/head boxes, clamps every coordinate to the source boundaries, and limits pan velocity and acceleration. It does not zoom. Wide-separated faces may not fit a vertical Fill crop; use Fit to preserve the whole scene. Faces that leave the scene, are obscured, are very small/profile views, or are animated characters can be missed. This is not biometric re-identification, transcript diarization, or a guarantee of perfect speaker attribution. Low-confidence segments hold a stable frame rather than inventing speech evidence.

Private analysis files live alongside owner/project/clip-scoped editor drafts and contain immutable analysis IDs. Drafts save `reframe.enabled`, `focus`, `selection`, and `analysis_id`; they do not accept arbitrary client-provided trajectories or filesystem paths. Undo/redo can reuse prior analysis. On refresh, the editor restores the setting and loads a plan for the current aspect ratio. Missing analysis keeps export disabled until tracking is retried or disabled; a static crop is not labelled as successful tracking.

The browser interpolates the server's actual crop trajectory against the main video's generated-clip time. Original comparison bypasses it. Export obtains the same owner-checked analysis and trajectory, shifts the time origin by the trim start, and uses FFmpeg dynamic crop expressions before effects/captions. B-roll retains its own framing, and captions are composited above it as before. Original audio/timing remain connected. Selected export previews, individual downloads, and ZIP exports all use this renderer.

## Verification

Offline regression tests include planning with overlap/uncertainty, hysteresis, bounded movement, left/both focus, ownership and clip isolation, saved state, Chat actions, and a real FFmpeg moving-crop export with audio:

```sh
python3 -m unittest tests.test_reframe tests.test_editor_navigation -q
```

Opt-in real-model verification uses the public TalkNet `demo/001.avi` kept outside the repository:

```sh
python3 tests/manual/verify_reframe_media.py --source /tmp/cascade-conversation.avi
CASCADE_REFRAME_FIXTURES=/tmp/cascade-tracking-fixtures python3 tests/editor_browser_server.py
# With isolated Chrome on DevTools port 9333:
python3 -m tests.test_reframe_browser
python3 -m tests.test_exports_browser
```

The controlled turn-taking fixture uses real speaking-face video opposite a frozen listener, then swaps their roles. The moving-person fixture translates the actual speaking video across a canvas. No camera path or speaker labels are supplied to inference. These are constructed test stimuli, not a natural-conversation accuracy benchmark. Real inference selected opposite sides for the two turns and tracked the moving subject with bounded smooth motion. The uploaded sources inspected for this task contain animation or a human/animated-character interaction and were not treated as a valid two-human-speaker benchmark.
