// Identical piecewise clock to backend/editor/retiming.py. All editable events use source time.
export function timelineClock(state) {
  if (state.fablecut) {
    const base = timelineClock({ ...state, fablecut: null });
    const parts = []; let duration = 0;
    for (const shot of state.fablecut.shots) {
      const a = Math.max(state.start, shot.start), b = Math.min(state.end, shot.end);
      const input = base.output(a), consumed = base.output(b) - input;
      if (b <= a || consumed < .05) continue;
      const length = 2 * consumed / (shot.rate_from + shot.rate_to);
      parts.push({ shot, a, b, input, out: duration, length }); duration += length;
    }
    const consumedAt = (p, dt) => p.shot.rate_from * dt + (p.shot.rate_to - p.shot.rate_from) * dt * dt / (2 * p.length);
    return { duration,
      output(t) {
        const p = parts.find(v => t >= v.a && t < v.b) || parts.at(-1);
        if (!p) return 0;
        const target = Math.max(0, Math.min(base.output(t) - p.input, consumedAt(p, p.length)));
        let lo = 0, hi = p.length;
        for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; if (consumedAt(p, mid) < target) lo = mid; else hi = mid; }
        return p.out + (lo + hi) / 2;
      },
      source(t) { const p = parts.find(v => t < v.out + v.length - 1e-8) || parts.at(-1); return p ? base.source(p.input + consumedAt(p, Math.max(0, Math.min(p.length, t - p.out)))) : state.start; },
    };
  }
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
