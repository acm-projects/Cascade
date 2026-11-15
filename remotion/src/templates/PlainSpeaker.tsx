import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Footage } from '../components/Footage';
import { useBeat } from '../lib/context';
import { clamp, easeOut } from '../lib/motion';

/** Breathers and pauses: the speaker with a slow push-in (a touch faster on a pause before a payoff). */
export function PlainSpeaker() {
  const frame = useCurrentFrame();
  const { beat, length } = useBeat();
  const pause = !beat.spoken_text;
  const zoom = interpolate(frame, [0, length], [1.0, pause ? 1.14 : 1.07], { ...clamp, easing: easeOut });
  return <AbsoluteFill>
    <Footage scale={zoom} origin="68% 32%" darken={pause ? 0.15 : 0} />
  </AbsoluteFill>;
}
