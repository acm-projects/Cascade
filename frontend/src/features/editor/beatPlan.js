// The AI Editor's beat plan as rows for the compact list: time in the edit, on-screen text, style.

const STYLE_NAMES = {
  KINETIC_KEYWORD: "Kinetic keyword",
  TEXT_BEHIND_SUBJECT: "Text behind speaker",
  NUMBER_COUNTER: "Number counter",
  MAP_CALLOUT: "Map callout",
  BROLL_OVERLAY: "B-roll overlay",
  SCREENSHOT_CALLOUT: "Screenshot callout",
  SCRIBBLE_HIGHLIGHT: "Scribble highlight",
  COLLAGE: "Collage",
  SPEAKER_CUTOUT_ICONS: "Speaker cutout + icons",
  PLAIN_SPEAKER: "Speaker",
};

export const styleName = template => STYLE_NAMES[template] || template;

/** 83.4 -> "1:23.4" */
export function clockTime(seconds) {
  const tenths = Math.max(0, Math.round(seconds * 10));
  const minutes = Math.floor(tenths / 600);
  const rest = (tenths - minutes * 600) / 10;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

/** Rows for the list. Times are measured from the start of the edit, not the source clip. */
export function beatRows(plan, changedIds = []) {
  if (!plan?.beats?.length) return [];
  const origin = plan.source_window?.start ?? plan.beats[0].start;
  const changed = new Set(changedIds);
  return plan.beats.map(beat => ({
    id: beat.id,
    time: clockTime(beat.start - origin),
    length: `${(beat.end - beat.start).toFixed(1)}s`,
    text: beat.emphasis_text || "",
    accent: beat.accent_word || "",
    spoken: beat.spoken_text || "(pause)",
    style: styleName(beat.template),
    color: beat.semantic_color || "white",
    changed: changed.has(beat.id),
  }));
}
