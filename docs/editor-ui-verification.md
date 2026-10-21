# Editor UI and tracking verification

Reviewed October 21, 2026. The requested screenshot was not attached, so this
review used the rendered editor in isolated Chrome. No project records were
changed, and no commits or pushes were made.

## UI changes

- Widened the clip sidebar so Session, Wave, and Clip labels stay on one line.
- Removed the inert Source video tile. Added guidance distinguishing opening a
  clip from checking it for export.
- Strengthened the selected clip border, background, and text weight, retaining
  the existing accessible selected-state attributes.
- Separated Canvas navigation, project/save status, undo/redo, and delivery
  actions. On phones, export navigation occupies its own full-width row.
- Aligned editing-tool tabs and fields, hid the empty chat placeholder, and
  moved trend research into a disclosure that starts collapsed.
- Kept the Cascade palette, preview, timeline, editing functions, and each
  project's existing session/wave history.

## Tests performed

`python3 -m tests.test_editor_layout_browser` passed at 1440, 1024, 768, and
390 pixels. It checks horizontal overflow, readable hierarchy labels, selected
clip state, editing tabs, research disclosure, and desktop column placement.
Screenshots are in `/tmp/cascade-editor-layout-artifacts`.

`python3 -m tests.test_reframe_browser` ran the real YuNet/Light-ASD models,
Chrome preview, and FFmpeg exporter. It checked moving-subject framing,
speaker-side changes, collapsible navigation, chat action application,
undo/redo, reload, different saved focus settings and analysis IDs for two
clips, and a 9:16 export retaining duration and audio. Decoded export frames at
3 and 10 seconds were compared with browser-composited preview screenshots;
mean absolute RGB differences were 11.62 and 13.75 out of 255 at preview size.
These allow raster scaling and encoding differences; they are not claims of
pixel-identical rendering. Images and MP4 are in
`/tmp/cascade-reframe-browser-artifacts`.

`python3 -m tests.test_exports_browser` passed the selection/refresh, carousel,
MP4, ZIP, captions, B-roll, effects, trim, and audio workflow. The state and
editor-flow JavaScript suites and 25 Python editor/navigation/reframe/frontend
tests also passed.

Authentication and chat-provider replies are fixture replacements in these
browser tests. Face/speaker inference, video decoding, preview rendering,
export rendering, and persistence are real. Live AI interpretation was not
tested.

## Tracking evidence and limits

Tracking is implemented in `backend/reframe.py`, rather than being a UI-only
setting. It detects and associates face tracks and uses an audio-visual model
for speech evidence. The server generates one smoothed trajectory; browser
interpolation and FFmpeg crop expressions consume that trajectory, accounting
for trim time. Draft settings and analysis files are scoped to individual clips.

The controlled conversation fixture places real speaking video beside a frozen
listener, then swaps sides. The movement fixture translates real human video
across a canvas. Both exercise real inference without supplied trajectories,
but neither establishes natural two-person conversational accuracy or tracking
of a person walking freely through a scene.

Real inference was also run on the unmodified 20.04-second TalkNet demo video
already available at `/tmp/cascade-conversation.avi`: 501 frames were analyzed,
with 345 confident and 156 uncertain multi-face speaker-evidence frames. This
is multi-person group footage without independently verified turn labels. Model
confidence is not ground-truth accuracy, so this run does not establish correct
natural two-person speaker handoffs. That remains unverified with the available
footage. The previous blanket “complete” assessment was too broad.

Fixed Fill crops cannot always fit both people. Tracking can lose small,
occluded, or profile faces, and uncertain speech evidence can hold the last
crop. No guarantee of perfect speaker attribution or keeping every face fully
inside the frame is implied by the controls or these tests.
