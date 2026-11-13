import test from 'node:test';
import assert from 'node:assert/strict';
import { viewData, clipTime, problemText, referenceLearning, youtubeUrl, concise } from './trendsView.js';
const state = { start: 5, end: 20, timeline: [{ start: 10, end: 20 }] };
test('No reference plots or missing reference traits leak into clip opportunities', () => {
  const data = viewData({ result: { summary: 'Your clip has no dialogue.', strengths: ['A clear reveal.', 'a clear reveal!', 'Short framing.', 'Good contrast.', 'Extra.'], comparison: { missing_traits: ['topics: unrelated reference plot'] }, references: [{ id: 'abcdefghijk', kind: 'example' }], suggestions: [{ technique: 'punch_in', at: 12, text: 'Emphasize the reveal.', reason: 'Focus attention.', source_ids: ['abcdefghijk', 'invented'] }, { technique: 'punch_in', at: 12, text: 'Same effect again.', source_ids: [] }] } }, state, { has_audio: true, cues: [] });
  assert.equal(data.strengths.length, 3); assert.equal(data.suggestions.length, 1);
  assert.deepEqual(data.suggestions[0].source_ids, ['abcdefghijk']); assert.match(data.summary, /uncertain/);
  assert.doesNotMatch(data.summary, /has no dialogue|unrelated reference plot/);
});
test('Time is current edited clip time; a moment that was not located or is outside the clip shows no time', () => {
  assert.equal(clipTime({ at: 12 }, state), 'at 0:02');
  assert.equal(clipTime({ at: null, technique: 'punch_in' }, state), '');
  assert.equal(clipTime({ at: 30, technique: 'punch_in' }, state), '');
  assert.equal(clipTime({ at: null, technique: 'captions' }, state), 'Whole clip');
  const data = viewData({ result: { suggestions: [{ technique: 'freeze', at: 12 }, { technique: 'captions', at: null }] } }, state, { cues: [] });
  assert.equal(data.suggestions[0].title, 'Review this technique'); assert.match(data.summary, /No YouTube videos/);
});
test('Findings keep the planner priority order and failures read in plain words', () => {
  const data = viewData({ result: { references: [{ id: 'abcdefghijk', kind: 'example' }], observed_patterns: [{ trait: 'visual style: quick cuts', count: 2, examples: 2 }], suggestions: [{ technique: 'captions', at: null, executable: false }, { technique: 'music', at: null, title: 'Let the ending breathe' }] } }, state, { cues: [] });
  assert.deepEqual(data.suggestions.map(s => s.technique), ['captions', 'music']);
  assert.equal(data.suggestions[0].title, 'Make the words easier to follow'); assert.equal(data.suggestions[1].title, 'Let the ending breathe');
  assert.deepEqual(data.patterns, ['Visual style: quick cuts (both examples)']);
  assert.match(problemText('No YouTube references analyzed. ai_tagging: rate_limited'), /usage limit/);
  assert.match(problemText('No YouTube references analyzed. download: download_failed'), /No YouTube videos/);
  assert.doesNotMatch(problemText('ai_clip_analysis: ai_failed — raw provider text'), /ai_failed|provider/);
});
test('Reference learning excludes plot topics, missing metrics stay missing and URLs require real IDs', () => {
  assert.deepEqual(referenceLearning({ observed_tags: { topics: ['plot'], visual_style: ['Quick cuts', 'quick cuts!'] } }), ['Visuals: Quick cuts']);
  assert.equal(youtubeUrl({ id: '../../invalid' }), null); assert.equal(youtubeUrl({ id: 'abcdefghijk' }), 'https://www.youtube.com/watch?v=abcdefghijk');
  assert.ok(concise('Long text. '.repeat(100)).length <= 220);
  assert.match(concise('Start with “emphasize the reaction.” Then review it.'), /emphasize the reaction/);
});
