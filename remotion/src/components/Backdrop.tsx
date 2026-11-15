import { AbsoluteFill } from 'remotion';
import { NIGHT, PAPER } from '../lib/style';

/** Light "paper grid" or dark grid scene. */
export function Backdrop({ mode, tint }: { mode: 'light' | 'dark'; tint?: string }) {
  const light = mode === 'light';
  const line = light ? 'rgba(20,20,20,0.075)' : 'rgba(255,255,255,0.055)';
  return <AbsoluteFill style={{
    background: light ? PAPER : (tint || NIGHT),
    backgroundImage: `linear-gradient(${line} 1px, transparent 1px), linear-gradient(90deg, ${line} 1px, transparent 1px)`,
    backgroundSize: '64px 64px', backgroundPosition: '-1px -1px',
  }}>
    <AbsoluteFill style={{ background: light
      ? 'radial-gradient(ellipse at 50% 45%, rgba(255,255,255,0.55), rgba(0,0,0,0) 60%)'
      : 'radial-gradient(ellipse at 50% 45%, rgba(255,255,255,0.06), rgba(0,0,0,0) 65%)' }} />
  </AbsoluteFill>;
}
