Current UI behavior and verification are described in [Editor and Exports delivery update](editor-delivery.md). The implementation history below includes earlier controls that have since been replaced.

All HTML view markup now lives in `web/index.html`; names such as `editor_C.html` below refer to preserved public routes. CSS and JavaScript files remain separate.

Frontend filenames below live under `web/`; backend service filenames live under `backend/`. Public URLs are unchanged. Run test commands from the repository root.

# Editor implementation

The editor uses existing Clerk authentication, project IDs, generation job IDs and zero-based clip indexes. Shared `flow_C.js` initializes the authenticated editor, canvas, and Exports controllers. `app1.py` registers editor routes and allows editor assets. Existing generation, scene selection and clip-count behavior remains connected.

The navigation hierarchy is source video → Session → Waves → Clips. A full-video prompt starts a Session; follow-up jobs sharing its parent ancestry are Waves in that Session. Each generation job is one Wave; derived caption-style jobs stay in their parent Wave. `backend/editor_navigation.py` derives stable labels from existing ordered jobs and parent IDs without migrating or rewriting history. Actual available results determine the clip list, with no four-clip bound. Existing `?project=…&job=…&clip=…` links take precedence over saved selection. Missing explicit selections leave the sidebar available.

Drafts use existing atomic JSON writes under `video_jobs/projects/<user hash>/editor/<project>/<job>-<index>.json`. Last selection lives on the existing project record. There is no database migration; old drafts default the new per-segment `texts` map to empty. Browser recovery records are scoped to user, project and clip. Debounced saves flush before switching or internal navigation; failed saves keep recovery data and expose retry. Undo/redo is per clip for the current visit; saved edits and chat survive reloads, but undo stacks do not.

## Live preview and comparison

`editor_captions.js` draws actual timed caption text on a transparent canvas over the displayed video rectangle, excluding letterbox bars. Font, size, weight, color, outline, background, opacity, position and per-segment text edits appear locally. Styling a caption enables the additional caption layer. Caption-text typing saves after a short idle period. Manual gestures and validated AI responses share the same editing state and history.

Original mode shows the full generated clip with the additional caption layer hidden; Edited mode restores the retained trim and caption layer. Comparison is temporary view state and does not enter undo history or modify saved edits. Any editing operation returns to Edited mode. Main preview labels identify the mode, and known burned-in-caption limitations appear beside the video. The original media is never modified.

All trim boundaries use generated-media time. Source `start`/`end` metadata is never used as a playback offset. FFprobe supplies actual duration. Trim changes pause and position playback at the retained start, and playback stops at the retained end. Caption timing remains in generated-media coordinates during preview.

## Aspect ratio and playback

The Aspect Ratio tab offers Original, 9:16, 1:1, 4:5, 16:9 and 4:3 presets with ratio illustrations and selected-state indicators. `composition` is an additive per-clip state field containing the preset, Fit/Fill mode, normalized horizontal/vertical crop positions and Fit background color. Old drafts default to Original/Fit/centered without losing trim or caption edits. All controls participate in the same history and autosave; one crop-slider gesture is one history entry.

`editor_state.js` and `backend/editor/composition.py` calculate matching output geometry. Presets use standard ratios with even integer dimensions derived from the source’s longest edge, rather than device-specific resolutions. Fit uniformly scales the video within the frame and pads unused pixels; Fill scales to cover and crops at the chosen position. Scaling and offsets are rounded for encoder/chroma alignment. Captions are drawn at output-frame dimensions after framing, so they stay inside the final composition. Export scales/pads/crops the source before compositing those same caption PNGs. Original comparison bypasses framing and additional captions without changing saved state.

The visible Play/Pause button sits beneath the main preview, shares playback with the timeline, shows time relative to the retained range, restarts after trim end, and exposes loading/playback errors. The main video and local caption layer compose live; normal framing changes do not render or request a new MP4.

## Timeline

`editor_timeline.js` provides a horizontal ruler, real sampled clip thumbnails, a synchronized playhead, a caption track, shaded discarded regions, draggable trim handles, numeric in/out controls, keyboard seeking/trimming, zoom and horizontal scrolling. Pointer coordinates are measured against the full content rectangle, including scroll offset and zoom scale. Pointer capture preserves a drag outside its initial target; each trim gesture creates one history entry. Playing follows the playhead when zoomed. Thumbnail extraction uses a separate local decoder, so it does not move the main preview. Decoding failures leave seeking/trimming usable and show a message.

