import { useState } from "react";

// Which Editor layout to show:
//   "classic" - the original three columns (clip list | video + timeline | tab pills)
//   "revamp"  - the Figma "Editor Page – Revamp" mockup (tool rail | panel | dark stage, timeline underneath)
// The switch button in the bottom-left corner flips it; the choice is remembered in this browser.
// To pick a different default for everyone, change DEFAULT_LAYOUT.
export const DEFAULT_LAYOUT = "revamp";
const STORAGE_KEY = "cascade.editorLayout";

function readSaved() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "classic" || saved === "revamp" ? saved : DEFAULT_LAYOUT;
  } catch {
    return DEFAULT_LAYOUT;
  }
}

export default function useEditorLayout() {
  const [layout, setLayout] = useState(readSaved);

  function toggle() {
    const next = layout === "revamp" ? "classic" : "revamp";
    setLayout(next);
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* private window: just don't remember it */ }
  }

  return [layout, toggle];
}
