# Editor and Exports delivery update

Implemented October 21, 2026, against the rendered application. No screenshot
attachment was available. Existing project histories and saved edits were kept;
there is no data migration or history regrouping.

- Editor: Go to Exports replaces direct video downloads. Video, Captions,
  B-roll, Research Agent, Chat and Effects are separate tools.
- Timeline: one compact video strip by default; Expand tracks reveals synchronized
  Video, Captions and B-roll layers. Collapse changes only the view.
- Framing: Fill automatically prepares real face/speaker tracking when cropping is
  needed. Existing Fill drafts are prepared on open. Exports performs identical
  preparation; matching source/output geometry skips tracking. No manual x/y
  sliders or enable toggle remain. Saved focus choices are retained.
- Research Agent: account preferences use the existing account-scoped `/api/settings`
  store and retain their values. Analyze trends still uses the existing source-video
  research endpoint. Preferences retain their existing behavior: they are stored,
  but do not currently influence generation.
- Settings: existing account/Profile/Sign out remain; preferences link back to the
  Research Agent for the last opened project, or to project selection.
- B-roll: Find B-roll, Preview & Add, and Added B-roll are distinct sections. Add
  and direct dragging from results work. Hovering the timeline expands it, previews
  a valid insertion, and rejects overlaps. Dropping seeks to the insertion and
  updates the preview. Segment movement and both-edge trims use the same state,
  one undo transaction per gesture, per-clip save, and synchronized numeric fields.
  The panel remains available for precise timing and source-offset changes.
- Exports: rounded grouped video tiles, subtle offsets and transitions, shared
  collapsible Session → Wave → Clips navigation, synchronized checkboxes, individual
  downloads and a ZIP containing only the checked clips. Progress, success, failed
  previews and Retry preview are visible. Actual edited previews are prepared in
  the background rather than presenting static thumbnail placeholders. YouTube
  retains its existing honest setup/help behavior; upload is not implemented.

## Verification

Run the isolated server with real local models and controlled fixtures:

```sh
CASCADE_REFRAME_MODELS=/tmp/cascade-reframe-models \
CASCADE_REFRAME_FIXTURES=/tmp/cascade-tracking-fixtures \
python3 tests/editor_browser_server.py
```

Use isolated Chrome on DevTools port 9333. Run browser suites sequentially:

```sh
python3 -m tests.test_editor_delivery_browser
python3 -m tests.test_exports_browser
python3 -m tests.test_reframe_browser
python3 -m tests.test_editor_aspect_browser
python3 -m tests.test_editor_layout_browser
```

The delivery suite uses actual mouse dragging from a draggable result card, tests
hover expansion and insertion indication before drop, moves and trims added
segments, checks Add/replace/remove, undo/redo, saved reload, preferences, Research
Agent request/results, Settings, and desktop/1024/768/390px layouts. Screenshots
are in `/tmp/cascade-delivery-browser-artifacts`.

The export suite downloads a real edited MP4 and a ZIP containing a selected subset,
checks original audio, duration, framing, captions, effects and B-roll, and forces a
preview failure to verify retry. Auth, Pexels, chat and trend-provider replies are
fixtures; production persistence, renderer, pointer/drop handling and downloads run.
No paid provider calls were made. Live trend research and live Pexels/provider
availability are not established by these browser tests.

Tracking tests run real YuNet/Light-ASD inference, not a mocked camera path. They
check per-clip focus/analysis independence, legacy Fill preparation with caption
edits retained, motion, controlled speaker-side changes, smooth trajectories, and
browser-preview versus decoded-export frames. The aspect suite additionally runs
actual no-face analysis and verifies the centered fallback and export agreement.

The moving-human fixture translates real speaking footage across a canvas; the
conversation fixture alternates real speaking footage and a frozen listener.
Natural two-person turn-taking accuracy and tracking a freely walking subject
remain unverified. The earlier unmodified group-video run is not a ground-truth
benchmark. Occlusion, profiles, tiny faces, overlapping speech and fixed-crop
limitations remain. See [Auto Reframe](auto-reframe.md) for setup and limitations.