## Export and AI

Browser-initiated edited downloads send the exact locally rendered transparent caption PNGs and their trimmed intervals. The backend validates PNG format, dimensions, payload size and intervals against the clip's real cues, then composites them over the trimmed video. This preserves browser caption layout and font rendering in export. H.264/yuv420p encoding is lossy, including chroma subsampling near caption edges. Clients without raster previews can still use the existing ASS export fallback, which requires FFmpeg with libass. An installed Homebrew `ffmpeg-full` is detected where available; `CASCADE_EDITOR_FFMPEG` can specify a compatible binary. Export status is indeterminate while encoding; there are no simulated percentages. Edited downloads render on demand; the existing Exports page continues downloading originals.

Chat uses `backend/editor/ai.py` and the shared `cascade_llm` structured helper. `LLM_PROVIDER` selects Anthropic or OpenAI; optional `CASCADE_EDITOR_PROVIDER` overrides only editor chat, without mutating process-wide provider settings. Pydantic and media-boundary validation follow the structured response. Supported actions: remove initial trim seconds, keep initial trim seconds, reset trim, captions on/off, text color, bold, top/middle/bottom position and text for an identified caption segment. Multiple actions in one response form one undo transaction. No generated commands are executed. Provider calls are mocked in tests. Request format follows [official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

Burned-in-caption detection relies on existing clip metadata/job kind. Those pixels remain in both comparison modes and exports; additional captions cannot erase them. Pexels B-roll now replaces main video pixels during inserted segments, so original burned-in captions can be covered by stock footage. The additional caption layer remains above B-roll. See [B-roll setup and workflow](broll.md).

## Validation

```sh
python3 -m unittest discover -s tests -p 'test_editor.py' -v
node tests/test_editor_state.cjs
node tests/test_editor_flow.cjs
# Full suite also needs subtitle support for existing generation tests:
env PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH" python3 -m unittest discover -s tests -p 'test_*.py' -q
```

Real-browser tests use isolated temporary media/storage and a localhost-only fixture server. Identity/provider mocks exist only inside that process, never in production routes. They exercise actual Chrome media playback, pointer gestures, rasterized captions, screenshot changes, comparison, zoom/scroll coordinates, undo/redo, reload and encoded export frames. The runner uses the optional Python `websockets` package and an isolated Chrome DevTools port:

```sh
# Start Chrome with a separate temporary profile:
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-first-run --remote-debugging-port=9333 --remote-allow-origins=http://localhost:9333 --user-data-dir=/tmp/cascade-editor-chrome about:blank
# In separate terminals:
python3 tests/editor_browser_server.py
python3 tests/test_editor_browser.py
```

Screenshots and export comparisons are written to `/tmp/cascade-editor-browser-artifacts`. These tests do not exercise live Clerk, cloud storage or paid AI. They use one landscape fixture and the laptop viewport sizes in the runner; they are not a claim of cross-browser/device coverage.

Additional real-browser framing validation (with the fixture server/Chrome setup above):

```sh
python3 tests/test_editor_aspect_browser.py
```

This checks all six preset compositions, Fit background, Fill crop repositioning, real pointer crop gestures, the main Play/Pause control and timeline timing, caption bounds, comparison, independent clip state and reload, plus missing-media error visibility and recovery. It downloads actual Fit and Fill MP4s through the export button, probes dimensions/duration, and compares encoded frames with the corresponding live composition. Artifacts are in `/tmp/cascade-aspect-artifacts`. The source fixture is landscape; other browsers and portrait source media are not covered by that browser run.


## Effects, simple captions, and selected exports

Editor tabs are Chat · Captions · Aspect ratio · B-roll · Effects. The visible Captions panel offers enable/disable, Classic/Bold/Yellow styles, and color. Detailed style/text settings remain in the state and chat protocol (`caption_settings` accepts a complete validated style; `caption_text` targets a timed segment). Hidden compatibility controls retain existing bindings; they are not presented as manual settings. The numeric In/Out section and redundant duration/frame status are hidden. Timeline trim handles, keyboard trimming, reset, captions, B-roll and playback remain available.

`effects` defaults older drafts to brightness/contrast/saturation 1 and grayscale false. Controls join per-clip history and autosave. CSS filters affect both original footage and B-roll in Edited preview, while Original comparison bypasses effects. FFmpeg applies RGB brightness/contrast and a saturation matrix after B-roll and before caption compositing. Values are bounded and finite on both client and server. Encoder color conversions can cause small pixel differences from browser preview; the caption raster remains shared.

The canvas retains its original clip cards without export checkboxes or an export-selection toolbar. Export selection now lives in the editor's far-left nested Session → Wave → Clips sidebar. Native collapsible groups expand independently; the active clip's parents open automatically. Separate checkboxes select clips, whole waves or sessions, with native indeterminate states for partial selection. Selection is account/project scoped under `cascade-export-selection:v1:<user>:<project>` and survives clip switching and refresh. **Open exports (N)** opens exactly the selection. Exports has a matching sidebar containing only selected clips; selecting a clip there and swiping the carousel keep the same active clip highlighted. Unavailable selected clips are omitted with a warning. With no selection, Exports directs the user back to the editor.

Repeated generation requests with the same source and normalized prompt share a Session and form distinct Waves. Follow-up ancestry remains authoritative; explicit session/wave IDs are respected. Caption-style variants stay under their generation Wave. Distinct real generation runs are retained, never silently collapsed or deleted. Legacy `history_id` is a generation request ID, not a Session identity. All clips retain their original job/index keys and drafts.

`web/exports_C.js` loads each draft, preferring a newer local recovery snapshot when present, normalizes it, rasterizes its captions, and calls the existing authenticated editor `/export` endpoint. Thus each playable preview and active Download uses an actual edited MP4 with trim, framing, effects, captions, original audio, and B-roll. No original-media fallback is passed off as an edited preview. The front rounded video card has playback controls; adjacent cards partially show behind it. Arrows, horizontal swipe, and left/right keys change the active card and pause its predecessor. Aspect ratios are preserved with contain framing.

Previews render on demand, with immediate neighbours prepared in the background. Each card deduplicates render requests and retains its rendered Blob for this page visit. Export All submits the same state/raster payloads to owner-checked `POST /api/projects/{pid}/editor/export-selected`, which renders entries sequentially into a ZIP (up to 100 clips per ZIP). Temporary files are cleaned up. Errors are displayed, retry is available, and action locks prevent repeat submissions while processing. Export is a snapshot of edits loaded for that page visit; return from the editor or refresh Exports to load later edits. No new paid AI calls are made by export.

YouTube trend research is not an upload integration. The YouTube action honestly explains that account connection and upload backend work are required, and links to YouTube Studio for manually uploading a downloaded file.

Additional verification: run `python3 -m tests.test_exports_browser` with `tests/editor_browser_server.py` and isolated headless Chrome on DevTools port 9333. This covers simplified controls, effects/history/restore, editor selection across groups and refresh, exactly selected stacked video previews, pause on navigation, arrows/keyboard/swipe, real MP4 and ZIP downloads, output framing/duration/audio, grayscale B-roll below colored captions, duplicate ZIP prevention, and honest YouTube setup. All fixture data lives in temporary directories and provider calls are mocked.


Follow Speaker now integrates with Fill to Frame, saved drafts, Chat, comparison, and every edited export. See [Auto Reframe processing, setup, limitations and verification](auto-reframe.md).


## Backend package (CAS-43 / CAS-44)

`backend/main.py` includes `backend/editor/routes.py` as an APIRouter. The editor
models, action validation, caption rendering, composition, media, drafts, tracking,
and exports each live in their own module under `backend/editor/`. The old
`backend/editor_backend.py` is a two-line compatibility re-export, not a second
implementation. Request-time service imports keep app startup free of circular
imports and retain isolated job-directory overrides in tests.

`tests/editor_routes_before.json` records the route contract before extraction.
`tests/test_editor_routes.py` compares every path/method pair and enforces the
300-line module budget. Provider tests mock both adapters; they exercise caption
changes with either provider's key, override isolation, invalid proposals, missing
credentials, and disabled OpenAI response storage. Automated tests do not make
paid provider calls.

On Windows, tracking locks use `msvcrt`, and publishing worker liveness is queried
without `os.kill(pid, 0)` (which can send a Windows console signal). OpenCV and
`tzdata` must be installed from the existing runtime requirements for the related
tracking and timezone tests.
