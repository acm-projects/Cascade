const MIN = 0.05;
const clamp = (n, low, high) => Math.max(low, Math.min(high, n));
const round = (n) => Math.round(n * 10000) / 10000;

export function validateBroll(segments, duration) {
  if (segments.length > 30) throw new Error("Use at most 30 B-roll segments.");
  const ids = new Set();
  let end = 0;
  for (const item of [...segments].sort((a, b) => a.start - b.start)) {
    if (ids.has(item.id)) throw new Error("B-roll IDs must be unique.");
    ids.add(item.id);
    if (![item.start, item.duration, item.offset, item.asset.duration].every(Number.isFinite) ||
        item.start < 0 || item.offset < 0 || item.duration < MIN ||
        item.start + item.duration > duration + 1e-6 || item.offset + item.duration > item.asset.duration + 1e-6) {
      throw new Error("B-roll must fit inside the clip and available stock footage.");
    }
    if (item.start < end - 1e-6) throw new Error("B-roll cannot overlap. Choose an empty part of the timeline.");
    end = item.start + item.duration;
  }
  return segments;
}

export function insertBroll(state, asset, playhead, id) {
  const segments = state.broll || [];
  const start = clamp(Number.isFinite(playhead) ? playhead : state.start, state.start, state.end);
  if (segments.some(s => s.start <= start && start < s.start + s.duration)) {
    throw new Error("B-roll cannot overlap. Choose an empty part of the timeline.");
  }
  const next = Math.min(state.end, ...segments.filter(s => s.start > start).map(s => s.start));
  const duration = Math.min(3, asset.duration, next - start);
  if (duration < MIN) throw new Error("Move the playhead earlier to leave room for B-roll.");
  const segment = { id, asset, start, duration, offset: 0, mode: "fill" };
  return { ...state, broll: [...segments, segment] };
}

export function updateBroll(state, id, changes, duration) {
  const broll = (state.broll || []).map(s => s.id === id ? { ...s, ...changes } : s);
  validateBroll(broll, duration);
  return { ...state, broll };
}

// Pointer moves are clamped to the original segment's free gap and stock range.
export function dragBroll(segment, kind, delta, segments, duration) {
  const others = segments.filter(s => s.id !== segment.id);
  const before = Math.max(0, ...others.filter(s => s.start + s.duration <= segment.start + 1e-6).map(s => s.start + s.duration));
  const after = Math.min(duration, ...others.filter(s => s.start >= segment.start + segment.duration - 1e-6).map(s => s.start));
  if (kind === "move") return { ...segment, start: round(clamp(segment.start + delta, before, after - segment.duration)) };
  if (kind === "start") {
    const start = clamp(segment.start + delta, Math.max(before, segment.start - segment.offset), segment.start + segment.duration - MIN);
    return { ...segment, start: round(start), duration: round(segment.start + segment.duration - start), offset: round(segment.offset + start - segment.start) };
  }
  return { ...segment, duration: round(clamp(segment.duration + delta, MIN, Math.min(after - segment.start, segment.asset.duration - segment.offset))) };
}
