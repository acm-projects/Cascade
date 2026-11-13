// How deep the background sea is: 0 = the normal work-page water, 1 = deep (darker, glowing, zoomed in).
// The Trends window sets 1 while it's open; every WaterFlow eases toward this value.
let target = 0;

export function setSeaDepth(value) {
  target = Math.max(0, Math.min(1, value));
}

export function seaDepthTarget() {
  return target;
}
