import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop } from '../components/Backdrop';
import { StockBackground, hasStock } from '../components/StockBackground';
import { Accent, Keyword, fit } from '../components/Words';
import { useBeat } from '../lib/context';
import { clamp, easeOut } from '../lib/motion';
import { color, rng } from '../lib/style';

/** A place: a pin dropping onto a stylised map grid with ripples, the place name beside it. (No real map data
 * is drawn, so nothing about the place's shape is invented.) */
export function MapCallout() {
  const frame = useCurrentFrame();
  const { beat, props, assets } = useBeat();
  const { width: W, height: H } = props;
  const place = beat.data?.place || beat.emphasis_text || '';
  const tone = color(beat.semantic_color === 'white' ? 'yellow' : beat.semantic_color);
  const r = rng(beat.id * 5 + 1);
  const roads = Array.from({ length: 16 }, () => {
    const x = r() * 1000, y = r() * 560;
    return `M${x},${y} C${x + (r() - 0.5) * 500},${y + (r() - 0.5) * 300} ${x + (r() - 0.5) * 500},${y + (r() - 0.5) * 300} ${x + (r() - 0.5) * 800},${y + (r() - 0.5) * 400}`;
  });
  const drop = interpolate(frame, [0, 10], [-H * 0.4, 0], { ...clamp, easing: easeOut });
  const px = W * 0.32, py = H * 0.55;
  const size = fit(place.toUpperCase(), W * 0.45, H * 0.2);
  return <AbsoluteFill>
    {hasStock(assets) ? <StockBackground scale={1.1 - frame * 0.0006} shade="rgba(10,18,51,0.6)" /> : <Backdrop mode="dark" tint="#0a1233" />}
    <svg viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid slice" style={{ position: 'absolute', width: '100%', height: '100%', transform: `scale(${1.1 - frame * 0.0006})` }}>
      {roads.map((d, i) => <path key={i} d={d} fill="none" stroke="#5f7cff" strokeOpacity={0.18} strokeWidth={1.5 + (i % 3)} />)}
    </svg>
    {[0, 1, 2].map(i => {
      const t = ((frame - 8 - i * 9) % 30) / 30;
      return frame > 8 + i * 9 && <div key={i} style={{ position: 'absolute', left: px - 80, top: py - 26, width: 160, height: 52, borderRadius: '50%',
        border: `3px solid ${tone}`, opacity: 1 - t, transform: `scale(${0.3 + t * 1.8})` }} />;
    })}
    <svg viewBox="0 0 24 32" width={H * 0.12} style={{ position: 'absolute', left: px - H * 0.06, top: py - H * 0.16 + drop, filter: `drop-shadow(0 0 12px ${tone})` }}>
      <path d="M12 31C12 31 2 18 2 11a10 10 0 0 1 20 0c0 7-10 20-10 20z" fill={tone} /><circle cx="12" cy="11" r="4" fill="#0a1233" />
    </svg>
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'flex-start', paddingLeft: W * 0.45 }}>
      <Keyword text={place} size={size} frame={frame} delay={6} semantic={beat.semantic_color === 'white' ? 'yellow' : beat.semantic_color} style={{ transformOrigin: 'left center' }} />
      {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.42} frame={frame} delay={9} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
