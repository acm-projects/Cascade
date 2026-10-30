import { test } from "node:test";
import assert from "node:assert/strict";
import { activeCueIndex, effectsFilter, frameSize } from "./playerMath.js";

test("a 9:16 frame in a wide space is limited by the height", () => {
  assert.deepEqual(frameSize({ width: 1000, height: 400 }, 9 / 16), { width: 225, height: 400 });
});

test("a 16:9 frame in a tall space is limited by the width", () => {
  assert.deepEqual(frameSize({ width: 320, height: 1000 }, 16 / 9), { width: 320, height: 180 });
});

test("frameSize is safe before the space has been measured", () => {
  assert.deepEqual(frameSize({ width: 0, height: 0 }, 1), { width: 0, height: 0 });
  assert.deepEqual(frameSize({ width: 100, height: 100 }, NaN), { width: 0, height: 0 });
});

test("activeCueIndex picks the right line at the edges", () => {
  const cues = [{ start: 0, end: 2 }, { start: 2, end: 4 }, { start: 5, end: 6 }];
  assert.equal(activeCueIndex(cues, 0), 0);
  assert.equal(activeCueIndex(cues, 1.99), 0);
  assert.equal(activeCueIndex(cues, 2), 1); // the end belongs to the next line
  assert.equal(activeCueIndex(cues, 4.5), -1); // a gap between lines
  assert.equal(activeCueIndex(cues, 6), -1);
  assert.equal(activeCueIndex([], 1), -1);
});

test("effectsFilter is 'none' when nothing is changed", () => {
  assert.equal(effectsFilter(undefined), "none");
  assert.equal(effectsFilter({ brightness: 1, contrast: 1, saturation: 1, grayscale: false }), "none");
});

test("effectsFilter turns the draft's effects into a CSS filter", () => {
  assert.equal(
    effectsFilter({ brightness: 1.2, contrast: 0.8, saturation: 1, grayscale: true }),
    "brightness(1.2) contrast(0.8) saturate(1) grayscale(1)",
  );
});
