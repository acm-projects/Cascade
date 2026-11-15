import test from 'node:test';
import assert from 'node:assert/strict';
import { beatRows, clockTime, styleName } from './beatPlan.js';

const plan = {
  source_window: { start: 27.12, end: 31.28 },
  beats: [
    { id: 1, start: 27.12, end: 28.88, spoken_text: 'I think the jungle to me is', template: 'TEXT_BEHIND_SUBJECT', emphasis_text: 'THE JUNGLE', accent_word: 'to me', semantic_color: 'white' },
    { id: 2, start: 28.88, end: 31.28, spoken_text: '', template: 'PLAIN_SPEAKER', emphasis_text: null, accent_word: null, semantic_color: 'green' },
  ],
};

test('Beat rows start at 0:00.0 for the edit, show on-screen text and a readable style, and mark changed beats', () => {
  const rows = beatRows(plan, [2]);
  assert.deepEqual(rows.map(r => [r.time, r.text, r.accent, r.style, r.changed]), [
    ['0:00.0', 'THE JUNGLE', 'to me', 'Text behind speaker', false],
    ['0:01.8', '', '', 'Speaker', true],
  ]);
  assert.equal(rows[1].spoken, '(pause)');
  assert.equal(rows[0].length, '1.8s');
});

test('Clock time and unknown styles', () => {
  assert.equal(clockTime(83.44), '1:23.4');
  assert.equal(clockTime(-1), '0:00.0');
  assert.equal(styleName('SOMETHING_NEW'), 'SOMETHING_NEW');
  assert.deepEqual(beatRows(null), []);
});
