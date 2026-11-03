import test from 'node:test';
import assert from 'node:assert/strict';
import { audioPeaks, layoutLanes, thumbnailTimes, waveformPath } from './timelineLayout.js';
import { timeToX, xToTime, moveStart, moveEnd } from './timelineMath.js';

test('filmstrip timestamps share the exact ruler scale at fit and zoom, including scroll', () => {
  const duration = 38.038;
  const times = thumbnailTimes(duration, 20);
  assert.equal(times[0], 0);
  assert.equal(times[19], duration * 19 / 20);
  for (const width of [640, 1920, 5120]) for (const time of times) {
    const scroll = 300;
    const screenX = timeToX(time, duration, width) - scroll;
    assert.ok(Math.abs(xToTime(screenX + scroll, duration, width) - time) < 1e-9);
  }
  assert.equal(moveStart(12, 20, duration), 12);
  assert.equal(moveEnd(25, 12, duration), 25);
});

test('overlapping captions get lanes while short captions keep their actual duration', () => {
  const { items, lanes } = layoutLanes([{ start: 1, duration: .02 }, { start: 1.01, duration: 2 }, { start: 3.01, duration: 1 }]);
  assert.equal(lanes, 2);
  assert.deepEqual(items.map(item => item.lane), [0, 1, 0]);
  assert.equal(items[0].duration, .02);
  assert.equal(timeToX(items[0].duration, 10, 1000), 2);
});

test('audio waveform peaks use real samples across channels, with silence staying silent', () => {
  const buffer = { numberOfChannels: 2, length: 8, getChannelData: i => i ? [0, 0, 0, 0, -.8, 0, 0, 0] : [0, 0, .5, 0, 0, 0, 0, 0] };
  assert.deepEqual(audioPeaks(buffer, 4), [0, .5, .8, 0]);
  assert.equal(waveformPath([0, 0], 2, { offset: 0, duration: 2 }, 3), 'M0,20 L1,20 L2,20 L2,20 L1,20 L0,20 Z');
});

test('audio waveform respects source offsets, source end and looping', () => {
  const peaks = [0, 1, .5, 0];
  const trimmed = waveformPath(peaks, 4, { offset: 1, duration: 1 }, 3);
  assert.ok(trimmed.startsWith('M0,3'));
  const ended = waveformPath(peaks, 4, { offset: 4, duration: 1 }, 3);
  assert.ok(ended.startsWith('M0,20'));
  const looped = waveformPath(peaks, 4, { offset: 5, duration: 1, loop: true }, 3);
  assert.equal(looped, trimmed);
});
