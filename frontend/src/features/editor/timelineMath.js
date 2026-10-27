// Small maths for the Editor timeline: converting between seconds and pixels, and keeping the trim valid.
// Kept separate from Timeline.jsx so it can be unit tested (timelineMath.test.js, run with `npm test`).

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

/** Seconds -> pixels across a track `width` px wide showing `duration` seconds. */
export function timeToX(t, duration, width) {
  if (!(duration > 0) || !(width > 0)) return 0;
  return (clamp(t, 0, duration) / duration) * width;
}

/** Pixels -> seconds (the opposite of timeToX). Clicks outside the track snap to its ends. */
export function xToTime(x, duration, width) {
  if (!(duration > 0) || !(width > 0)) return 0;
  return clamp(x / width, 0, 1) * duration;
}

/** The shortest trim allowed: 1 s, but never more than half of a very short clip. */
export function minLength(duration, wanted = 1) {
  return Math.min(wanted, duration / 2);
}

/** Make any { start, end } valid: inside the clip and at least the minimum length. Keeps start if it can. */
export function clampTrim(start, end, duration, minLen = minLength(duration)) {
  const safeStart = clamp(start, 0, duration - minLen);
  const safeEnd = clamp(end, safeStart + minLen, duration);
  return { start: safeStart, end: safeEnd };
}

/** Drag the START handle to `t`: it can't go below 0 or closer than minLen to the end. */
export function moveStart(t, end, duration, minLen = minLength(duration)) {
  return clamp(t, 0, end - minLen);
}

/** Drag the END handle to `t`: it can't go past the clip or closer than minLen to the start. */
export function moveEnd(t, start, duration, minLen = minLength(duration)) {
  return clamp(t, start + minLen, duration);
}

/** Ruler spacing: the smallest "nice" step that gives at most ~10 labels (e.g. 30 s clip -> every 5 s). */
export function rulerStep(duration) {
  const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  return steps.find((step) => duration / step <= 10) ?? steps[steps.length - 1];
}

/** The times to label on the ruler: 0, step, 2*step... up to the end of the clip. */
export function rulerTicks(duration) {
  const step = rulerStep(duration);
  const ticks = [];
  for (let t = 0; t <= duration + 1e-9; t += step) ticks.push(Math.round(t * 1000) / 1000);
  return ticks;
}
