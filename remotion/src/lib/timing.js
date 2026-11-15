// Frame math shared by the composition and mirrored exactly in backend/editor/ai_edit/beats/render.py
// (frames_for). A beat covers frames [from, to) of the edit; frame 0 is the plan's source_window.start.

/** @param {number} seconds @param {number} fps */
export const toFrame = (seconds, fps) => Math.round(seconds * fps + 1e-6);

/** Every beat's frame range. Ranges are contiguous: beat k ends exactly where beat k+1 starts. */
export function beatFrames(plan, fps) {
  const origin = plan.source_window.start;
  return plan.beats.map(beat => ({ id: beat.id, from: toFrame(beat.start - origin, fps), to: toFrame(beat.end - origin, fps) }));
}

export const totalFrames = (plan, fps) => toFrame(plan.source_window.end - plan.source_window.start, fps);

/** Frames the transition into a beat overlaps the previous beat (never more than a third of the beat). */
export const TRANSITION_FRAMES = { whip_pan: 12, zoom_blur: 12, glitch: 9, flash_cut: 8, slide: 12, fade: 14 };
export function transitionLength(name, beatLength) {
  return Math.max(0, Math.min(TRANSITION_FRAMES[name] ?? 0, Math.floor(beatLength / 3)));
}
