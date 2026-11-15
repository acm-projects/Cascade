import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop } from '../components/Backdrop';
import { Cutout, hasCutout } from '../components/Cutout';
import { Footage } from '../components/Footage';
import { Icon, iconsFor } from '../components/Icons';
import { Accent, Keyword, fit } from '../components/Words';
import { useBeat } from '../lib/context';
import { clamp, easeOut } from '../lib/motion';
import { FONTS, color, rng } from '../lib/style';

/** The speaker cut out on a deep grid scene, outlined in the beat's colour, with themed icons floating around. */
export function SpeakerCutoutIcons() {
  const frame = useCurrentFrame();
  const { beat, assets, props } = useBeat();
  const { width: W, height: H } = props;
  const tone = color(beat.semantic_color === 'white' ? 'yellow' : beat.semantic_color);
  const icons = iconsFor(`${beat.spoken_text} ${beat.intent} ${beat.emphasis_text}`);
  const r = rng(beat.id * 13);
  const spots = [[0.1, 0.22], [0.3, 0.12], [0.08, 0.62], [0.42, 0.7], [0.88, 0.16], [0.9, 0.7]].map(([x, y]) => [x + (r() - 0.5) * 0.05, y + (r() - 0.5) * 0.05]);
  const text = beat.emphasis_text || '';
  const size = fit(text, W * 0.55, H * 0.2, 0.42);
  return <AbsoluteFill>
    <Backdrop mode="dark" tint="#0b1030" />
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 66% 45%, ${tone}33 0%, rgba(0,0,0,0) 55%)` }} />
    {hasCutout(assets) ? <Cutout scale={1.02} origin="66% 40%" glowColor={tone} outline={2} grade="bw" />
      : <AbsoluteFill style={{ opacity: 0.85 }}><Footage darken={0.25} /></AbsoluteFill>}
    {spots.map(([x, y], i) => {
      const t = interpolate(frame - i * 2, [0, 10], [0, 1], { ...clamp, easing: easeOut });
      const bob = Math.sin((frame + i * 11) / 14) * H * 0.012;
      return <div key={i} style={{ position: 'absolute', left: x * W, top: y * H + bob, opacity: t, transform: `scale(${0.4 + 0.6 * t}) rotate(${(r() - 0.5) * 30}deg)`,
        filter: `drop-shadow(0 0 10px ${tone})` }}>
        <Icon name={icons[i % icons.length]} size={H * 0.11} color="#ffffff" />
      </div>;
    })}
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'flex-start', padding: `0 0 ${H * 0.1}px ${W * 0.06}px` }}>
      <Keyword text={text} size={size} frame={frame} delay={3} semantic={beat.semantic_color === 'white' ? 'yellow' : beat.semantic_color}
        family={FONTS.accent} italic style={{ transformOrigin: 'left bottom' }} />
      {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.42} frame={frame} delay={7} style={{ marginLeft: size * 0.6 }} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
