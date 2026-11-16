import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { Accent, Keyword, fit } from '../components/Words';
import { Backdrop } from '../components/Backdrop';
import { Media } from '../components/Media';
import { useBeat } from '../lib/context';
import { drift } from '../lib/motion';
import { color, glow } from '../lib/style';

const glowFor = (semantic: string) => glow(color(semantic), 0.8);

/** Stock clip behind the keyword. Dark: full bleed, darkened. Light: a tilted photo card on the paper grid. */
export function BrollOverlay() {
  const frame = useCurrentFrame();
  const { beat, length, assets, props } = useBeat();
  const { width: W, height: H } = props;
  const text = beat.emphasis_text || '';
  const media = <Media media={assets.broll?.[0]} query={beat.broll_query || ''} seed={beat.id} grade={beat.grade}
    tone={color(beat.semantic_color)} scale={drift(frame, length, 0.08)} />;
  if (beat.background_mode === 'light') {
    const size = fit(text, W * 0.8, H * 0.3);
    return <AbsoluteFill>
      <AbsoluteFill style={{ filter: 'brightness(1.12) contrast(0.95)' }}>{media}</AbsoluteFill>
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 45%, rgba(240,236,228,0) 35%, rgba(240,236,228,0.78) 100%)' }} />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
        <Keyword text={text} size={size} frame={frame} delay={2} glowStrength={0.9} style={{ textShadow: `0 0 30px rgba(0,0,0,0.55), ${glowFor(beat.semantic_color)}` }} />
        {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.55} frame={frame} delay={6} style={{ marginTop: -size * 0.14 }} />}
      </AbsoluteFill>
    </AbsoluteFill>;
  }
  const size = fit(text, W * 0.8, H * 0.32);
  return <AbsoluteFill>
    {media}
    <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.6) 100%)' }} />
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      <Keyword text={text} size={size} frame={frame} delay={2} />
      {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.55} frame={frame} delay={6} style={{ marginTop: -size * 0.14 }} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
