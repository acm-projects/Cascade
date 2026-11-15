import { interpolate } from 'remotion';
import { clamp, easeOut } from '../lib/motion';

/** A hand-drawn double ellipse around a w x h box, revealed like a pen stroke from `delay` over `frames`. */
export function ScribbleEllipse({ w, h, color, frame, delay = 5, frames = 16, width = 5 }:
  { w: number; h: number; color: string; frame: number; delay?: number; frames?: number; width?: number }) {
  const p = interpolate(frame - delay, [0, frames], [0, 1], { ...clamp, easing: easeOut });
  const rx = w / 2 + w * 0.08, ry = h / 2 + h * 0.28, cx = w / 2, cy = h / 2;
  // two slightly different loops, like a marker going round twice
  const loop = (k: number, wobble: number) => {
    const pts = Array.from({ length: 41 }, (_, i) => {
      const a = (i / 40) * Math.PI * 2 - Math.PI * 0.9 + k;
      return [cx + Math.cos(a) * rx * (1 + wobble * Math.sin(a * 3)), cy + Math.sin(a) * ry * (1 + wobble * Math.cos(a * 2))];
    });
    return 'M' + pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L');
  };
  const length = 2 * Math.PI * Math.sqrt((rx * rx + ry * ry) / 2) * 1.05;
  return <svg width={w} height={h} style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible', filter: `drop-shadow(0 0 8px ${color})` }}>
    {[[0, 0.03], [0.25, -0.025]].map(([k, wobble], i) => <path key={i} d={loop(k, wobble)} fill="none" stroke={color} strokeWidth={width - i}
      strokeLinecap="round" strokeDasharray={length} strokeDashoffset={length * (1 - Math.max(0, Math.min(1, p * 1.9 - i * 0.9)))} />)}
  </svg>;
}

/** A hand-drawn strike-through or underline across a w-wide line of text. */
export function ScribbleLine({ w, y, color, frame, delay = 10, frames = 8, width = 4 }:
  { w: number; y: number; color: string; frame: number; delay?: number; frames?: number; width?: number }) {
  const p = interpolate(frame - delay, [0, frames], [0, 1], { ...clamp, easing: easeOut });
  const d = `M${-w * 0.03},${y + 3} C${w * 0.3},${y - 4} ${w * 0.6},${y + 6} ${w * 1.04},${y - 2}`;
  return <svg width={w} height={y + 20} style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible' }}>
    <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - p} />
  </svg>;
}
