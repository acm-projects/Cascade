# Studio canvas nodes — CAS-26 / ticket 3.2

The final ticket keeps prompts as full cards. `PromptNode.jsx` reuses
`GenerationNode.jsx`; essential details never depend on hovering or opening a popup.

## What existed already

The MLK branch already had Source, Generation and Clip components, React Flow
handles, saved graph positions, file upload, Stop/Retry/Reuse actions, clip
checkboxes, a larger preview dialog, and one shared selection for AI references
and Editor handoff. Those behaviors remain. The graph already handled clip
revisions, including keeping an original clip visible while an update fails.

What was missing: the ticket's flat node contracts, inline hover playback,
top-right clip checkboxes, permanent Selected N labels, optional grade badges,
source status rendering, and a development canvas showing the states together.

## Data flow and decisions

1. **Adapt server data at the graph boundary.** Backend records use fields such
   as `job_id` and `clip_url`; nodes receive `jobId` and `clipUrl`. `buildGraph`
   translates these once. Rendering components should not need to understand the
   entire backend document. Existing node IDs (`generation:<job>`, for example)
   remain unchanged, even though the renderer type is now `prompt`. This preserves
   saved positions and backend validation.
2. **Reuse the full prompt card.** `PromptNode` exports the existing card renderer,
   which accepts the ticket's flat contract and supports older group-based data.
   The card shows prompt, count, state, reference numbers, progress and applicable
   actions. Its handles still support source → prompt → clip and clip → prompt
   branches. State colors distinguish ready, working and failed requests.
3. **Separate clip selection from opening.** Clicking a card opens it; clicking
   its top-right checkbox only changes selection. `stopPropagation` prevents that
   click from also reaching the card. `nodrag`/`nopan` prevent canvas gestures
   from consuming the interaction. Keyboard users can open a focused clip with
   Enter or Space and operate its native checkbox normally.
4. **Let the server own selection numbers.** MLK's Studio selection endpoint did
   not contain the permanent numbering described in the ticket. Each session now
   stores `selection_numbers` and `next_selection_number`. If clips 1 and 2 are
   selected and 1 is unchecked, 2 keeps its label. The next selection gets 3;
   selecting the old clip again gets a new number. Existing selections receive
   numbers when their Studio document is loaded. Ref objects remain the same
   `{job_id, clip_index}` shape, preserving Editor and generation contracts.
5. **Keep request history truthful.** A new generation stores a snapshot of its
   reference numbers in job metadata. Later unchecking or reselecting a clip
   cannot relabel that generation's history. Old jobs have no historical number
   snapshot; the UI does not invent one.
6. **Preview protected media through the authenticated API.** A browser video
   element cannot attach the application's bearer token to a media request.
   Real clips therefore load through `api.getMedia` when hovered and play from a
   temporary blob URL. Leaving pauses and resets playback, and releases the URL.
   A request finishing after leave/unmount is ignored. This avoids permanent
   retention of every preview video. The tradeoff is that re-hovering downloads
   the clip again; a bounded cache or authenticated streaming could be future work.
7. **Wait for selection saves before the next selection/prompt.** The checkbox
   updates optimistically, then refreshes authoritative numbers from the server.
   During that brief save, selection controls and prompt submission are disabled.
   This prevents competing whole-list updates from silently losing selections.

## Review and validation

Run the frontend with `npm run dev` and open `/dev/ui`. Its Studio example uses
a small generated test-pattern video, not a user's media or a paid AI service.
It includes completed, processing and failed prompts; selected/unselected clips;
and an optional grade badge. Try the checkbox, hover preview, and prompt actions.
This route and its mock assets are excluded from production builds.

From `frontend/`:

```sh
npm test
npm run test:nodes
npm run build
npm run lint
```

Backend regressions (FFmpeg and FFprobe must be on PATH):

```sh
python -m unittest discover -s tests -p test_studio.py -q
```

Component tests cover visible prompt details/actions, checkbox event isolation,
preview playback/reset, protected media URL cleanup, late responses, optional
grade rendering and source states. Graph tests cover contract mapping plus
existing reference/revision layouts. Backend tests verify permanent numbering
across reloads and saved reference snapshots.

Source thumbnails/durations and clip grades render when supplied. The current
generation API does not guarantee source thumbnail/duration fields, and this
ticket does not add media extraction or AI grading. No paid generation was run
to validate these UI changes.
