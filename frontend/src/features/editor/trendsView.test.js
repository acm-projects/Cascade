import test from 'node:test';
import assert from 'node:assert/strict';
import { viewData, clipTime, referenceLearning, youtubeUrl, concise } from './trendsView.js';
const state = { start: 5, end: 20, timeline: [{ start: 10, end: 20 }] };
test('No reference plots or missing reference traits leak into clip opportunities', () => {
  const data = viewData({ result: { summary: 'Your clip has no dialogue.', strengths: ['A clear reveal.', 'a clear reveal!', 'Short framing.', 'Good contrast.', 'Extra.'], comparison: { missing_traits: ['topics: unrelated reference plot'] }, references: [{ id: 'abcdefghijk', kind: 'example' }], suggestions: [{ technique: 'punch_in', at: 12, text: 'Emphasize the reveal.', reason: 'Focus attention.', source_ids: ['abcdefghijk', 'invented'] }, { technique: 'punch_in', at: 12, text: 'Same effect again.', source_ids: [] }] } }, state, { has_audio: true, cues: [] });
  assert.equal(data.strengths.length, 3); assert.equal(data.suggestions.length, 1);
  assert.deepEqual(data.suggestions[0].source_ids, ['abcdefghijk']); assert.match(data.summary, /uncertain/);
  assert.doesNotMatch(data.summary, /has no dialogue|unrelated reference plot/);
});
test('Time is current edited clip time; absent timing and unsupported techniques stay honest', () => {
  assert.equal(clipTime({ at: 12 }, state), '0:02.00 · current clip time');
  assert.equal(clipTime({ at: null, technique: 'punch_in' }, state), 'Timing not located');
  assert.ok(viewData({ result: { suggestions: [{ technique: 'punch_in', at: 6 }] } }, state, { cues: [] }).suggestions[0].unavailable.includes('removed'));
  const data = viewData({ result: { suggestions: [{ technique: 'freeze', at: 12 }, { technique: 'captions', at: null }, { technique: 'punch_in', at: null }] } }, state, { cues: [] });
  assert.ok(data.suggestions.every(s => s.unavailable)); assert.match(data.summary, /No YouTube references/);
});
test('Reference learning excludes plot topics, missing metrics stay missing and URLs require real IDs', () => {
  assert.deepEqual(referenceLearning({ observed_tags: { topics: ['plot'], visual_style: ['Quick cuts', 'quick cuts!'] } }), ['Visuals: Quick cuts']);
  assert.equal(youtubeUrl({ id: '../../invalid' }), null); assert.equal(youtubeUrl({ id: 'abcdefghijk' }), 'https://www.youtube.com/watch?v=abcdefghijk');
  assert.ok(concise('Long text. '.repeat(100)).length <= 220);
  assert.match(concise('Start with “emphasize the reaction.” Then review it.'), /emphasize the reaction/);
});
