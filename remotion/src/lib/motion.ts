import { Easing, interpolate } from 'remotion';

export const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

/** The house text entrance: starts blurred and scaled, snaps sharp within ~6 frames. */
export function entrance(frame: number, delay = 0, frames = 6) {
  const p = interpolate(frame - delay, [0, frames], [0, 1], { ...clamp, easing: easeOut });
  return { opacity: Math.min(1, p * 1.6), blur: (1 - p) * 18, scale: 1.32 - 0.32 * p, p };
}

/** A slow push-in over the whole beat so nothing sits still. */
export const drift = (frame: number, length: number, amount = 0.05) => 1 + amount * Math.min(1, frame / Math.max(1, length));
