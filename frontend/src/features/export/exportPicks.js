// Which clips the Editor sends to Export. The picker (ExportPicker.jsx) saves the keys here and in the page change,
// so a reload of the Export page keeps the same clips. The browser tab forgets them when it closes.
import { clipKey } from "../editor/clips.js";

const storageKey = (projectId) => `cascade.exportPicks.${projectId}`;

/** Clips ticked when the picker opens: every edited clip plus the one on screen (or just that one). */
export function defaultPicks(clips, currentKey) {
  const keys = clips.filter((clip) => clip.edited).map(clipKey);
  if (currentKey && clips.some((clip) => clipKey(clip) === currentKey) && !keys.includes(currentKey)) keys.unshift(currentKey);
  return keys.length ? keys : clips.slice(0, 1).map(clipKey);
}

export function savePicks(projectId, keys) {
  try { sessionStorage.setItem(storageKey(projectId), JSON.stringify(keys)); } catch { /* private mode: the page change still carries them */ }
}

export function loadPicks(projectId) {
  try {
    const keys = JSON.parse(sessionStorage.getItem(storageKey(projectId)) || "null");
    return Array.isArray(keys) && keys.every((key) => typeof key === "string") ? keys : null;
  } catch { return null; }
}

/** The clips Export shows: the picked ones, in project order. Unknown or no picks = every clip. */
export function pickedClips(clips, keys) {
  if (!keys?.length) return clips;
  const chosen = clips.filter((clip) => keys.includes(clipKey(clip)));
  return chosen.length ? chosen : clips;
}
