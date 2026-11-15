import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { Accent, Keyword, fit } from '../components/Words';
import { Backdrop } from '../components/Backdrop';
import { Footage } from '../components/Footage';
import { useBeat } from '../lib/context';
import { drift } from '../lib/motion';

/** Bold keyword + italic serif accent. Dark: over the graded speaker, on the side he faces. Light: paper grid, centered. */
export function KineticKeyword() {
  const frame = useCurrentFrame();
  const { beat, length, props } = useBeat();
  const { width: W, height: H } = props;
  const text = beat.emphasis_text || '';
  const light = beat.background_mode === 'light';
  if (light) {
    const size = fit(text, W * 0.84, H * 0.36);
    return <AbsoluteFill>
      <Backdrop mode="light" />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', transform: `scale(${drift(frame, length, 0.06)})` }}>
        <Keyword text={text} size={size} frame={frame} light />
        {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.42} frame={frame} light style={{ marginTop: -size * 0.12, alignSelf: 'center' }} />}
      </AbsoluteFill>
    </AbsoluteFill>;
  }
  const size = fit(text, W * 0.5, H * 0.3);
  return <AbsoluteFill>
    <Footage scale={drift(frame, length, 0.07) * 1.04} darken={0.42} origin="65% 35%" />
    <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.25) 55%, rgba(0,0,0,0) 75%)' }} />
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'flex-start', paddingLeft: W * 0.07 }}>
      <Keyword text={text} size={size} frame={frame} style={{ transformOrigin: 'left center' }} />
      {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.46} frame={frame} style={{ marginTop: -size * 0.1, marginLeft: size * 0.35, transformOrigin: 'left center' }} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
