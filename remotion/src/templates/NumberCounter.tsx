import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop } from '../components/Backdrop';
import { StockBackground, hasStock } from '../components/StockBackground';
import { Accent } from '../components/Words';
import { useBeat } from '../lib/context';
import { clamp, easeOut, entrance } from '../lib/motion';
import { FONTS, color, glow } from '../lib/style';

/** Format like the speech: "-$70,000", "3.5", "1,200". Money if the beat's words talk about money. */
export function formatNumber(value: number, money: boolean, decimals: number) {
  const sign = value < 0 ? '-' : '';
  const body = Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return `${sign}${money ? '$' : ''}${body}`;
}

/** An animated number counting up to data.number (no chart: just the big number), over the beat's b-roll if it has one. */
export function NumberCounter() {
  const frame = useCurrentFrame();
  const { beat, length, props, assets } = useBeat();
  const { width: W, height: H } = props;
  const target = beat.data?.number ?? 0;
  const money = /\$|dollar|money|debt|cost|paid|pay|price|salary|income|worth/i.test(`${beat.spoken_text} ${beat.emphasis_text}`);
  const decimals = Number.isInteger(target) ? 0 : Math.min(2, String(target).split('.')[1]?.length || 1);
  const p = interpolate(frame, [2, Math.max(8, length * 0.6)], [0, 1], { ...clamp, easing: easeOut });
  const value = target * p;
  const light = beat.background_mode === 'light' && !hasStock(assets);   // with a stock clip the number goes over it, dark style
  const tone = color(beat.semantic_color === 'white' ? (target < 0 ? 'red' : 'green') : beat.semantic_color);
  const e = entrance(frame, 0);
  const label = formatNumber(Number(value.toFixed(decimals)), money, decimals);
  const size = Math.min(H * 0.3, (W * 0.8) / Math.max(4, label.length * 0.55));
  return <AbsoluteFill>
    {hasStock(assets) ? <StockBackground scale={1 + frame * 0.0008} shade="rgba(0,0,0,0.6)" /> : <Backdrop mode={light ? 'light' : 'dark'} />}
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ fontFamily: FONTS.ui, fontWeight: 800, fontSize: size, color: tone, textShadow: light ? 'none' : glow(tone, 1),
        transform: `skewX(-9deg) scale(${e.scale})`, filter: `blur(${e.blur}px)`, opacity: e.opacity, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{label}</div>
      {(beat.accent_word || beat.emphasis_text) && <Accent text={beat.accent_word || beat.emphasis_text || ''} size={size * 0.3} frame={frame} delay={8} light={light}
        style={{ alignSelf: 'center', marginLeft: size * 1.2 }} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
