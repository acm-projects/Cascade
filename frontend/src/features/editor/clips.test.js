import test from "node:test";
import assert from "node:assert/strict";
import { combinable, flattenClips } from "./clips.js";

test("picked clips carry their job kind and combined edits are not combined again", () => {
  const index = { sessions: [
    { job_id: "g1", kind: "generation", session_name: "Main", clips: [{ job_id: "g1", clip_index: 0 }, { job_id: "g1", clip_index: 2 }] },
    { job_id: "c1", kind: "combined", clips: [{ job_id: "c1", clip_index: 0 }] },
  ] };
  const clips = flattenClips(index);
  assert.deepEqual(clips.map((c) => c.kind), ["generation", "generation", "combined"]);
  assert.deepEqual(combinable(clips).map((c) => `${c.job_id}:${c.clip_index}`), ["g1:0", "g1:2"]);
  assert.deepEqual(combinable(null), []);
});
