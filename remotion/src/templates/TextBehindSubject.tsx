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
  const words = text.split(' ').filter(Boolean);
  // two short words stack on two lines so each can be huge ("THE / JUNGLE")
  const lines = words.length > 1 && text.length > 7 ? [words.slice(0, -1).join(' '), words.at(-1) as string] : [text];
  const small = lines.length > 1 && lines[0].length <= 3;          // "THE / JUNGLE": the article rides small above
  const longest = Math.max(...lines.slice(small ? 1 : 0).map(l => l.length));
  // the speaker stands on the right: keep the word in the left two-thirds so most of it stays readable
  const size = Math.min(H * (lines.length > 1 && !small ? 0.5 : 0.7), (W * 0.7) / Math.max(1, longest * 0.47));
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
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'flex-start', paddingLeft: W * 0.03, width: W * 0.74 }}>
      <div style={{ fontFamily: FONTS.heading, fontSize: size, lineHeight: 0.84, color: fill, letterSpacing: '-0.01em', whiteSpace: 'nowrap', textAlign: 'left',
        transform: `translateY(${rise + (cut ? 0 : H * 0.12)}px)`, filter: `blur(${blur}px)`, opacity: cut ? 1 : 0.78,
        textShadow: light ? '0 10px 40px rgba(0,0,0,0.18)' : glow(beat.semantic_color === 'white' ? '#ffffff' : tone, 0.5) }}>
        {lines.map((line, i) => <div key={i} style={small && i === 0 ? { fontSize: size * 0.42, lineHeight: 1, marginLeft: size * 0.06 } : undefined}>{line}</div>)}
      </div>
    </AbsoluteFill>
    {cut && <Cutout scale={zoom} origin="68% 35%" glowColor={beat.semantic_color === 'white' ? '#ff6a1c' : tone} />}
    {beat.accent_word && <div style={{ position: 'absolute', left: W * 0.3, top: H * 0.62, background: '#b3121a', padding: `0 ${H * 0.03}px ${H * 0.012}px`,
      transform: `rotate(-4deg) scale(${interpolate(frame, [8, 14], [0.6, 1], { ...clamp, easing: easeOut })})`, opacity: interpolate(frame, [8, 11], [0, 1], clamp),
      boxShadow: '0 8px 30px rgba(0,0,0,0.35)' }}>
      <Accent text={beat.accent_word.toUpperCase()} size={H * 0.1} frame={frame} delay={8} />
    </div>}
  </AbsoluteFill>;
}
