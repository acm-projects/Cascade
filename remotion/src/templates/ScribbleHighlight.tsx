import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { Backdrop } from '../components/Backdrop';
import { Footage } from '../components/Footage';
import { ScribbleEllipse, ScribbleLine } from '../components/Scribble';
import { useBeat } from '../lib/context';
import { entrance } from '../lib/motion';
import { FONTS, color, glow, textColor } from '../lib/style';

/** A word circled by hand, the lead-in words above it struck through. */
export function ScribbleHighlight() {
  const frame = useCurrentFrame();
  const { beat, props } = useBeat();
  const { width: W, height: H } = props;
  const light = beat.background_mode === 'light';
  const text = (beat.emphasis_text || '').toUpperCase();
  const tone = beat.semantic_color === 'white' ? 'yellow' : beat.semantic_color;
  const ink = light ? '#151515' : color(tone);
  const pen = color(tone === 'yellow' ? 'orange' : tone);
  const size = Math.min(H * 0.26, (W * 0.62) / Math.max(1, text.length * 0.5));
  const boxW = text.length * size * 0.5, boxH = size;
  const e = entrance(frame, 0);
  const lead = beat.accent_word || '';
  const leadSize = size * 0.38;
  return <AbsoluteFill>
    {light ? <Backdrop mode="light" /> : <><Footage darken={0.82} blur={6} scale={1.1} /><Backdrop mode="dark" tint="rgba(8,8,10,0.55)" /></>}
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      {lead && <div style={{ position: 'relative', fontFamily: FONTS.ui, fontWeight: 700, fontSize: leadSize, color: light ? '#222' : '#f1f1f1',
        marginBottom: size * 0.05, opacity: entrance(frame, 2).opacity, filter: `blur(${entrance(frame, 2).blur}px)` }}>
        {lead}
        <ScribbleLine w={lead.length * leadSize * 0.52} y={leadSize * 0.62} color={light ? '#c0392b' : '#ffffff'} frame={frame} delay={14} />
      </div>}
      <div style={{ position: 'relative', width: boxW, height: boxH, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <div style={{ fontFamily: FONTS.accent, fontStyle: 'italic', fontSize: size, lineHeight: 1, color: light ? ink : textColor(tone, false),
          textShadow: light ? 'none' : glow(color(tone), 0.7), whiteSpace: 'nowrap', opacity: e.opacity, filter: `blur(${e.blur}px)`, transform: `scale(${e.scale})` }}>{text}</div>
        <ScribbleEllipse w={boxW} h={boxH} color={pen} frame={frame} delay={5} />
      </div>
    </AbsoluteFill>
  </AbsoluteFill>;
}
