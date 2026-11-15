import { AbsoluteFill, Img, staticFile, useCurrentFrame } from 'remotion';
import { useBeat } from '../lib/context';
import { GRADES, color } from '../lib/style';

/** The speaker cut out of the footage (RGBA PNG frames made by the backend), with a rim glow in `glowColor`.
 * Returns null when this beat has no cut-out, so callers can fall back. */
export function Cutout({ scale = 1, origin = '50% 50%', glowColor, grade, outline = 0 }:
  { scale?: number; origin?: string; glowColor?: string; grade?: string; outline?: number }) {
  const frame = useCurrentFrame();
  const { beat, assets, props, from, offset } = useBeat();
  const cut = assets.cutout;
  if (!cut || !cut.count) return null;
  // edit frame -> index in the cut-out sequence (which starts at cut.from and runs at cut.fps)
  const editFrame = offset + frame;
  const index = Math.max(0, Math.min(cut.count - 1, Math.floor((editFrame - cut.from) * cut.fps / props.fps)));
  const rim = glowColor || color(beat.semantic_color === 'white' ? 'orange' : beat.semantic_color);
  const shadows = [`drop-shadow(0 0 ${2 + outline}px ${rim})`, `drop-shadow(0 0 14px ${rim}aa)`, `drop-shadow(0 0 34px ${rim}55)`].join(' ');
  return <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: origin, filter: `${GRADES[grade || beat.grade] || ''} ${shadows}` }}>
    <Img src={staticFile(`${cut.dir}/${String(index).padStart(4, '0')}.png`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
  </AbsoluteFill>;
}

export const hasCutout = (assets: { cutout?: { count: number } }) => Boolean(assets.cutout?.count);
