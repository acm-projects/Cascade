import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Footage } from '../components/Footage';
import { Cutout, hasCutout } from '../components/Cutout';
import { Accent } from '../components/Words';
import { useBeat } from '../lib/context';
import { clamp, drift, easeOut } from '../lib/motion';
import { FONTS, color, glow } from '../lib/style';

/** Giant word behind the cut-out speaker (intros, names, payoff lines). Without a cut-out, the word sits over
 * the footage, lower and translucent, so nothing is hidden. */
export function TextBehindSubject() {
  const frame = useCurrentFrame();
  const { beat, length, assets, props } = useBeat();
  const { width: W, height: H } = props;
  const light = beat.background_mode === 'light';
  const text = (beat.emphasis_text || '').toUpperCase();
  const size = Math.min(H * 0.72, (W * 0.94) / Math.max(1, text.length * 0.47));
  const rise = interpolate(frame, [0, 10], [H * 0.12, 0], { ...clamp, easing: easeOut });
  const blur = interpolate(frame, [0, 7], [22, 0], clamp);
  const tone = color(beat.semantic_color);
  const cut = hasCutout(assets);
  const fill = light ? (beat.semantic_color === 'white' ? '#3a3a3a' : tone) : (beat.semantic_color === 'white' ? '#e9e6df' : tone);
  const zoom = drift(frame, length, 0.05) * 1.03;
  return <AbsoluteFill>
    <Footage scale={zoom} origin="68% 35%" grade={beat.grade} />
    {light && <AbsoluteFill style={{ background: 'rgba(236,232,224,0.62)' }} />}
    {!light && <AbsoluteFill style={{ background: 'rgba(0,0,0,0.35)' }} />}
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ fontFamily: FONTS.heading, fontSize: size, lineHeight: 0.86, color: fill, letterSpacing: '-0.01em', whiteSpace: 'nowrap',
        transform: `translateY(${rise + (cut ? 0 : H * 0.12)}px)`, filter: `blur(${blur}px)`, opacity: cut ? 1 : 0.78,
        textShadow: light ? '0 10px 40px rgba(0,0,0,0.18)' : glow(beat.semantic_color === 'white' ? '#ffffff' : tone, 0.5),
        WebkitTextStroke: light ? '0' : '0' }}>{text}</div>
    </AbsoluteFill>
    {cut && <Cutout scale={zoom} origin="68% 35%" glowColor={beat.semantic_color === 'white' ? '#ff6a1c' : tone} />}
    {beat.accent_word && <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'flex-start', padding: `0 0 ${H * 0.12}px ${W * 0.08}px` }}>
      <div style={{ background: light ? '#151515' : '#b3121a', padding: '2px 18px 6px', transform: 'rotate(-3deg)' }}>
        <Accent text={beat.accent_word} size={H * 0.08} frame={frame} delay={8} />
      </div>
    </AbsoluteFill>}
  </AbsoluteFill>;
}
