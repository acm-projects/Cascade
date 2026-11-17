import { AbsoluteFill } from 'remotion';
import { Media } from './Media';
import { useBeat } from '../lib/context';
import { color } from '../lib/style';

/** The beat's stock clip as a darkened, slowly pushing background (a graphic beat over b-roll), or null if it has none. */
export function StockBackground({ scale = 1, shade = 'rgba(0,0,0,0.55)' }: { scale?: number; shade?: string }) {
  const { beat, assets } = useBeat();
  const clip = assets.broll?.[0];
  if (!clip) return null;
  return <AbsoluteFill>
    <Media media={clip} query={beat.broll_query || ''} seed={beat.id} grade={beat.grade} tone={color(beat.semantic_color)} scale={scale} />
    <AbsoluteFill style={{ background: shade }} />
  </AbsoluteFill>;
}

export function hasStock(assets: { broll?: unknown[] }) {
  return Boolean(assets.broll?.[0]);
}
