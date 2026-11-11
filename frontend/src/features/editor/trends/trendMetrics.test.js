import test from 'node:test';
import assert from 'node:assert/strict';
import { aspect, countWhere, editCues, editFindings, kept, measuredVideo, pacing, range, shots, speechConflicts } from './trendMetrics.js';

const base = { start: 2, end: 12, captions: { enabled: true }, timeline: [], audio: [], dialogue_volume: 1, texts: {} };
const info = { cues: [{ start: 1, end: 3, text: 'cut off' }, { start: 4, end: 6, text: 'hello there' }, { start: 13, end: 14, text: 'after the end' }] };

test('cues are placed in output time and trimmed lines drop out', () => {
  const cues = editCues(base, info);
  assert.deepEqual(cues.map(c => [c.text, c.start, c.end]), [['cut off', 0, 1], ['hello there', 2, 4]]);
});

test('timeline spans remove the gap between them', () => {
  const state = { ...base, timeline: [{ start: 2, end: 3 }, { start: 4, end: 12 }] };
  assert.equal(kept(3.5, state), false);
  assert.equal(kept(4.5, state), true);
  const cues = editCues(state, info);
  assert.equal(cues.find(c => c.text === 'hello there').start, 1); // 4s source → 1s output (the 3–4s gap is cut)
});

test('shots, pacing and measured summaries come straight from cut times', () => {
  assert.deepEqual(shots([2, 5], 8).map(s => s.length), [2, 3, 3]);
  assert.deepEqual(pacing([1, 2, 6], 12, 5).map(p => p.count), [2, 1, 0]);
  const m = measuredVideo({ duration: 30, measured_seconds: 30, cuts: [3, 9, 20], width: 1080, height: 1920 });
  assert.equal(m.avgShot, 7.5);
  assert.equal(measuredVideo(null), null);
  assert.equal(measuredVideo({ duration: 10 }).cuts, null); // not measured ≠ zero cuts
});

test('music that stays loud under speech is flagged; ducked music is not', () => {
  const loud = { ...base, audio: [{ id: 'a', track: 'music', start: 2, duration: 10, volume: .8, duck: false, duck_gain: .25 }] };
  const conflicts = speechConflicts(loud, info);
  assert.equal(conflicts.length, 2);
  assert.equal(conflicts[0].ratio, .8);
  const ducked = { ...loud, audio: [{ ...loud.audio[0], duck: true }] }; // 0.8 × 0.25 = 0.2
  assert.equal(speechConflicts(ducked, info).length, 0);
});

test('findings report unknowns as null, not zero', () => {
  const f = editFindings(base, { cues: [] }, null);
  assert.equal(f.firstWords, null);
  assert.equal(f.avgShot, null);
  assert.equal(f.captionCoverage, null);
  const g = editFindings(base, info, measuredVideo({ duration: 10, cuts: [5] }));
  assert.equal(g.firstWords, 0);
  assert.equal(g.avgShot, 5);
  assert.equal(Math.round(g.captionCoverage * 100), 30);
});

test('range, counts and aspect helpers', () => {
  assert.deepEqual(range([2, null, 4]), { min: 2, max: 4, count: 2 });
  assert.equal(range([null]), null);
  assert.deepEqual(countWhere([1, 5, null, 2], v => v <= 3), { hits: 2, of: 3 });
  assert.equal(aspect(1080, 1920), 0.5625);
  assert.equal(aspect(0, 0), 9 / 16);
});
