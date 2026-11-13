// Measured numbers for the Trend Analysis page. Pure functions (no React), so they're easy to test.
// Rule of this page: charts and numbers only come from measurements (FFmpeg on the files, or your
// edit's own settings). Anything an AI judged is shown as a written observation instead.
import { timelineClock } from '../reelTiming.js';

const round = (n, d = 1) => Math.round(n * 10 ** d) / 10 ** d;

/** "0:07" / "1:04" */
export function clock(seconds) {
  if (!Number.isFinite(seconds)) return '–';
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** "3.4 s" */
export const secs = (n, d = 1) => (Number.isFinite(n) ? `${round(n, d)} s` : '–');

/** Is this source-time moment still in the edit (inside the trim and a kept timeline span)? */
export function kept(t, state) {
  if (t < state.start || t >= state.end) return false;
  if (!state.timeline?.length) return true;
  return state.timeline.some(span => t >= span.start && t < span.end);
}

/** Caption lines as they play in the edited video: [{ start, end, text }] in output seconds. */
export function editCues(state, info) {
  const time = timelineClock(state);
  return (info?.cues || []).map((cue, index) => ({ ...cue, index, text: state.texts?.[index] ?? cue.text }))
    .filter(cue => cue.end > state.start && cue.start < state.end && (kept(cue.start, state) || kept(cue.end - 0.01, state)))
    .map(cue => ({ index: cue.index, text: cue.text, source: cue.start,
      start: time.output(Math.max(cue.start, state.start)), end: time.output(Math.min(cue.end, state.end)) }))
    .filter(cue => cue.end - cue.start > 0.05);
}

/** Music segments in output seconds, with how loud they are relative to speech. */
export function musicSpans(state) {
  const time = timelineClock(state);
  return (state.audio || []).filter(a => a.track === 'music').map(a => {
    const start = time.output(Math.max(a.start, state.start)), end = time.output(Math.min(a.start + a.duration, state.end));
    // Ducking lowers music under speech; that's the level that matters while someone is talking.
    const underSpeech = a.duck ? a.volume * a.duck_gain : a.volume;
    return { id: a.id, start, end, volume: a.volume, underSpeech, duck: a.duck };
  }).filter(m => m.end > m.start);
}

/** Merge overlapping [start, end] intervals. */
function merge(spans) {
  const out = [];
  for (const s of [...spans].sort((a, b) => a.start - b.start)) {
    const last = out.at(-1);
    if (last && s.start <= last.end) last.end = Math.max(last.end, s.end); else out.push({ ...s });
  }
  return out;
}

/** Moments where music plays under speech loud enough that it may cover words.
 *  Threshold: music under speech at more than 35% of the speech level (both from your edit's settings). */
export function speechConflicts(state, info, threshold = 0.35) {
  const speech = merge(editCues(state, info).map(c => ({ start: c.start, end: c.end })));
  const dialogue = Math.max(0.01, state.dialogue_volume ?? 1);
  const out = [];
  for (const m of musicSpans(state)) {
    const ratio = m.underSpeech / dialogue;
    if (ratio <= threshold) continue;
    for (const s of speech) {
      const start = Math.max(s.start, m.start), end = Math.min(s.end, m.end);
      if (end - start > 0.2) out.push({ start, end, ratio: round(ratio, 2) });
    }
  }
  return merge(out).map(c => ({ ...c, ratio: Math.max(...out.filter(o => o.start < c.end && o.end > c.start).map(o => o.ratio)) }));
}

/** Shot lengths from cut times: [{ start, end, length }]. */
export function shots(cuts = [], duration) {
  const points = [0, ...cuts.filter(t => t > 0 && t < duration), duration];
  return points.slice(1).map((end, i) => ({ start: points[i], end, length: end - points[i] }));
}

/** Cuts per window (for the pacing chart): [{ t, count }] with t = window start. */
export function pacing(cuts = [], duration, window = 5) {
  if (!Number.isFinite(duration) || duration <= 0) return [];
  const bins = Math.max(1, Math.ceil(duration / window));
  return Array.from({ length: bins }, (_, i) => ({ t: i * window, end: Math.min(duration, (i + 1) * window),
    count: cuts.filter(c => c >= i * window && c < (i + 1) * window).length }));
}

/** Everything measured about one video, or null when it was never measured. */
export function measuredVideo(m) {
  if (!m || !Number.isFinite(m.duration)) return null;
  const span = Math.min(m.duration, m.measured_seconds || m.duration);
  const cuts = Array.isArray(m.cuts) ? m.cuts.filter(t => t < span) : null;
  return {
    duration: m.duration, span, width: m.width, height: m.height,
    cuts, avgShot: cuts ? span / (cuts.length + 1) : null,
    loudness: Array.isArray(m.loudness) ? m.loudness : null, window: m.window || 0.5,
  };
}

/** The four at-a-glance measurements for your edit. Each value can be null = "not measured". */
export function editFindings(state, info, measured) {
  const time = timelineClock(state);
  const duration = measured?.duration ?? time.duration;
  const cues = editCues(state, info);
  const speechCovered = merge(cues.map(c => ({ start: c.start, end: c.end }))).reduce((sum, s) => sum + s.end - s.start, 0);
  const captionsOn = state.captions?.enabled !== false;
  const music = musicSpans(state);
  const loudestMusic = music.length ? Math.max(...music.map(m => m.underSpeech)) : 0;
  return {
    duration,
    firstWords: cues.length ? cues[0].start : null,
    avgShot: measured?.avgShot ?? null,
    cutCount: measured?.cuts?.length ?? null,
    captionCoverage: !info?.cues?.length ? null : captionsOn ? Math.min(1, speechCovered / Math.max(0.1, duration)) : 0,
    captionsOn,
    speechLevel: state.dialogue_volume ?? 1,
    musicLevel: music.length ? loudestMusic : 0,
    hasMusic: music.length > 0,
    conflicts: speechConflicts(state, info),
  };
}

/** min–max across the references that have a value (null when none do). */
export function range(values) {
  const v = values.filter(Number.isFinite);
  if (!v.length) return null;
  return { min: Math.min(...v), max: Math.max(...v), count: v.length };
}

/** "4 of 6 references" style count for a measured rule. */
export function countWhere(items, test) {
  const known = items.filter(x => x != null);
  return { hits: known.filter(test).length, of: known.length };
}

/** Video shape (width ÷ height) for the players, or the 9:16 short-form default. */
export function aspect(width, height, fallback = 9 / 16) {
  return width > 0 && height > 0 ? width / height : fallback;
}
