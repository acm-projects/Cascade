// Identical piecewise clock to backend/editor/retiming.py. All editable events use source time.
export function timelineClock(state) {
  const spans = state.timeline?.length ? state.timeline : [{ start: state.start, end: state.end }];
  const pieces = []; let duration = 0;
  for (const span of spans) {
    const left = Math.max(state.start, span.start), right = Math.min(state.end, span.end);
    if (right <= left) continue;
    const boundaries = new Set([left, right]);
    for (const ramp of state.speed || []) for (let i = 0; i <= 8; i++) {
      const t = ramp.start + (ramp.end - ramp.start) * i / 8;
      if (left < t && t < right) boundaries.add(t);
    }
    const points = [...boundaries].sort((a, b) => a - b);
    for (let i = 0; i < points.length - 1; i++) {
      const start = points[i], end = points[i + 1], mid = (start + end) / 2;
      const ramp = (state.speed || []).find(r => r.start <= mid && mid < r.end);
      const rate = ramp ? ramp.rate_from + (ramp.rate_to - ramp.rate_from) * (mid - ramp.start) / (ramp.end - ramp.start) : 1;
      pieces.push({ start, end, rate, out: duration }); duration += (end - start) / rate;
    }
  }
  return { duration,
    output(t) { return pieces.reduce((sum, p) => sum + Math.max(0, Math.min(p.end - p.start, t - p.start)) / p.rate, 0); },
    source(t) { const p = pieces.find(p => t < p.out + (p.end - p.start) / p.rate - 1e-8); return p ? p.start + Math.max(0, t - p.out) * p.rate : pieces.at(-1)?.end || 0; },
  };
}
