import { test } from "node:test";
import assert from "node:assert/strict";
import { defaultPicks, pickedClips } from "./exportPicks.js";

const clip = (n, edited = false) => ({ job_id: "j", clip_index: n, edited });

test("ticks every edited clip plus the one on screen", () => {
  assert.deepEqual(defaultPicks([clip(0), clip(1, true), clip(2, true)], "j:0"), ["j:0", "j:1", "j:2"]);
  assert.deepEqual(defaultPicks([clip(0), clip(1, true)], "j:1"), ["j:1"]);
});

test("with nothing edited and no clip on screen, ticks the first clip", () => {
  assert.deepEqual(defaultPicks([clip(0), clip(1)], null), ["j:0"]);
  assert.deepEqual(defaultPicks([], null), []);
});

test("Export shows only the picked clips, in project order, or all when the picks are unknown", () => {
  const clips = [clip(0), clip(1), clip(2)];
  assert.deepEqual(pickedClips(clips, ["j:2", "j:0"]).map((c) => c.clip_index), [0, 2]);
  assert.equal(pickedClips(clips, null), clips);
  assert.equal(pickedClips(clips, ["gone:9"]), clips);
});
