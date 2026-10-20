All HTML view markup now lives in `web/index.html`; names such as `editor_C.html` below refer to preserved public routes. CSS and JavaScript files remain separate.

Frontend filenames below live under `web/`; backend service filenames live under `backend/`. Public URLs are unchanged. Run test commands from the repository root.

# Editor implementation

The editor uses existing Clerk authentication, project IDs, generation job IDs and zero-based clip indexes. Only `initializeEditor()` changed in shared `flow_C.js`. `app1.py` registers editor routes and allows editor assets. Canvas, clip-count selection, generation, scene selection and generation prompts are unchanged.

One generation job defines a session; derived caption-style jobs stay under their parent generation session. Actual available results determine the clip list, with no four-clip bound. Existing `?project=…&job=…&clip=…` links take precedence over saved selection. Missing explicit selections leave the sidebar available.

Drafts use existing atomic JSON writes under `video_jobs/projects/<user hash>/editor/<project>/<job>-<index>.json`. Last selection lives on the existing project record. There is no database migration; old drafts default the new per-segment `texts` map to empty. Browser recovery records are scoped to user, project and clip. Debounced saves flush before switching or internal navigation; failed saves keep recovery data and expose retry. Undo/redo is per clip for the current visit; saved edits and chat survive reloads, but undo stacks do not.

## Live preview and comparison

`editor_captions.js` draws actual timed caption text on a transparent canvas over the displayed video rectangle, excluding letterbox bars. Font, size, weight, color, outline, background, opacity, position and per-segment text edits appear locally. Styling a caption enables the additional caption layer. Caption-text typing saves after a short idle period. Manual gestures and validated AI responses share the same editing state and history.

Original mode shows the full generated clip with the additional caption layer hidden; Edited mode restores the retained trim and caption layer. Comparison is temporary view state and does not enter undo history or modify saved edits. Any editing operation returns to Edited mode. Main preview labels identify the mode, and known burned-in-caption limitations appear beside the video. The original media is never modified.

All trim boundaries use generated-media time. Source `start`/`end` metadata is never used as a playback offset. FFprobe supplies actual duration. Trim changes pause and position playback at the retained start, and playback stops at the retained end. Caption timing remains in generated-media coordinates during preview.

## Aspect ratio and playback

The Aspect Ratio tab offers Original, 9:16, 1:1, 4:5, 16:9 and 4:3 presets with ratio illustrations and selected-state indicators. `composition` is an additive per-clip state field containing the preset, Fit/Fill mode, normalized horizontal/vertical crop positions and Fit background color. Old drafts default to Original/Fit/centered without losing trim or caption edits. All controls participate in the same history and autosave; one crop-slider gesture is one history entry.

`editor_state.js` and `editor_backend.py` calculate matching output geometry. Presets use standard ratios with even integer dimensions derived from the source’s longest edge, rather than device-specific resolutions. Fit uniformly scales the video within the frame and pads unused pixels; Fill scales to cover and crops at the chosen position. Scaling and offsets are rounded for encoder/chroma alignment. Captions are drawn at output-frame dimensions after framing, so they stay inside the final composition. Export scales/pads/crops the source before compositing those same caption PNGs. Original comparison bypasses framing and additional captions without changing saved state.

The visible Play/Pause button sits beneath the main preview, shares playback with the timeline, shows time relative to the retained range, restarts after trim end, and exposes loading/playback errors. The main video and local caption layer compose live; normal framing changes do not render or request a new MP4.

## Timeline

`editor_timeline.js` provides a horizontal ruler, real sampled clip thumbnails, a synchronized playhead, a caption track, shaded discarded regions, draggable trim handles, numeric in/out controls, keyboard seeking/trimming, zoom and horizontal scrolling. Pointer coordinates are measured against the full content rectangle, including scroll offset and zoom scale. Pointer capture preserves a drag outside its initial target; each trim gesture creates one history entry. Playing follows the playhead when zoomed. Thumbnail extraction uses a separate local decoder, so it does not move the main preview. Decoding failures leave seeking/trimming usable and show a message.

## Export and AI

Browser-initiated edited downloads send the exact locally rendered transparent caption PNGs and their trimmed intervals. The backend validates PNG format, dimensions, payload size and intervals against the clip's real cues, then composites them over the trimmed video. This preserves browser caption layout and font rendering in export. H.264/yuv420p encoding is lossy, including chroma subsampling near caption edges. Clients without raster previews can still use the existing ASS export fallback, which requires FFmpeg with libass. An installed Homebrew `ffmpeg-full` is detected where available; `CASCADE_EDITOR_FFMPEG` can specify a compatible binary. Export status is indeterminate while encoding; there are no simulated percentages. Edited downloads render on demand; the existing Exports page continues downloading originals.

Chat uses the existing server-side OpenAI key/model configuration, with optional `OPENAI_EDITOR_MODEL` override. The Responses API uses strict structured output, followed by Pydantic and media-boundary validation. Supported actions: remove initial trim seconds, keep initial trim seconds, reset trim, captions on/off, text color, bold, top/middle/bottom position and text for an identified caption segment. Multiple actions in one response form one undo transaction. No generated commands are executed. Provider calls are mocked in tests. Request format follows [official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

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
