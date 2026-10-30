import { useState } from 'react';
import { timelineClock } from './reelTiming';
export const REEL_PROMPT = 'Make this a polished high-energy Reel with a strong opening, beat-synced edits, bold animated captions, selective punch-in zooms, relevant B-roll, and music that stays beneath the dialogue.';
export default function ReelControls({ state, change, onApply, thinking }) {
  const [start, setStart] = useState(state.start);
  const [end, setEnd] = useState(Math.min(state.end, state.start + 1));
  const clock = timelineClock(state);
  return <div className="editor-controls reel-controls">
    <button className="editor-choice" disabled={thinking} onClick={() => onApply(REEL_PROMPT)}>{thinking ? 'Planning your Reel…' : 'Apply High-Energy Reel'}</button>
    <p className="editor-control-note">A coordinated style: complete-phrase opening, measured music beats, up to three punch-ins, one subtle shake, selective cutaways, and no flashes. Reapplying replaces this style’s effect arrangement.</p>
    {state.reel && <><p>{state.reel.hook_reason}</p><p>{state.reel.beat_sync_current ? `${state.reel.beats.length} detected beats · ${state.reel.bpm?.toFixed(1)} BPM · confidence ${state.reel.beat_confidence.toFixed(2)}` : 'Beat alignment unavailable or music changed. Reapply to resync.'}</p></>}
    <p>Edited duration: {clock.duration.toFixed(2)}s</p>
    {state.reel && <p>Applied profile: {state.reel.intensity || 'high-energy'} · {state.motion?.length || 0} timed zooms</p>}
    {state.timeline?.map((span, i) => <p key={i}>Keep source {span.start.toFixed(2)}–{span.end.toFixed(2)}s</p>)}
    {state.speed?.map((r, i) => <div key={i}><p>Pause ramp {r.start.toFixed(2)}–{r.end.toFixed(2)}s · {r.rate_from.toFixed(2)}×→{r.rate_to.toFixed(2)}×</p><button className="editor-choice" onClick={() => change(s => ({ ...s, speed: s.speed.filter((_, j) => i !== j) }))}>Remove ramp</button></div>)}
    <label className="editor-control">Pause start (source seconds)<input type="number" min={state.start} max={state.end} step=".05" value={start} onChange={e => setStart(Number(e.target.value))} /></label>
    <label className="editor-control">Pause end (source seconds)<input type="number" min={start} max={state.end} step=".05" value={end} onChange={e => setEnd(Number(e.target.value))} /></label>
    <button className="editor-choice" onClick={() => change(s => ({ ...s, speed: [...(s.speed || []), { start, end, rate_from: 1, rate_to: 1.8 }] }))}>Add pause-only speed ramp</button>
    <p className="editor-control-note">Saving/rendering rejects ramps over speech or without transcript timestamps. Rates ramp in eight small steps; original speech stays at natural speed.</p>
    <button className="editor-choice" onClick={() => change(s => ({ ...s, timeline: [], speed: [], reel: null }))}>Restore continuous source timing</button>
  </div>;
}
