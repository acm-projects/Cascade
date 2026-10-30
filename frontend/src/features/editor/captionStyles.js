// The rules behind the Captions tab. Every value here stays inside the backend's limits
// (Captions in backend/editor/models.py), so saving never fails with a 422.

export const FONTS = ["Arial", "Georgia", "Verdana"];
export const POSITIONS = ["top", "middle", "bottom"];
export const LIMITS = { size: [12, 80], thickness: [0, 8], opacity: [0, 1] };
const MAX_TEXT = 2000; // the backend's longest caption line

// Quick color picks (the custom color input covers everything else)
export const SWATCHES = [
  { name: "White", color: "#ffffff" },
  { name: "Black", color: "#000000" },
  { name: "Yellow", color: "#ffd400" },
  { name: "Pink", color: "#ff5fa2" },
  { name: "Green", color: "#3fae4a" },
];

// One click sets several fields at once
export const PRESETS = [
  { name: "Clean", values: { color: "#ffffff", stroke: "#000000", thickness: 2, opacity: 0, bold: false } },
  { name: "Bold pop", values: { color: "#ffd400", stroke: "#000000", thickness: 3, opacity: 0, bold: true } },
  { name: "Boxed", values: { color: "#ffffff", background: "#000000", thickness: 0, opacity: 0.6, bold: false } },
];

export function applyPreset(captions, preset) {
  return { ...captions, ...preset.values };
}

// Is this preset what the captions look like right now? (to highlight its button)
export function presetMatches(captions, preset) {
  return Object.entries(preset.values).every(([field, value]) => captions[field] === value);
}

// Keep a slider value inside the backend's range
export function clampField(field, value) {
  const [low, high] = LIMITS[field];
  return Math.min(high, Math.max(low, Number(value)));
}

// The words shown for caption line `index`: your edit if there is one, otherwise the transcript's
export function cueText(texts, cues, index) {
  return texts?.[String(index)] ?? cues[index].text;
}

// Change the words of ONE line (the backend stores edits as texts["<line number>"])
export function setCueText(texts, index, text) {
  return { ...texts, [String(index)]: text.slice(0, MAX_TEXT) };
}

// Undo your edit for one line, going back to the transcript's words
export function resetCueText(texts, index) {
  const next = { ...texts };
  delete next[String(index)];
  return next;
}
