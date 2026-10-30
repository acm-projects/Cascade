import { useEffect, useRef } from "react";
import { formatTime } from "../../../utils/time";
import {
  FONTS, LIMITS, POSITIONS, PRESETS, SWATCHES,
  applyPreset, clampField, cueText, presetMatches, resetCueText, setCueText,
} from "../captionStyles";
import "../EditorControls.css";
import "./CaptionsTab.css";

const POSITION_ICONS = { top: "⤒", middle: "≡", bottom: "⤓" };

// The Editor's Captions tab: an on/off switch, then two sub-tabs
//   Style - presets, font, size, colors, outline, box, position
//   Text  - fix the words of each caption line
// Props:
//   state, info                 - the draft and the clip's info (cues, burned_in)
//   change, patch, recordUndo   - from useClipDraft
//   player                      - the ClipPlayer's controlRef ({ seek(t) })
//   view, onView                - which sub-tab is open ("Style" | "Text")
//   focusedCue, onFocusCue      - the caption line picked here or on the timeline
function CaptionsTab({ state, info, change, patch, recordUndo, player, view, onView, focusedCue, onFocusCue }) {
  const captions = state.captions;
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });

  // Live edits (dragging a slider, picking a custom color, typing) use patch() so the preview
  // updates right away, and commit() turns the whole thing into ONE undo step at the end.
  const editing = useRef(null); // the state from before the live edit started
  function live(update) {
    if (!editing.current) editing.current = latest.current;
    patch(update);
  }
  function commit() {
    if (!editing.current) return;
    recordUndo(editing.current);
    editing.current = null;
  }

  const setStyle = (values) => change((s) => ({ ...s, captions: { ...s.captions, ...values } }));
  const liveStyle = (values) => live((s) => ({ ...s, captions: { ...s.captions, ...values } }));

  const slider = (field, step) => ({
    type: "range",
    min: LIMITS[field][0],
    max: LIMITS[field][1],
    step,
    value: captions[field],
    onChange: (e) => liveStyle({ [field]: clampField(field, e.target.value) }),
    onPointerDown: () => window.addEventListener("pointerup", commit, { once: true }),
    onKeyUp: commit,
    onBlur: commit,
  });

  return (
    <div className="editor-controls captions-tab">
      <label className="captions-toggle">
        <input type="checkbox" checked={captions.enabled} onChange={(e) => setStyle({ enabled: e.target.checked })} />
        <span>Show captions</span>
      </label>
      {info.burned_in && (
        <p className="editor-control-note">This clip already has captions burned in, so ours start off. Turn them on to add more.</p>
      )}

      <div className="captions-views" role="tablist">
        {["Style", "Text"].map((name) => (
          <button key={name} type="button" role="tab" aria-selected={view === name}
            className={`captions-view${view === name ? " active" : ""}`} onClick={() => onView(name)}>
            {name}
          </button>
        ))}
      </div>

      <fieldset className="editor-controls" disabled={!captions.enabled}>
        <label className="editor-control">Animation<select value={captions.animation || "none"} onChange={e => setStyle({ animation: e.target.value })}><option value="none">None</option><option value="pop">Pop in</option><option value="karaoke">Highlighted words (estimated timing)</option></select></label>
        <label className="editor-control">Highlight color<input type="color" value={captions.highlight || "#ffdc39"} onChange={e => setStyle({ highlight: e.target.value })} /></label>
        {view === "Style" ? (
          <>
            <div className="editor-control">
              <span>Presets</span>
              <div className="captions-presets">
                {PRESETS.map((preset) => (
                  <button key={preset.name} type="button"
                    className={`captions-preset${presetMatches(captions, preset) ? " active" : ""}`}
                    onClick={() => change((s) => ({ ...s, captions: applyPreset(s.captions, preset) }))}>
                    <span className="captions-preset-sample" style={presetSample(preset.values, captions)}>Aa</span>
                    {preset.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="captions-row">
              <label className="editor-control">
                <span>Font</span>
                <select value={captions.font} onChange={(e) => setStyle({ font: e.target.value })}>
                  {FONTS.map((font) => <option key={font}>{font}</option>)}
                </select>
              </label>
              <label className="editor-control editor-control-row captions-bold">
                <input type="checkbox" checked={captions.bold} onChange={(e) => setStyle({ bold: e.target.checked })} />
                Bold
              </label>
            </div>

            <label className="editor-control">
              <span>Size <b>{captions.size}</b></span>
              <input {...slider("size", 1)} />
            </label>

            <ColorPicker label="Text color" value={captions.color}
              onPick={(color) => setStyle({ color })} onLive={(color) => liveStyle({ color })} onDone={commit} />
            <ColorPicker label="Outline color" value={captions.stroke}
              onPick={(stroke) => setStyle({ stroke })} onLive={(stroke) => liveStyle({ stroke })} onDone={commit} />
            <label className="editor-control">
              <span>Outline thickness <b>{captions.thickness}</b></span>
              <input {...slider("thickness", 0.5)} />
            </label>

            <ColorPicker label="Box color" value={captions.background}
              onPick={(background) => setStyle({ background })} onLive={(background) => liveStyle({ background })} onDone={commit} />
            <label className="editor-control">
              <span>Box opacity <b>{Math.round(captions.opacity * 100)}%</b></span>
              <input {...slider("opacity", 0.05)} />
            </label>

            <div className="editor-control">
              <span>Position</span>
              <div className="editor-choice-row">
                {POSITIONS.map((position) => (
                  <button key={position} type="button" aria-pressed={captions.position === position}
                    className={`editor-choice${captions.position === position ? " active" : ""}`}
                    onClick={() => setStyle({ position })}>
                    {POSITION_ICONS[position]} {position}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : (
          <CaptionLines state={state} cues={info.cues} player={player} live={live} commit={commit}
            change={change} focusedCue={focusedCue} onFocusCue={onFocusCue} />
        )}
      </fieldset>
    </div>
  );
}

// What a preset's "Aa" sample looks like (fields the preset doesn't set come from the current captions)
function presetSample(values, captions) {
  const look = { ...captions, ...values };
  return {
    color: look.color,
    fontWeight: look.bold ? 800 : 500,
    WebkitTextStroke: look.thickness ? `${Math.min(look.thickness, 2) / 2}px ${look.stroke}` : undefined,
    background: look.opacity ? `color-mix(in srgb, ${look.background} ${look.opacity * 100}%, transparent)` : "#4b5d4f",
  };
}

// Five quick swatches + a custom color picker
function ColorPicker({ label, value, onPick, onLive, onDone }) {
  return (
    <div className="editor-control">
      <span>{label}</span>
      <div className="captions-swatches">
        {SWATCHES.map((swatch) => (
          <button key={swatch.color} type="button" title={swatch.name} aria-label={`${label}: ${swatch.name}`}
            aria-pressed={value.toLowerCase() === swatch.color}
            className={`captions-swatch${value.toLowerCase() === swatch.color ? " active" : ""}`}
            style={{ background: swatch.color }} onClick={() => onPick(swatch.color)} />
        ))}
        <input type="color" value={value} aria-label={`${label}: custom`} title="Custom color"
          onChange={(e) => onLive(e.target.value)} onBlur={onDone} />
      </div>
    </div>
  );
}

// The Text sub-tab: one row per caption line. Click a row to jump there; type to fix the words.
function CaptionLines({ state, cues, player, live, commit, change, focusedCue, onFocusCue }) {
  const focusedRow = useRef(null);

  // The line picked on the timeline scrolls into view
  useEffect(() => {
    focusedRow.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focusedCue]);

  if (cues.length === 0) return <p className="editor-control-note">This clip has no caption lines.</p>;

  return (
    <ol className="captions-lines">
      {cues.map((cue, index) => {
        const edited = state.texts?.[String(index)] !== undefined;
        const focused = index === focusedCue;
        return (
          <li key={index} ref={focused ? focusedRow : null} className={`captions-line${focused ? " focused" : ""}`}
            onClick={() => {
              player.current?.seek(cue.start);
              onFocusCue(index);
            }}>
            <span className="captions-line-time">{formatTime(cue.start)}</span>
            <input type="text" value={cueText(state.texts, cues, index)} aria-label={`Caption line ${index + 1}`}
              onChange={(e) => live((s) => ({ ...s, texts: setCueText(s.texts, index, e.target.value) }))}
              onBlur={commit} />
            {edited && (
              <button type="button" className="captions-reset" title={`Back to: "${cue.text}"`}
                onClick={(e) => {
                  e.stopPropagation();
                  change((s) => ({ ...s, texts: resetCueText(s.texts, index) }));
                }}>
                Reset
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export default CaptionsTab;
