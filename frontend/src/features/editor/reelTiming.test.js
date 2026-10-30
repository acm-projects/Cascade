import test from 'node:test';
import assert from 'node:assert/strict';
import { timelineClock } from './reelTiming.js';
test('Reel clock matches renderer eight-step ramp and inverse seeks', () => {
  const clock = timelineClock({ start: 0, end: 10, timeline: [{ start: 2, end: 10 }], speed: [{ start: 4, end: 6, rate_from: 1, rate_to: 2 }] });
  const expected = 6 + Array.from({ length: 8 }, (_, i) => .25 / (1 + (i + .5) / 8)).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(clock.duration - expected) < 1e-8);
  for (const time of [2, 3.5, 4.2, 5.1, 6, 9.9]) assert.ok(Math.abs(clock.source(clock.output(time)) - time) < 1e-8);
});
test('Removed footage never increases output time; next kept phrase starts cleanly', () => {
  const clock = timelineClock({ start: 0, end: 10, timeline: [{ start: 1, end: 3 }, { start: 5, end: 8 }], speed: [] });
  assert.equal(clock.duration, 5);
  assert.equal(clock.output(4), 2);
  assert.equal(clock.source(2), 5);
});
