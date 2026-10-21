# Exports: wave stacks

This correction uses the attached reference's overlapping-card structure, with
Cascade's existing green/teal palette. It changes Exports only; the editor,
Research Agent, Settings, B-roll, tracking and project history are not modified.
The implementation is the existing HTML/CSS/vanilla JavaScript frontend, with no
new framework or dependency.

Each wave in the review set is grouped by its actual session ID and wave ID
(falling back to its existing job ID). A collapsed wave displays its dynamic clip
count and a portrait 3:4 front thumbnail, with up to three smaller, dimmed cards
behind it. Alternating offsets, rotations and soft shadows create the fan.
Single-clip waves show one card. The thumbnails come from a frame of each actual
edited export, not stock images or CSS placeholders. Thumbnail cropping does not
change the encoded clip or the full-aspect playable preview.

Click the stack or Expand wave to reveal every clip in that review group. The
expanded wave uses the available desktop width and shows large cards side by
side in original clip order, rather than moving the active clip to the front. Collapse wave pauses
its videos and makes the hidden gallery inert for keyboard/screen-reader access.
Escape collapses a wave when focus is within it, restoring focus to its toggle.
Reduced-motion preferences disable transitions. A horizontal rail supports native trackpad/touch scrolling, mouse dragging outside
active player controls, per-wave arrows and CSS scroll snapping. Selecting a clip
in the sidebar scrolls it into view. The spread/fold transitions are isolated from
native snapping so an in-progress animation cannot change the chosen clip.
Collapsing restores the compact overlapping stack and retains the selected clip.

The Session → Wave → Clips sidebar opens the appropriate wave and highlights the
clip. Checkboxes remain synchronized with Download selected. Each clip retains its
individual download and retry action; Download wave downloads the whole review
wave. Controls are outside thumbnails. Existing selection semantics, edited video
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
per-wave counts, portrait front-card proportions, expansion/collapse, larger
playback, pause on collapse, sidebar synchronization, selection, a real three-clip
wave ZIP, keyboard dismissal, reduced motion, and no overflow at desktop, 1024,
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
