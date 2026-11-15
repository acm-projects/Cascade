import test from 'node:test';
import assert from 'node:assert/strict';
import { sameEdit, canUndoAI, isAIUndo } from './editorTransactions.js';

test('AI response and undo guards accept equal snapshots but reject newer manual edits', () => {
  const before={start:0,end:10,motion:[]};
  const after={...before,motion:[{start:3,shake:.004}]};
  assert.ok(sameEdit(after,structuredClone(after)));
  assert.ok(canUndoAI({before,after},structuredClone(after)));
  assert.equal(canUndoAI({before,after},{...after,start:1}),false);
  assert.equal(canUndoAI(null,after),false);
});
test('only explicit AI undo commands consume the AI transaction', () => {
  assert.ok(isAIUndo('Undo your last edit'));
  assert.ok(isAIUndo('Please undo the last AI edit.'));
  assert.equal(isAIUndo('Undo the manual trim and add music'),false);
});
