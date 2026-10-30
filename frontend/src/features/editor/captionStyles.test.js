import { test } from "node:test";
import assert from "node:assert/strict";
import {
  FONTS, LIMITS, POSITIONS, PRESETS, SWATCHES,
  applyPreset, clampField, cueText, presetMatches, resetCueText, setCueText,
} from "./captionStyles.js";

const defaults = {
  enabled: true, font: "Arial", size: 32, color: "#ffffff", stroke: "#000000",
  thickness: 2, background: "#000000", opacity: 0, position: "bottom", bold: false,
};
const hex = /^#[0-9a-fA-F]{6}$/;

test("presets and swatches only use values the backend accepts", () => {
  for (const { values } of PRESETS) {
    for (const field of ["color", "stroke", "background"]) {
      if (field in values) assert.match(values[field], hex);
    }
    for (const field of ["thickness", "opacity"]) {
      if (field in values) assert.equal(clampField(field, values[field]), values[field]);
    }
  }
  for (const { color } of SWATCHES) assert.match(color, hex);
  assert.deepEqual(FONTS, ["Arial", "Georgia", "Verdana"]);
  assert.deepEqual(POSITIONS, ["top", "middle", "bottom"]);
});

test("applyPreset changes the style but keeps font, size and position", () => {
  const boldPop = PRESETS.find((p) => p.name === "Bold pop");
  const result = applyPreset({ ...defaults, font: "Georgia", size: 50 }, boldPop);
  assert.equal(result.color, "#ffd400");
  assert.equal(result.bold, true);
  assert.equal(result.font, "Georgia");
  assert.equal(result.size, 50);
  assert.ok(presetMatches(result, boldPop));
  assert.ok(!presetMatches(result, PRESETS[0]));
});

test("the default captions look like the Clean preset", () => {
  assert.ok(presetMatches(defaults, PRESETS[0]));
});

test("clampField keeps sliders in range", () => {
  assert.equal(clampField("size", 5), LIMITS.size[0]);
  assert.equal(clampField("size", 200), LIMITS.size[1]);
  assert.equal(clampField("size", "40"), 40);
  assert.equal(clampField("thickness", -1), 0);
  assert.equal(clampField("opacity", 1.5), 1);
});

test("editing one caption line changes only that line", () => {
  const cues = [{ text: "hello there" }, { text: "general kenobi" }];
  const texts = setCueText({}, 1, "General Kenobi!");
  assert.deepEqual(texts, { 1: "General Kenobi!" });
  assert.equal(cueText(texts, cues, 0), "hello there");
  assert.equal(cueText(texts, cues, 1), "General Kenobi!");
  assert.equal(cueText(undefined, cues, 0), "hello there");
});

test("an empty edit is kept (it hides that line) and Reset removes the edit", () => {
  const cues = [{ text: "um" }];
  const texts = setCueText({ 0: "uh" }, 0, "");
  assert.equal(cueText(texts, cues, 0), "");
  const reset = resetCueText(texts, 0);
  assert.deepEqual(reset, {});
  assert.equal(cueText(reset, cues, 0), "um");
});

test("very long lines are cut to the backend's limit", () => {
  assert.equal(setCueText({}, 0, "x".repeat(3000))[0].length, 2000);
});
