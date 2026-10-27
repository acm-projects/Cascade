import test from "node:test";
import assert from "node:assert/strict";
import { clampTrim, minLength, moveEnd, moveStart, rulerStep, rulerTicks, timeToX, xToTime } from "./timelineMath.js";

// Run with: npm test

test("seconds and pixels convert both ways", () => {
  assert.equal(timeToX(15, 30, 600), 300);   // halfway through a 30 s clip on a 600 px track
  assert.equal(xToTime(300, 30, 600), 15);
  assert.equal(xToTime(timeToX(7.5, 30, 600), 30, 600), 7.5);
});

test("times and clicks outside the track snap to its ends", () => {
  assert.equal(timeToX(-5, 30, 600), 0);
  assert.equal(timeToX(99, 30, 600), 600);
  assert.equal(xToTime(-40, 30, 600), 0);
  assert.equal(xToTime(900, 30, 600), 30);
});

test("an empty track or clip never divides by zero", () => {
  assert.equal(timeToX(5, 0, 600), 0);
  assert.equal(xToTime(100, 30, 0), 0);
});

test("the minimum trim is 1 s, or half of a very short clip", () => {
  assert.equal(minLength(30), 1);
  assert.equal(minLength(1), 0.5);
});

test("dragging the start handle stops 1 s before the end and at 0", () => {
  assert.equal(moveStart(12, 20, 30), 12);
  assert.equal(moveStart(19.8, 20, 30), 19);
  assert.equal(moveStart(-3, 20, 30), 0);
});

test("dragging the end handle stops 1 s after the start and at the clip's end", () => {
  assert.equal(moveEnd(25, 10, 30), 25);
  assert.equal(moveEnd(10.2, 10, 30), 11);
  assert.equal(moveEnd(45, 10, 30), 30);
});

test("clampTrim repairs any trim", () => {
  assert.deepEqual(clampTrim(5, 20, 30), { start: 5, end: 20 });
  assert.deepEqual(clampTrim(-2, 40, 30), { start: 0, end: 30 });
  assert.deepEqual(clampTrim(20, 20.2, 30), { start: 20, end: 21 });   // too short: end moves
  assert.deepEqual(clampTrim(29.8, 30, 30), { start: 29, end: 30 });   // start too late: start moves
});

test("the ruler picks a readable spacing", () => {
  assert.equal(rulerStep(30), 5);
  assert.equal(rulerStep(8), 1);
  assert.equal(rulerStep(1), 0.1);
  assert.equal(rulerStep(600), 60);
  assert.deepEqual(rulerTicks(10), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.deepEqual(rulerTicks(12), [0, 2, 4, 6, 8, 10, 12]);
});
