import { test } from "node:test";
import assert from "node:assert/strict";
import { exportTree } from "./exportTree.js";

const clip = (studioSession, waveId, n) => ({ studioSession, waveId, wavePrompt: `prompt ${waveId}`, clip_index: n });

test("groups clips by session, then wave, keeping their order", () => {
  const tree = exportTree([clip("Funny", "a", 0), clip("Funny", "a", 1), clip("Sad", "b", 0), clip("Funny", "c", 0)]);
  assert.deepEqual(tree.map((s) => s.name), ["Funny", "Sad"]);
  assert.deepEqual(tree[0].waves.map((w) => [w.name, w.prompt, w.clips.length]), [["Wave 1", "prompt a", 2], ["Wave 2", "prompt c", 1]]);
  assert.equal(tree[1].waves[0].name, "Wave 1");
});

test("clips without a session name go in Main session", () => {
  assert.equal(exportTree([clip(undefined, "a", 0)])[0].name, "Main session");
});

test("no clips gives an empty list", () => {
  assert.deepEqual(exportTree([]), []);
});

test("independent sessions with the same editable name keep their own waves", () => {
  const tree = exportTree([
    { ...clip("My session", "a", 0), studioSessionId: "first" },
    { ...clip("My session", "b", 0), studioSessionId: "second" },
  ]);
  assert.equal(tree.length, 2);
  assert.deepEqual(tree.map(s => [s.id, s.waves[0].id]), [["first", "a"], ["second", "b"]]);
});
