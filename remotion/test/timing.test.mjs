import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { beatFrames, totalFrames, transitionLength } from '../src/lib/timing.js';

const plan = JSON.parse(readFileSync(new URL('../../backend/editor/ai_edit/beats/examples/edit_plan_example.json', import.meta.url)));

test('beat frame ranges are contiguous, start at 0 and end at the total', () => {
  const frames = beatFrames(plan, 60);
  assert.equal(frames[0].from, 0);
  frames.slice(1).forEach((f, i) => assert.equal(f.from, frames[i].to));
  assert.equal(frames.at(-1).to, totalFrames(plan, 60));
  assert.equal(totalFrames(plan, 60), 2680);           // 44.66 s at 60 fps
  for (const [f, beat] of frames.map((f, i) => [f, plan.beats[i]]))
    assert.ok(Math.abs(f.from / 60 - (beat.start - 27.12)) <= 0.5 / 60);   // within half a frame of the plan
});

test('transitions never take more than a third of a beat', () => {
  assert.equal(transitionLength('whip_pan', 120), 12);
  assert.equal(transitionLength('fade', 30), 10);
  assert.equal(transitionLength('none', 120), 0);
});
