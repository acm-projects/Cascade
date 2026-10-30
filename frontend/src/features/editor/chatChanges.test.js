import { test } from "node:test";
import assert from "node:assert/strict";
import { describeChanges } from "./chatChanges.js";

const base = {
  start: 0, end: 30, texts: {}, broll: [],
  captions: { enabled: true, color: "#ffffff", size: 32, bold: false, position: "bottom", font: "Arial" },
  composition: { ratio: "original", mode: "fit" },
  reframe: { enabled: false },
};

test("no changes gives no chips", () => {
  assert.deepEqual(describeChanges(base, structuredClone(base)), []);
});

test("trim and caption color", () => {
  const after = { ...base, start: 3, captions: { ...base.captions, color: "#ffd400" } };
  assert.deepEqual(describeChanges(base, after), ["Trim 3.0–30.0 s", "Caption color: #ffd400"]);
});

test("captions off, moved to the top, bold", () => {
  const after = { ...base, captions: { ...base.captions, enabled: false, position: "top", bold: true } };
  assert.deepEqual(describeChanges(base, after), ["Captions: off", "Bold captions: on", "Caption position: top"]);
});

test("framing, text and b-roll changes", () => {
  const after = {
    ...base, texts: { 2: "hi" }, broll: [{ id: "a" }],
    composition: { ratio: "9:16", mode: "fill" }, reframe: { enabled: true },
  };
  assert.deepEqual(describeChanges(base, after),
    ["Caption text", "Frame: 9:16", "Crop to fill", "Follow speaker: on", "B-roll: 1 segment(s)"]);
});

test("missing state gives no chips", () => {
  assert.deepEqual(describeChanges(null, base), []);
});
