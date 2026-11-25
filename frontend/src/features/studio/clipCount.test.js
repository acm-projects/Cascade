import test from 'node:test';
import assert from 'node:assert/strict';
import { requestedClipCount } from './clipCount.js';

test('explicit chat counts override the selector, including larger batches and words', () => {
  for (const [prompt,count] of [['Find 10 funny clips',10],['give me ten clips',10],
    ['generate twenty-five clips',25],['I want 1 clip',1],['output of 20 clips',20],
    ['I asked for 2 clips, you only gave me one',2],['10 clips about science',10]]) {
    // Adjectives between the count and "clips" are also common requests.
    assert.equal(requestedClipCount(prompt,4),count,prompt);
  }
});
test('reference numbers and source durations do not override the chosen output count', () => {
  for (const prompt of ['combine these 2 clips', 'mix clips 4 and 5', 'funny moments from a 10 minute video'])
    assert.equal(requestedClipCount(prompt,12),12);
});
test('invalid counts are explained instead of silently clamped', () => {
  for (const prompt of ['find 0 clips','generate 51 clips'])
    assert.throws(()=>requestedClipCount(prompt,4),/between 1 and 50/);
});

import { requestedClipLength } from './clipCount.js';
test('clip length comes from the prompt: short moments, explicit seconds, or the default', () => {
  for (const [prompt, length] of [
    ['find me 4 funniest nostalgic friendship clips', 30],
    ['find 4 short funny clips', 5],
    ['quick moments of us laughing', 5],
    ['4 clips, each around 5 or 6 seconds', 5],
    ['clips of 1-6 seconds so the edit is 10-15 seconds', 5],
    ['give me 15 second clips', 15],
    ['30s clips', 30],
    ['find 3 clips of 45 seconds', 60],
    ['make YouTube shorts clips', 30],
  ]) assert.equal(requestedClipLength(prompt), length, prompt);
});
