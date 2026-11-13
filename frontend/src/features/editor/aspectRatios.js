// The frame shapes the Editor offers, named for where people watch. Every id is a ratio the backend accepts
// (Composition.ratio in backend/editor/models.py) except "original", which keeps the clip's own shape.
export const PRESETS = [
  { id: "9:16", label: "iPhone", hint: "Reels · TikTok · Shorts", w: 9, h: 16 },
  { id: "16:9", label: "TV", hint: "YouTube · widescreen", w: 16, h: 9 },
  { id: "16:10", label: "Desktop", hint: "Laptop · monitor", w: 16, h: 10 },
  { id: "4:5", label: "Instagram", hint: "Portrait feed", w: 4, h: 5 },
  { id: "1:1", label: "Square", hint: "Feed · profile", w: 1, h: 1 },
  { id: "4:3", label: "iPad", hint: "Classic · tablet", w: 4, h: 3 },
  { id: "21:9", label: "Ultrawide", hint: "Cinema bars", w: 21, h: 9 },
  { id: "original", label: "Original", hint: "Exactly the clip's shape", w: null, h: null },
];

/** "16:10" -> 1.6. "original" (or anything unknown) -> the fallback, usually the clip's own width / height. */
export function ratioOf(id, fallback = 16 / 9) {
  const [w, h] = String(id || "").split(":").map(Number);
  return w > 0 && h > 0 ? w / h : fallback;
}
