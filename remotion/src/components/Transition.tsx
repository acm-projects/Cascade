import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { BeatInfo } from '../lib/context';
import { clamp, easeInOut, easeOut } from '../lib/motion';
import { motionBlur } from './Finish';
import { BeatPicture, PrevPicture } from '../Edit';

/** The cut into a beat: whip_pan, zoom_blur, glitch, flash_cut, slide or fade, over `frames` frames at its start,
 * with the previous beat still moving underneath. After that, just the beat. */
export function Transition({ name, frames, prev, info }: { name: string; frames: number; prev: BeatInfo | null; info: BeatInfo }) {
  const f = useCurrentFrame();
  const current = <BeatPicture info={info} />;
  if (!prev || frames <= 0 || f >= frames) return current;
  const p = interpolate(f, [0, frames], [0, 1], clamp);
  const before = <PrevPicture info={prev} />;
  const layer = (child, style) => <AbsoluteFill style={style}>{child}</AbsoluteFill>;
  switch (name) {
    case 'whip_pan': {
      const e = easeInOut(p);
      const speed = Math.sin(Math.PI * p);        // fastest mid-whip, so blur peaks there
      return <AbsoluteFill style={{ overflow: 'hidden' }}>
        {layer(before, { transform: `translateX(${-e * 100}%)`, filter: motionBlur(44 * speed) })}
        {layer(current, { transform: `translateX(${(1 - e) * 100}%)`, filter: motionBlur(44 * speed) })}
      </AbsoluteFill>;
    }
    case 'zoom_blur': {
      const e = easeOut(p);
      return <AbsoluteFill style={{ overflow: 'hidden' }}>
        {layer(before, { transform: `scale(${1 + 0.6 * p})`, filter: `blur(${18 * p}px)`, opacity: 1 - e })}
        {layer(current, { transform: `scale(${1.45 - 0.45 * e})`, filter: `blur(${(1 - e) * 22}px)`, opacity: Math.min(1, e * 1.6) })}
      </AbsoluteFill>;
    }
    case 'glitch': {
      const showNew = f % 3 !== 1 && p > 0.25;
      const jitter = (f * 37) % 7 - 3;
      const split = (1 - p) * 14;
      const picture = showNew ? current : before;
      return <AbsoluteFill style={{ overflow: 'hidden', background: '#000' }}>
        {layer(picture, { transform: `translateX(${jitter * 4}px)` })}
        {layer(picture, { transform: `translateX(${split}px)`, mixBlendMode: 'screen', opacity: 0.55, filter: 'sepia(1) hue-rotate(-50deg) saturate(6)' })}
        {layer(picture, { transform: `translateX(${-split}px)`, mixBlendMode: 'screen', opacity: 0.45, filter: 'sepia(1) hue-rotate(140deg) saturate(6)' })}
        {[0.18, 0.47, 0.71].map((y, i) => layer(picture, { clipPath: `inset(${y * 100}% 0 ${(1 - y - 0.07) * 100}% 0)`, transform: `translateX(${((f + i * 5) % 9 - 4) * 12 * (1 - p)}px)` }))}
      </AbsoluteFill>;
    }
    case 'flash_cut': {
      const flash = 1 - Math.abs(p * 2 - 1);
      return <AbsoluteFill>
        {p < 0.5 ? before : layer(current, { transform: `scale(${1.06 - 0.06 * p})` })}
        <AbsoluteFill style={{ background: '#fff', opacity: flash * 0.95 }} />
      </AbsoluteFill>;
    }
    case 'slide': {
      const e = easeInOut(p);
      const speed = Math.sin(Math.PI * p);
      return <AbsoluteFill style={{ overflow: 'hidden' }}>
        {layer(before, { transform: `translateY(${-e * 35}%)`, filter: motionBlur(30 * speed, 'v') })}
        {layer(current, { transform: `translateY(${(1 - e) * 100}%)`, filter: motionBlur(30 * speed, 'v'), boxShadow: '0 -20px 60px rgba(0,0,0,.6)' })}
      </AbsoluteFill>;
    }
    default: // fade
      return <AbsoluteFill>{before}{layer(current, { opacity: easeInOut(p) })}</AbsoluteFill>;
  }
}
