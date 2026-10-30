# Guided Trends modal

The shared Editor/Exports modal now has Overview, Suggested edits, and References
tabs. The preview and compact fox guide stay visible on desktop; only the right
content pane scrolls. Mobile stacks naturally with locked background overflow,
an always-accessible close button, and a sticky action bar. Tabs support arrow keys,
Home/End, focus trapping/return and Escape.

Overview limits strengths/opportunities to three, removes reference plots and
missing-trait lists from clip guidance, and keeps methodology/expiry/diagnostics in
collapsed details. Source chips open References and focus/scroll the matching card.
The source count stays visible. Cards show actual retained titles, thumbnails,
channels, dates, views, observed/explained techniques and supporting suggestions.
Missing metadata is labeled unavailable, never invented. Failed/unprocessed sources
remain separate. Day-only publication dates preserve the source day across time zones.

Editing goal and search terms are separate. Generic instructions are not literal
YouTube queries. Queries derive editing relevance from the clip's content and tone;
users may override terms in Search details. New research saves explicit per-reference
selection rationale and learning notes. Older reports honestly say when rationale
was not retained; the redesign does not replace them with rewritten fake research.

The real report used for screenshots incorrectly inferred no dialogue from missing
saved cues. That certainty is suppressed in the main view and audio uncertainty is
shown explicitly. New research attempts actual audio transcription when saved cues
are absent, retaining failures/uncertainty rather than declaring silence. Recovered
research text does not masquerade as editor timing: phrase/caption actions remain
unsupported until reliable editor timestamps exist.

Suggested edits show current edited clip time via the shared source/output clock,
or explicitly say timing is unavailable. Cards include concrete execution scope,
reference chips, checkboxes and outcomes. Selected edits execute in one undoable
batch, keep partial successes and preserve existing cuts when tightening pauses.
Receipts match the resulting edit state, so Applied status survives saved reload,
Undo returns it to Suggested, and Redo restores it. Only the known applied-state
chain can reuse the analysis; unrelated manual changes still invalidate it.

Screenshots in `/tmp/cascade-guided-{overview,edits,references,mobile}.png` show the
unchanged saved real research from the prior signed-in run, paired with a copy of
the identical clip and its audio assets. The display harness isolates ownership
and storage only; it does not simulate fresh findings or change the real project.
Its new-analysis function deliberately errors instead of fabricating a result.
Keyboard, provenance navigation, selected Apply, Undo/Redo, save/reload and true
390px mobile viewport checks run in a separate automated test browser, not the
user's signed-in browser. Edge-case tests cover long text, equivalent duplicates,
missing metadata, partial failure, absent timing, audio uncertainty and zero sources.
The regression run passed 119 backend tests and 29 frontend tests; both browser
suites and the production build passed. Lint retains three preexisting warnings.

Validation commands:

```sh
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
CASCADE_WARM_MODELS=0 .venv/bin/python -m unittest tests.test_guided_trends -q
```

The existing startup/API/OAuth configuration is unchanged. All work stays local and
uncommitted on `mlk`; no secrets, `.local-https/`, original media or unrelated edits
were overwritten. No publishing or fresh paid research calls were made for this UI
redesign. Camera stabilization and other unimplemented advice are explicitly outside
the Apply action; supported edits continue through the existing renderer.
