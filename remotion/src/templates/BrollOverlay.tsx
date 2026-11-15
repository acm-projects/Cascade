import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { Accent, Keyword, fit } from '../components/Words';
import { Backdrop } from '../components/Backdrop';
import { Media } from '../components/Media';
import { useBeat } from '../lib/context';
import { drift, entrance } from '../lib/motion';
import { color } from '../lib/style';

/** Stock clip behind the keyword. Dark: full bleed, darkened. Light: a tilted photo card on the paper grid. */
export function BrollOverlay() {
  const frame = useCurrentFrame();
  const { beat, length, assets, props } = useBeat();
  const { width: W, height: H } = props;
  const text = beat.emphasis_text || '';
  const media = <Media media={assets.broll?.[0]} query={beat.broll_query || ''} seed={beat.id} grade={beat.grade}
    tone={color(beat.semantic_color)} scale={drift(frame, length, 0.08)} />;
  if (beat.background_mode === 'light') {
    const e = entrance(frame, 0, 8);
    const size = fit(text, W * 0.78, H * 0.26);
    return <AbsoluteFill>
      <Backdrop mode="light" />
      <AbsoluteFill style={{ left: W * 0.12, top: H * 0.1, width: W * 0.76, height: H * 0.62, border: '10px solid #fbfaf6',
        boxShadow: '0 24px 60px rgba(0,0,0,0.35)', transform: `rotate(${-2.5 + e.p * 1.2}deg) scale(${0.92 + 0.08 * e.p})`, opacity: e.opacity, overflow: 'hidden' }}>
        {media}
      </AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: H * 0.06 }}>
        <Keyword text={text} size={size} frame={frame} delay={3} light />
        {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.45} frame={frame} delay={6} light style={{ marginTop: -size * 0.08 }} />}
      </AbsoluteFill>
    </AbsoluteFill>;
  }
  const size = fit(text, W * 0.8, H * 0.32);
  return <AbsoluteFill>
    {media}
    <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.6) 100%)' }} />
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      <Keyword text={text} size={size} frame={frame} delay={2} />
      {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.45} frame={frame} delay={6} style={{ marginTop: -size * 0.08 }} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
