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

// Dragging a cropped (Fill) video inside its frame: the new framing x/y (0-1) after moving the
// pointer dx, dy pixels from where the drag started. Dragging right shows more of the left side.
//   start - { x, y } when the drag began ; frame - the frame's size ; video - the video's own size
export function dragFraming(start, dx, dy, frame, video) {
  if (!(video.width > 0) || !(video.height > 0)) return start;
  const scale = Math.max(frame.width / video.width, frame.height / video.height);
  const extraX = video.width * scale - frame.width;   // how much of the video is cut off sideways
  const extraY = video.height * scale - frame.height; // ... and top/bottom
  const move = (value, delta, extra) =>
    extra > 0.5 ? Math.round(Math.min(1, Math.max(0, value - delta / extra)) * 1000) / 1000 : value;
  return { x: move(start.x, dx, extraX), y: move(start.y, dy, extraY) };
}
