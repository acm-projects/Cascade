import { formatTime } from "../../utils/time";
import "./EditorControls.css";

// The Editor's right-panel controls. Each one calls change(...) with a new draft state, which
// makes it undoable and auto-saves it (see useClipDraft). Allowed values match backend/editor_backend.py.

const MIN_LENGTH = 0.5; // seconds; the backend needs at least 0.05

// ---------- Trim ----------
export function TrimControls({ state, duration, change }) {
  const step = 0.1;
  const setStart = (value) => change((s) => ({ ...s, start: Math.min(Number(value), s.end - MIN_LENGTH) }));
  const setEnd = (value) => change((s) => ({ ...s, end: Math.max(Number(value), s.start + MIN_LENGTH) }));

  return (
    <div className="editor-controls">
      <label className="editor-control">
        <span>Start <b>{formatTime(state.start)}</b></span>
        <input type="range" min={0} max={duration} step={step} value={state.start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label className="editor-control">
        <span>End <b>{formatTime(state.end)}</b></span>
        <input type="range" min={0} max={duration} step={step} value={state.end} onChange={(e) => setEnd(e.target.value)} />
      </label>
      <p className="editor-control-note">Clip length: {formatTime(state.end - state.start)} of {formatTime(duration)}</p>
      <button type="button" className="btn btn-ghost btn-small"
        onClick={() => change((s) => ({ ...s, start: 0, end: duration }))}>Reset trim</button>
    </div>
  );
}
