import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop } from '../components/Backdrop';
import { Media } from '../components/Media';
import { Accent, Keyword, fit } from '../components/Words';
import { useBeat } from '../lib/context';
import { clamp, easeOut } from '../lib/motion';
import { color } from '../lib/style';

// Card positions (x, y, w, rotation) for 2, 3 and 4 subjects, as fractions of the frame.
const LAYOUTS: Record<number, number[][]> = {
  2: [[0.08, 0.14, 0.44, -6], [0.5, 0.2, 0.44, 5]],
  3: [[0.04, 0.12, 0.36, -7], [0.33, 0.24, 0.36, 3], [0.62, 0.1, 0.34, -4]],
  4: [[0.03, 0.08, 0.32, -8], [0.27, 0.36, 0.3, 5], [0.52, 0.06, 0.3, -3], [0.7, 0.34, 0.27, 7]],
};

/** 2-4 tilted cards, one per " | " subject, flying in one after another; the keyword on top. */
export function Collage() {
  const frame = useCurrentFrame();
  const { beat, assets, props } = useBeat();
  const { width: W, height: H } = props;
  const subjects = (beat.broll_query || '').split('|').map(s => s.trim()).filter(Boolean).slice(0, 4);
  const n = Math.max(2, Math.min(4, subjects.length || 2));
  const layout = LAYOUTS[n];
  const light = beat.background_mode === 'light';
  const text = beat.emphasis_text || '';
  const size = fit(text, W * 0.7, H * 0.24);
  return <AbsoluteFill>
    <Backdrop mode={light ? 'light' : 'dark'} />
    {layout.map(([x, y, w, rot], i) => {
      const t = interpolate(frame - i * 4, [0, 10], [0, 1], { ...clamp, easing: easeOut });
      const from = i % 2 ? W * 0.6 : -W * 0.6;
      return <div key={i} style={{ position: 'absolute', left: x * W, top: y * H, width: w * W, height: w * W * 0.62, overflow: 'hidden',
        border: '8px solid #f7f5ee', boxShadow: '0 18px 50px rgba(0,0,0,0.5)',
        transform: `translateX(${(1 - t) * from}px) rotate(${rot * (0.6 + 0.4 * t)}deg)`, filter: `blur(${(1 - t) * 16}px)` }}>
        <Media media={assets.broll?.[i]} query={subjects[i] || beat.broll_fallback_query || ''} seed={beat.id * 10 + i} grade={beat.grade} tone={color(beat.semantic_color)} scale={1.05 + frame * 0.0008} />
      </div>;
    })}
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: H * 0.07 }}>
      <Keyword text={text} size={size} frame={frame} delay={8} light={light} style={{ textShadow: light ? '0 6px 24px rgba(255,255,255,.9)' : undefined }} />
      {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.42} frame={frame} delay={11} light={light} style={{ marginTop: -size * 0.06 }} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
