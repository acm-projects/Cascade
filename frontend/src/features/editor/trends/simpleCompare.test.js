import test from 'node:test';
import assert from 'node:assert/strict';
import { askPrompt, compareRows, differences, firstCut } from './simpleCompare.js';

const edit = { duration: 44, span: 44, cuts: [4, 10, 20], avgShot: 11, width: 1284, height: 704 };
const refs = [
  { duration: 30, span: 30, cuts: [1, 2, 3, 4, 5, 6], avgShot: 30 / 7, width: 1080, height: 1920 },
  { duration: 40, span: 40, cuts: [1.5, 3], avgShot: 40 / 3, width: 1080, height: 1920 },
];

test('rows say in plain words where the edit is behind the top videos', () => {
  const rows = compareRows(edit, refs, 44);
  assert.deepEqual(rows.map(r => [r.key, r.yours, r.theirs, r.verdict]), [
    ['hook', '4 s', '1.3 s', 'Slower start'],
    ['pace', '11 s', '8.8 s', 'On par'],
    ['length', '44 s', '35 s', 'On par'],
    ['shape', 'Horizontal', 'Vertical', 'Different shape'],
  ]);
  assert.ok(rows.every(r => r.tip));
  assert.deepEqual(compareRows(null, [], null), []);
});

test('each trending video gets at most 3 short differences', () => {
  const lines = differences({ observed_tags: { hook_style: 'A bold question on screen in the first second' } }, refs[0], edit);
  assert.equal(lines.length, 3);
  assert.match(lines[0], /Changes the picture after 1 s; yours waits 4 s/);
  assert.match(lines[1], /Cuts about 3× faster/);
  assert.match(lines[2], /Vertical video; yours is horizontal/);
  assert.match(differences({}, { avgShot: 4, duration: 40 }, { avgShot: 6.4, duration: 44 })[0], /^Cuts a bit faster/);
  assert.equal(firstCut({ cuts: [], span: 9 }), 9);
});

test('suggestions become requests the AI Editor understands', () => {
  assert.match(askPrompt({ technique: 'hook' }), /hook punchier/);
  assert.equal(askPrompt({ technique: 'other', title: 'Add a title card', shortText: 'Put the topic on screen first. Then cut in.' }), 'Add a title card: Put the topic on screen first.');
});
