import { useEffect, useRef } from "react";
import "../EditorControls.css";
import "./AspectTab.css";
import Icon from "../../../components/ui/Icon";
import { PRESETS } from "../aspectRatios";

// The Editor's Aspect Ratio tab: frame shape, Fit (show everything) or Fill (crop), and where the crop sits.
// In Fill you can also drag the video in the preview (ClipPlayer). Cropped exports follow the people in
// the shot automatically (useAutoFraming), so there's no separate switch for that here.
// Props: state, change, patch, recordUndo (from useClipDraft), info (the clip's width/height)
function AspectTab({ state, info, change, patch, recordUndo }) {
  const composition = state.composition;
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });

  const set = (values) => change((s) => ({ ...s, composition: { ...s.composition, ...values } }));

  // Sliders and the color picker update live (patch) and become ONE undo step when you let go
  const editing = useRef(null);
  function live(values) {
    if (!editing.current) editing.current = latest.current;
    patch((s) => ({ ...s, composition: { ...s.composition, ...values } }));
  }
  function commit() {
    if (!editing.current) return;
    recordUndo(editing.current);
    editing.current = null;
  }
  const slider = (field) => ({
    type: "range", min: 0, max: 1, step: 0.01, value: composition[field],
    onChange: (e) => live({ [field]: Number(e.target.value) }),
    onPointerDown: () => window.addEventListener("pointerup", commit, { once: true }),
    onKeyUp: commit,
    onBlur: commit,
  });

  const clipShape = info.width && info.height ? { w: info.width, h: info.height } : { w: 16, h: 9 };
  const centered = composition.x === 0.5 && composition.y === 0.5;

  return (
    <div className="editor-controls aspect-tab">
      <div className="aspect-presets">
        {PRESETS.map((preset) => {
          const shape = preset.w ? preset : clipShape;
          return (
            <button key={preset.id} type="button" aria-pressed={composition.ratio === preset.id}
              className={`aspect-preset${composition.ratio === preset.id ? " active" : ""}`}
              onClick={() => set(preset.id === "original" ? { ratio: "original", mode: "fit", x: 0.5, y: 0.5 } : { ratio: preset.id, mode: "fill" })}>
              <span className="aspect-shape-box" aria-hidden="true">
                <span className="aspect-shape" style={{
                  aspectRatio: `${shape.w} / ${shape.h}`,
                  ...(shape.w < shape.h ? { height: "100%" } : { width: "100%" }), // tall shapes fill the height
                }} />
              </span>
              <b>{preset.label}</b>
              <span className="aspect-hint">{preset.hint}</span>
            </button>
          );
        })}
      </div>

      <div className="aspect-modes" role="radiogroup" aria-label="Fit or fill">
        {[["fit", "Fit", "Show everything"], ["fill", "Fill", "Crop to fill"]].map(([mode, label, hint]) => (
          <button key={mode} type="button" role="radio" aria-checked={composition.mode === mode}
            className={`aspect-mode${composition.mode === mode ? " active" : ""}`} onClick={() => set({ mode })}>
            <b>{label}</b> <span>{hint}</span>
          </button>
        ))}
      </div>

      {composition.mode === "fill" ? (
        <>
          <p className="editor-control-note">Fill follows whoever is talking: person one while they speak, then person two. You can also drag the video in the preview to choose what stays in the frame.</p>
          <label className="editor-control">
            <span>Horizontal</span>
            <input {...slider("x")} aria-label="Move the crop left or right" />
          </label>
          <label className="editor-control">
            <span>Vertical</span>
            <input {...slider("y")} aria-label="Move the crop up or down" />
          </label>
          <button type="button" className="btn btn-small btn-ghost" disabled={centered}
            onClick={() => set({ x: 0.5, y: 0.5 })}><Icon name="target" /> Center</button>
        </>
      ) : (
        <label className="editor-control">
          <span>Background color (the bars around the video)</span>
          <input type="color" value={composition.background}
            onChange={(e) => live({ background: e.target.value })} onBlur={commit} />
        </label>
      )}
    </div>
  );
}

export default AspectTab;
