import { AbsoluteFill, OffthreadVideo, Sequence, staticFile } from 'remotion';
import { GRADES } from '../lib/style';
import { useBeat } from '../lib/context';

/** The speaker footage at the same moment as the audio: source frame = edit frame. */
export function Footage({ scale = 1, grade, darken = 0, blur = 0, origin = '50% 40%' }:
  { scale?: number; grade?: string; darken?: number; blur?: number; origin?: string }) {
  const { beat, offset, props } = useBeat();
  return <AbsoluteFill style={{ overflow: 'hidden', background: '#000' }}>
    <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: origin, filter: `${GRADES[grade || beat.grade] || ''} ${blur ? `blur(${blur}px)` : ''}` }}>
      <Sequence from={-offset} layout="none">
        <OffthreadVideo src={staticFile(props.source)} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </Sequence>
    </AbsoluteFill>
    {darken > 0 && <AbsoluteFill style={{ background: `rgba(0,0,0,${darken})` }} />}
  </AbsoluteFill>;
}
