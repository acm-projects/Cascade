import { AbsoluteFill, Img, OffthreadVideo, staticFile } from 'remotion';
import { Media as MediaInfo } from '../lib/context';
import { Procedural } from './Procedural';
import { GRADES } from '../lib/style';

/** A b-roll subject: the stock clip/image the backend found, or a generated motion background from its query. */
export function Media({ media, query, seed, grade, tone, scale = 1, hue = 0 }:
  { media?: MediaInfo; query: string; seed: number; grade: string; tone?: string; scale?: number; hue?: number }) {
  const style = { width: '100%', height: '100%', objectFit: 'cover' as const };
  return <AbsoluteFill style={{ overflow: 'hidden', filter: GRADES[grade] || '' }}>
    <AbsoluteFill style={{ transform: `scale(${scale})` }}>
      {media?.kind === 'video' ? <OffthreadVideo src={staticFile(media.src)} muted style={style} />
        : media?.kind === 'image' ? <Img src={staticFile(media.src)} style={style} />
        : <AbsoluteFill style={{ filter: `blur(1.6px) saturate(0.78) hue-rotate(${hue}deg)` }}>
            {/* generated stand-in for footage: soft focus and a lens vignette so it reads as a shot, not a graphic */}
            <Procedural query={query} seed={seed} tone={tone} />
            <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 40%, rgba(0,0,0,0.55) 100%)' }} />
          </AbsoluteFill>}
    </AbsoluteFill>
  </AbsoluteFill>;
}
