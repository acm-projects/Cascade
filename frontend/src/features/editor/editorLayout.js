import { useState } from "react";

// Which Editor layout to show:
//   "classic" - the original three columns (clip list | video + timeline | tab pills)
//   "revamp"  - the Figma "Editor Page – Revamp" mockup (tool rail | panel | dark stage, timeline underneath)
//   "split"   - Abhishri's design from davebranch (video on the left, tools on the right, timeline underneath)
// The switch at the bottom of the page picks one; the choice is remembered in this browser.
// To pick a different default for everyone, change DEFAULT_LAYOUT.
export const DEFAULT_LAYOUT = "revamp";
export const LAYOUTS = [
  { id: "classic", label: "Classic" },
  { id: "revamp", label: "New" },
  { id: "split", label: "Abhishri's" },
];
const STORAGE_KEY = "cascade.editorLayout";

function readSaved() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return LAYOUTS.some((option) => option.id === saved) ? saved : DEFAULT_LAYOUT;
  } catch {
    return DEFAULT_LAYOUT;
  }
}

export default function useEditorLayout() {
  const [layout, setLayout] = useState(readSaved);

  function choose(next) {
    setLayout(next);
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* private window: just don't remember it */ }
  }

  return [layout, choose];
}
