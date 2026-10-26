# Branching AI Studio

The canvas route still uses FastAPI and Clerk. Its UI is now an actual React Flow
app bundled locally from `studio-ui/` into `web/studio/`, served at `/studio-assets`.
It needs no separate frontend server, CDN scripts, or browser-exposed API keys.

## Workflow

1. Upload the original video and describe the clips to find. Choose 1â€“12 clips.
2. Each request produces a generation node and its actual result clips. Empty,
   processing, error and fewer-than-requested results are shown honestly.
3. Check the single **Select clip** checkbox on one or more clips. Those same
   checked clips are the assistant context and the Editor selection. Current-session
   selections appear above the composer. Ask for similar moments to add child clips connected directly to the checked
   clips in the same session. Parents stay visible and unchanged; any child can
   be checked to branch again. Or discuss the selected clips. Different footage
   from the uploaded source can match their humor, action, tone and pacing.
4. **Discuss clips** asks the configured model about the selected context and saves
   the conversation without queueing generation. It does not claim to edit media.
5. Create named sessions to explore different moods with the same source. Sessions
   have separate requests, chat, references, node positions and viewport state.
6. Check all clips you want from any generation/session, then choose
   **Continue to Editor**. The existing editor shows just the checked clips when
   opened with `selection=canvas`; its standard all-clips mode is still supported.

Nodes can be dragged, the graph panned/zoomed, and generations revealed from chat.
Previews fetch authenticated video only when opened, then release Blob URLs when
closed. Keeping many video elements loaded across a large graph is avoided.

## Persistence and authorization

The existing `cascade_app.records` project payload holds a `studio` object:
sessions, active session, messages, positions, viewport, reference selections and
the shared Editor selection. **No new tables** or parallel schema are introduced.
Jobs retain `studio_session_id`, `parent_clips` and idempotent request IDs, alongside
the existing source/job/result metadata. Earlier generations are grouped into
source-specific sessions on first opening the new studio.

All routes are under `/api/projects/{pid}/studio` and use verified Clerk identity
plus existing ownership checks. References must be valid clips from the current
session and original source. Editor choices must belong to the project. Client
node positions cannot introduce arbitrary graph nodes or alter generation edges.
Generation requests are saved before worker submission, preventing retries from
silently creating extra paid jobs. Chat and generation use the configured provider;
testing this interface does not require real provider requests.

Failed saves are visible and offer Retry save. Requests preserve their source
context, and existing generation retry/cancellation endpoints remain available.
The app still uses one API worker; original source media must remain available
locally, while generated media follows the existing local/S3 storage setting.

## Build and checks

```powershell
cd studio-ui
npm ci
npm run build
cd ..
node --test studio-ui/src/graph.test.js
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_studio.py
```

Commit the generated `web/studio/studio.js` and CSS along with source/lockfiles so
other teammates can start FastAPI without a Node build. The synthetic browser
fixture `tests/project_browser_server.py` runs on port 8767 with mock identity and
generation and actual small FFmpeg media. It is not a production authentication
route and must not be deployed. The opt-in Neon smoke test checks studio state
after removing local metadata; synthetic database records are cleaned afterward.


## Revising a liked clip

Check one or more clips and describe what you like or want more of.
The selected moment supplies tone, action, prompt and captions as examples. The
agent can search different footage in the same uploaded source. The request uses
`operation: revise`; plain requests without a selection remain normal generations.
A successful update replaces that clip's canvas slot with its new alternatives,
inside the existing generation. It does not add another generation column.

Revision media keeps real job/clip IDs for previews and editing; the original
media/results are retained. The session's `clip_revisions` map persists the visible
replacement. Pending, failed and empty revisions keep the previous clip visible.
Replacement clips can themselves be selected for another revision. Existing
multi-reference generation API requests still use their prior behavior unless
`operation: revise` is explicitly requested.


## One shared checkbox

`studio.editor_clips` is the canonical checked selection (up to 100 clips across
sessions). Each session's AI references are derived from that list using its own
job IDs. The old separate AI selections are merged once on upgrade, preserving
existing choices. Clearing or unchecking updates both destinations. AI requests
accept up to twelve current-session selections; larger selections can still be
sent to the Editor.

For a multi-selection revision, alternatives are assigned across the selected
canvas slots without duplicated media cards or another generation column. If a
slot receives no alternatives, it keeps the previous clip. On completion, checked
originals are replaced in the shared selection by their visible replacement clips.
Unchecking while a request is pending prevents it from selecting the replacements
again. Empty and failed requests retain the previous visible results and selection.

Select two or more clips to combine their creative qualities in each new result.
For example, ask for three clips blending one reference’s humor with another’s action.
Each child connects to all selected parents; the source video supplies the footage.
