import './AIEditorChat.css';
import { timelineClock } from './reelTiming';

const OCC = 'openchatcut-0.2.17';
const TRANSITIONS = ['none', 'fade', 'whip', 'blur', 'zoom'];
const OCC_TRANSITIONS = [...TRANSITIONS, 'flash', 'shake', 'glitch', 'dip'];
const ZOOM_STYLES = ['punch', 'snap', 'pulse', 'whip-in', 'bounce', 'slow-push'];

export default function SequenceControls({ state, change, player }) {
  const sequence = state.fablecut;
  if (!sequence) return null;
  const occ = sequence.engine === OCC;
  const engineName = 'AI';
  const setSequence = values => change(s => ({ ...s, fablecut: { ...s.fablecut, ...values } }));
  const base = timelineClock({ ...state, fablecut: null });
  const spans = sequence.shots.reduce((all, shot, index) => {
    const duration = Math.max(0, 2 * (base.output(Math.min(state.end, shot.end)) - base.output(Math.max(state.start, shot.start))) / (shot.rate_from + shot.rate_to));
    const previous = all.at(-1);
    return [...all, { index, start: previous ? previous.start + previous.duration : 0, duration }];
  }, []);
  const cursor = spans.reduce((total, span) => total + span.duration, 0);
  function update(index, values) {
    change(s => ({ ...s, fablecut: { ...s.fablecut, shots: s.fablecut.shots.map((shot, i) => i === index ? { ...shot, ...values } : shot) } }));
  }
  return <section className="ai-sequence" aria-label={`${engineName} sequence`}>
    <b>AI sequence</b><span> · played in this order · source times below</span>
    <label>Sequence frame <select value={sequence.ratio} onChange={e => change(s => ({ ...s, fablecut: { ...s.fablecut, ratio: e.target.value } }))}>
      <option value="9:16">{occ ? '9:16 portrait' : '9:16 portrait crop'}</option><option value="original">Manual frame</option>
    </select></label>
    {occ && <>
      <label>Portrait framing <select value={sequence.framing} onChange={e => setSequence({ framing: e.target.value })}>
        <option value="blur">Whole frame on blurred fill</option><option value="cover">Crop to fill</option><option value="fit">Letterbox</option>
      </select></label>
      <label>Look <select value={sequence.look} onChange={e => setSequence({ look: e.target.value })}>
        <option value="none">Natural</option><option value="teal-orange">Teal-orange cinematic</option>
      </select></label>
    </>}
    <div className="ai-sequence-clock">Edited time · {cursor.toFixed(2)}s</div>
    <div className="ai-sequence-strip" aria-label="Edited sequence time scale">{spans.filter(s => s.duration > 0).map(span => <button key={span.index} type="button" style={{ width: `${100 * span.duration / cursor}%` }} onClick={() => player.current?.seek(sequence.shots[span.index].start)} title={`Output ${span.start.toFixed(2)}–${(span.start + span.duration).toFixed(2)}s`}>
      {span.index + 1}<small>{span.start.toFixed(1)}s</small>
    </button>)}</div>
    <details className="ai-sequence-details"><summary>Edit individual shots · {sequence.shots.length} shots</summary>
    <div className="ai-sequence-shots">{sequence.shots.map((shot, index) => <div className="ai-sequence-shot" key={index}>
      <button type="button" onClick={() => player.current?.seek(shot.start)} title={shot.reason}>Shot {index + 1} · {shot.start.toFixed(2)}–{shot.end.toFixed(2)}s</button>
      <label>Transition <select value={shot.transition} onChange={e => update(index, { transition: e.target.value })}>
        {(occ ? OCC_TRANSITIONS : TRANSITIONS).map(value => <option key={value}>{value}</option>)}
      </select></label>
      {occ && <label>Zoom style <select value={shot.zoom_style} onChange={e => update(index, { zoom_style: e.target.value })}>
        {ZOOM_STYLES.map(value => <option key={value}>{value}</option>)}
      </select></label>}
      <label>Punch-in <input aria-label={`Shot ${index + 1} punch-in`} type="range" min="1" max="1.3" step=".01" value={shot.zoom} onChange={e => update(index, { zoom: Number(e.target.value) })} /></label>
      <button type="button" disabled={sequence.shots.length < 2} onClick={() => change(s => ({ ...s, fablecut: { ...s.fablecut, shots: s.fablecut.shots.filter((_, i) => i !== index) } }))}>Remove shot {index + 1}</button>
      <button type="button" disabled={index === 0} onClick={() => change(s => {
        const shots = [...s.fablecut.shots]; [shots[index - 1], shots[index]] = [shots[index], shots[index - 1]];
        return { ...s, fablecut: { ...s.fablecut, shots } };
      })}>Move shot {index + 1} earlier</button>
    </div>)}</div></details>
    <p>Manual edits remain underneath this sequence. </p>
    <p>{sequence.music_asset_id ? 'AI music bed on edited time; existing manual music takes priority.' : 'No AI music bed.'} {sequence.sound_design ? (occ ? 'Whooshes on transitions and impacts on punch-ins.' : 'Selective impacts, whooshes and a build riser.') : 'No AI sound effects.'}</p>
    <button type="button" onClick={() => change(s => ({ ...s, fablecut: null }))}>Remove AI sequence</button>
  </section>;
}
