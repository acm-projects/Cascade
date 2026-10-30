// The small calculations behind the Editor's preview player (ClipPlayer.jsx).

// The biggest frame of a given shape (width / height) that fits the available space
export function frameSize(space, ratio) {
  if (!(ratio > 0) || !(space.width > 0) || !(space.height > 0)) return { width: 0, height: 0 };
  const width = Math.min(space.width, space.height * ratio);
  return { width, height: width / ratio };
}

// Which caption line is on screen at time t (-1 if none). A line shows from its start up to, not including, its end.
export function activeCueIndex(cues, t) {
  return cues.findIndex((cue) => cue.start <= t && t < cue.end);
}

// The draft's effects as a CSS filter, the same way the old editor previewed them
// (the backend renders the real effect on Export). No effects -> "none".
export function effectsFilter(effects) {
  if (!effects) return "none";
  const { brightness = 1, contrast = 1, saturation = 1, grayscale = false } = effects;
  if (brightness === 1 && contrast === 1 && saturation === 1 && !grayscale) return "none";
  return `brightness(${brightness}) contrast(${contrast}) saturate(${saturation}) grayscale(${grayscale ? 1 : 0})`;
}
