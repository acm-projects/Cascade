import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop } from '../components/Backdrop';
import { Accent, Keyword, fit } from '../components/Words';
import { useBeat } from '../lib/context';
import { clamp, easeOut } from '../lib/motion';
import { FONTS, color, rng } from '../lib/style';

/** A named source (site, channel, publication): a generic page card titled with its name, tilted and glowing,
 * the keyword in front. It is a stylised card, not a copy of the real page. */
export function ScreenshotCallout() {
  const frame = useCurrentFrame();
  const { beat, props } = useBeat();
  const { width: W, height: H } = props;
  const name = beat.data?.screenshot_target || beat.emphasis_text || '';
  const tone = color(beat.semantic_color === 'white' ? 'red' : beat.semantic_color);
  const t = interpolate(frame, [0, 12], [0, 1], { ...clamp, easing: easeOut });
  const r = rng(beat.id * 3);
  const text = beat.emphasis_text || name;
  const size = fit(text, W * 0.8, H * 0.24);
  return <AbsoluteFill>
    <Backdrop mode="dark" />
    <AbsoluteFill style={{ left: W * 0.14, top: H * 0.08, width: W * 0.72, height: H * 0.7, background: '#16171b', borderRadius: 14,
      boxShadow: `0 0 60px ${tone}55, 0 30px 80px rgba(0,0,0,0.6)`, transform: `perspective(1400px) rotateX(${12 - 6 * t}deg) rotateZ(${-3 + t}deg) scale(${0.9 + 0.1 * t})`,
      opacity: t, overflow: 'hidden', filter: `blur(${(1 - t) * 10}px)` }}>
      <div style={{ height: 34, background: '#24252b', display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 14 }}>
        {['#ff5f57', '#febc2e', '#28c840'].map(c => <div key={c} style={{ width: 12, height: 12, borderRadius: 6, background: c }} />)}
      </div>
      <div style={{ padding: '22px 28px', fontFamily: FONTS.ui, color: '#f2f2f2' }}>
        <div style={{ fontWeight: 800, fontSize: H * 0.06 }}>{name}</div>
        {Array.from({ length: 6 }, (_, i) => <div key={i} style={{ height: 14, width: `${50 + r() * 45}%`, background: '#2e3038', borderRadius: 7, marginTop: 16 }} />)}
      </div>
    </AbsoluteFill>
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: H * 0.08 }}>
      <Keyword text={text} size={size} frame={frame} delay={5} semantic={beat.semantic_color === 'white' ? 'red' : beat.semantic_color} glowStrength={1.4} />
      {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.42} frame={frame} delay={9} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
