import { AbsoluteFill, Img, OffthreadVideo, staticFile } from 'remotion';
import { Media as MediaInfo } from '../lib/context';
import { Procedural } from './Procedural';
import { GRADES } from '../lib/style';

/** A b-roll subject: the stock clip/image the backend found, or a generated motion background from its query. */
export function Media({ media, query, seed, grade, tone, scale = 1 }:
  { media?: MediaInfo; query: string; seed: number; grade: string; tone?: string; scale?: number }) {
  const style = { width: '100%', height: '100%', objectFit: 'cover' as const };
  return <AbsoluteFill style={{ overflow: 'hidden', filter: GRADES[grade] || '' }}>
    <AbsoluteFill style={{ transform: `scale(${scale})` }}>
      {media?.kind === 'video' ? <OffthreadVideo src={staticFile(media.src)} muted style={style} />
        : media?.kind === 'image' ? <Img src={staticFile(media.src)} style={style} />
        : <Procedural query={query} seed={seed} tone={tone} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
