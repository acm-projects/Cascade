import { CSSProperties } from 'react';
import { useBeat } from '../lib/context';
import { entrance } from '../lib/motion';
import { FONTS, color, glow, textColor } from '../lib/style';

/** Font size that fits `text` on one line in `width` px (Anton caps are ~0.47 em wide). */
export const fit = (text: string, width: number, max: number, em = 0.47) =>
  Math.min(max, width / Math.max(1, text.length * em));

/** The bold keyword with its blur-to-sharp entrance and semantic glow. */
export function Keyword({ text, size, frame, delay = 0, light = false, semantic, style, glowStrength = 1, family = FONTS.heading, italic = false }:
  { text: string; size: number; frame: number; delay?: number; light?: boolean; semantic?: string; style?: CSSProperties; glowStrength?: number; family?: string; italic?: boolean }) {
  const { beat } = useBeat();
  const tone = semantic || beat.semantic_color;
  const fill = textColor(tone, light);
  const e = entrance(frame, delay);
  const shine = light && tone === 'white' ? '0 6px 18px rgba(0,0,0,0.18)' : glow(color(tone), glowStrength);
  return <div style={{
    fontFamily: family, fontStyle: italic ? 'italic' : 'normal', fontSize: size, lineHeight: 0.92, color: fill,
    textTransform: family === FONTS.heading ? 'uppercase' : 'none', letterSpacing: family === FONTS.heading ? '0.01em' : '0',
    whiteSpace: 'nowrap', textShadow: shine, opacity: e.opacity, filter: `blur(${e.blur}px)`,
    transform: `scale(${e.scale})`, ...style,
  }}>{text}</div>;
}

/** The italic serif accent word, a beat behind the keyword. */
export function Accent({ text, size, frame, delay = 4, light = false, semantic, style }:
  { text: string; size: number; frame: number; delay?: number; light?: boolean; semantic?: string; style?: CSSProperties }) {
  const { beat } = useBeat();
  const tone = semantic || beat.semantic_color;
  const warm = tone === 'yellow' || tone === 'orange';
  const fill = light ? '#1d1d1d' : warm ? color(tone) : '#ffffff';
  const e = entrance(frame, delay);
  return <div style={{
    fontFamily: FONTS.accent, fontStyle: 'italic', fontSize: size, lineHeight: 1, color: fill, whiteSpace: 'nowrap',
    textShadow: light ? 'none' : `0 0 16px rgba(0,0,0,0.6), ${warm ? glow(color(tone), 0.6) : '0 0 22px rgba(255,255,255,0.35)'}`,
    opacity: e.opacity, filter: `blur(${e.blur}px)`, transform: `scale(${e.scale})`, ...style,
  }}>{text}</div>;
}
