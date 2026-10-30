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

// ---------- Captions ----------
const FONTS = ["Arial", "Georgia", "Verdana"];
const POSITIONS = ["top", "middle", "bottom"];

export function CaptionControls({ state, change, burnedIn }) {
  const captions = state.captions;
  const set = (field, value) => change((s) => ({ ...s, captions: { ...s.captions, [field]: value } }));

  return (
    <div className="editor-controls">
      {burnedIn && <p className="editor-control-note">This clip already has captions burned in. These controls add extra captions.</p>}
      <label className="editor-control editor-control-row">
        <input type="checkbox" checked={captions.enabled} onChange={(e) => set("enabled", e.target.checked)} />
        Show captions
      </label>
      <fieldset className="editor-controls" disabled={!captions.enabled}>
        <label className="editor-control">
          <span>Font</span>
          <select value={captions.font} onChange={(e) => set("font", e.target.value)}>
            {FONTS.map((font) => <option key={font}>{font}</option>)}
          </select>
        </label>
        <label className="editor-control">
          <span>Size <b>{captions.size}</b></span>
          <input type="range" min={12} max={80} value={captions.size} onChange={(e) => set("size", Number(e.target.value))} />
        </label>
        <label className="editor-control">Animation<select value={captions.animation || 'none'} onChange={e => set('animation', e.target.value)}><option value="none">None</option><option value="pop">Pop in</option><option value="karaoke">Highlighted words (estimated timing)</option></select></label>
        <label className="editor-control">Highlight color<input type="color" value={captions.highlight || '#ffdc39'} onChange={e => set('highlight', e.target.value)} /></label>
        <div className="editor-control-row">
          <label className="editor-control">
            <span>Text</span>
            <input type="color" value={captions.color} onChange={(e) => set("color", e.target.value)} />
          </label>
          <label className="editor-control">
            <span>Outline</span>
            <input type="color" value={captions.stroke} onChange={(e) => set("stroke", e.target.value)} />
          </label>
          <label className="editor-control">
            <span>Box</span>
            <input type="color" value={captions.background} onChange={(e) => set("background", e.target.value)} />
          </label>
        </div>
        <label className="editor-control">
          <span>Outline thickness <b>{captions.thickness}</b></span>
          <input type="range" min={0} max={8} step={0.5} value={captions.thickness}
            onChange={(e) => set("thickness", Number(e.target.value))} />
        </label>
        <label className="editor-control">
          <span>Box opacity <b>{Math.round(captions.opacity * 100)}%</b></span>
          <input type="range" min={0} max={1} step={0.05} value={captions.opacity}
            onChange={(e) => set("opacity", Number(e.target.value))} />
        </label>
        <div className="editor-control">
          <span>Position</span>
          <div className="editor-choice-row">
            {POSITIONS.map((position) => (
              <button key={position} type="button"
                className={`editor-choice${captions.position === position ? " active" : ""}`}
                onClick={() => set("position", position)}>{position}</button>
            ))}
          </div>
        </div>
        <label className="editor-control editor-control-row">
          <input type="checkbox" checked={captions.bold} onChange={(e) => set("bold", e.target.checked)} />
          Bold
        </label>
      </fieldset>
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
