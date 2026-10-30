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

// ---------- Aspect ratio ----------
const RATIOS = [
  { id: "original", label: "Original" },
  { id: "9:16", label: "9:16 Vertical" },
  { id: "1:1", label: "1:1 Square" },
  { id: "4:5", label: "4:5 Portrait" },
  { id: "16:9", label: "16:9 Wide" },
  { id: "4:3", label: "4:3" },
];

export function RatioControls({ state, change }) {
  const composition = state.composition;
  const set = (field, value) => change((s) => ({ ...s, composition: { ...s.composition, [field]: value } }));

  return (
    <div className="editor-controls">
      <div className="editor-choice-grid">
        {RATIOS.map((ratio) => (
          <button key={ratio.id} type="button" className={`editor-choice${composition.ratio === ratio.id ? " active" : ""}`}
            onClick={() => set("ratio", ratio.id)}>{ratio.label}</button>
        ))}
      </div>
      <div className="editor-control">
        <span>Fit</span>
        <div className="editor-choice-row">
          <button type="button" className={`editor-choice${composition.mode === "fit" ? " active" : ""}`}
            onClick={() => set("mode", "fit")}>Fit (show everything)</button>
          <button type="button" className={`editor-choice${composition.mode === "fill" ? " active" : ""}`}
            onClick={() => set("mode", "fill")}>Fill (crop)</button>
        </div>
      </div>
      {composition.mode === "fill" ? (
        <>
          <label className="editor-control">
            <span>Move left / right</span>
            <input type="range" min={0} max={1} step={0.01} value={composition.x} onChange={(e) => set("x", Number(e.target.value))} />
          </label>
          <label className="editor-control">
            <span>Move up / down</span>
            <input type="range" min={0} max={1} step={0.01} value={composition.y} onChange={(e) => set("y", Number(e.target.value))} />
          </label>
        </>
      ) : (
        <label className="editor-control">
          <span>Background color</span>
          <input type="color" value={composition.background} onChange={(e) => set("background", e.target.value)} />
        </label>
      )}
    </div>
  );
}
