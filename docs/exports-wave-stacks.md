# Exports: wave stacks

This correction uses the attached reference's overlapping-card structure, with
Cascade's existing green/teal palette. It changes Exports only; the editor,
Research Agent, Settings, B-roll, tracking and project history are not modified.
The implementation is the existing HTML/CSS/vanilla JavaScript frontend, with no
new framework or dependency.

All selected clips share one tile, including selections from different saves,
waves, or sessions. Only selected clips are included, in selection order; an
empty selection shows guidance to select clips in the editor. Unavailable
selections are omitted. The collapsed tile displays the selected clip count and
up to four overlapping thumbnails. Each selected clip immediately requests its
owner-checked `/editor/{job_id}/{clip_index}/thumbnail` endpoint, which extracts
a JPEG from the clip's local or cloud-backed media and caches it in server memory.
The browser fetches these images with authentication and creates fresh object URLs
on each page load. Posters load independently of tracking and edited rendering;
the finished edited frame replaces the initial source frame. Failed thumbnail
requests expose a retry action. Thumbnail cropping does not
change the encoded clip or the full-aspect playable preview.

Click the stack or Expand clips to reveal every clip in that review group. The
expanded wave uses the available desktop width and shows large cards side by
side in original clip order, rather than moving the active clip to the front. Collapse clips pauses
its videos and makes the hidden gallery inert for keyboard/screen-reader access.
Escape collapses a wave when focus is within it, restoring focus to its toggle.
Reduced-motion preferences disable transitions. A horizontal rail supports native trackpad/touch scrolling, mouse dragging outside
active player controls, per-wave arrows and CSS scroll snapping. Selecting a clip
in the sidebar scrolls it into view. The spread/fold transitions are isolated from
native snapping so an in-progress animation cannot change the chosen clip.
Collapsing restores the compact overlapping stack and retains the selected clip.

The Session → Wave → Clips sidebar opens the shared tile and highlights the
clip. Checkboxes remain synchronized with Download selected. Each clip retains its
individual download and retry action; Download clips downloads the whole selected review set. Controls are outside thumbnails. Existing selection semantics, edited video
renderer, ZIP endpoint, progress/error messages and account checks are retained.

`CascadeExports.initialize` accepts optional `stackOptions` with `backCards`
(default 3, maximum 4), `offset` (default 42px, reduced on small screens),
`rotation` (default 3 degrees) and `scale` (default .95 per layer).

## Browser verification

With `tests/editor_browser_server.py` and isolated Chrome on DevTools port 9333:

```sh
python3 -m tests.test_exports_horizontal_browser
python3 -m tests.test_exports_stacks_browser
python3 -m tests.test_exports_browser
```

The stack test checks actual rendered-poster loading and overlap geometry,
one shared tile and selected clip count, portrait front-card proportions, expansion/collapse, larger
playback, pause on collapse, sidebar synchronization, selection, a real three-clip
cross-save ZIP, keyboard dismissal, reduced motion, and no overflow at desktop, 1024,
768 and 390px. It compares the project record before/after to confirm history is
unchanged. Screenshots are in `/tmp/cascade-wave-stack-artifacts`.

The existing export workflow additionally verifies a real individually downloaded
edited MP4, a ZIP containing only checked clips, captions/effects/B-roll/audio,
preview retry and navigation. Identity and external providers are fixture
replacements; media, browser behavior, project reads and FFmpeg rendering are real.
No new claims about natural-conversation tracking or physical-device touch input
are made by this Exports-only correction.

The horizontal suite checks native horizontal wheel events, actual mouse drags,
Chrome-emulated touch swipes, per-card snap alignment including the last card,
full desktop-width expansion, stable clip order, selection and playback,
collapse/reopen, sidebar synchronization, arrows and 1024/768/390px layouts.
Screenshots are in `/tmp/cascade-horizontal-exports-artifacts`. Browser-emulated
touch is not verification on physical iPhone hardware.

The review surface now spans the available desktop width even while collapsed.
The collapsed pile has a bounded landscape stage; expanded cards use a compact
horizontal row (about three visible at a typical desktop width). Poster generation
keeps the source frame ratio, and both posters and video use `object-fit: contain`.

Timeline trackpad zoom uses Ctrl+wheel pinch events in Chromium and gesture events
in Safari, coalesced to animation frames. Zoom anchors the media time under the
cursor, updates the slider and percentage, and leaves ordinary horizontal wheel
input to native scrolling. Fit resets zoom and scroll to show the full timeline.
`tests/test_timeline_pinch_browser.py` checks Chromium input, cursor anchoring,
percentage/slider synchronization, horizontal scrolling, and Fit. Physical macOS
trackpad and Safari gesture hardware still require manual verification.

`node tests/test_exports_selection.cjs` checks cross-session selection grouping,
selected-only inclusion and order, empty/unavailable selections, and direct clip links.

`python3 -m tests.test_exports_thumbnails_browser` verifies real JPEGs from two
saves inside one tile while edited exports are held pending, thumbnail request
failure/retry, image visibility, and refresh. Its screenshot is saved to
`/tmp/cascade-exports-thumbnails.png`.
