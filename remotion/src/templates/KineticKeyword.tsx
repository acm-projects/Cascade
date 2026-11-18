import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { Accent, Keyword, fit } from '../components/Words';
import { Backdrop } from '../components/Backdrop';
import { Footage } from '../components/Footage';
import { Cutout, hasCutout } from '../components/Cutout';
import { StockBackground, hasStock } from '../components/StockBackground';
import { FONTS } from '../lib/style';
import { useBeat } from '../lib/context';
import { drift } from '../lib/motion';

/** Bold keyword + italic serif accent. Dark: over the graded speaker, on the side he faces. Light: paper grid, centered. */
export function KineticKeyword() {
  const frame = useCurrentFrame();
  const { beat, length, props, assets } = useBeat();
  const { width: W, height: H } = props;
  const text = beat.emphasis_text || '';
  const light = beat.background_mode === 'light' && !hasStock(assets);   // with a stock clip the words go over it, dark style
  // two or more words stack so each line can be big ("BEAUTIFUL / LIFE")
  const words = text.split(' ').filter(Boolean);
  const lines = words.length > 1 && text.length > 8 ? [words.slice(0, -1).join(' '), words.at(-1) as string] : [text];
  const longest = lines.reduce((a, b) => (b.length > a.length ? b : a), '');
  const stacked = lines.length > 1;
  if (light) {
    const size = fit(longest, W * 0.84, H * (stacked ? 0.3 : 0.36));
    return <AbsoluteFill>
      <Backdrop mode="light" />
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', transform: `scale(${drift(frame, length, 0.06)})` }}>
        {lines.map((line, i) => <Keyword key={i} text={line} size={size} frame={frame} delay={i * 2} light />)}
        {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.56} frame={frame} light style={{ marginTop: -size * 0.16, alignSelf: 'center' }} />}
      </AbsoluteFill>
    </AbsoluteFill>;
  }
  const size = fit(longest, W * 0.5, H * (stacked ? 0.27 : 0.36));
  const zoom = drift(frame, length, 0.07) * 1.04;
  const stock = hasStock(assets);   // a stock clip behind the words instead of the speaker
  const cut = hasCutout(assets) && !stock;
  return <AbsoluteFill>
    {stock ? <StockBackground scale={zoom} shade="rgba(0,0,0,0.35)" /> : <Footage scale={zoom} darken={cut ? 0.62 : 0.22} blur={cut ? 3 : 0} origin="65% 35%" />}
    {cut && <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'flex-end', paddingRight: W * 0.02 }}>
      <div style={{ fontFamily: FONTS.heading, fontSize: H * 0.62, lineHeight: 0.9, color: 'rgba(255,255,255,0.05)', WebkitTextStroke: '2px rgba(255,255,255,0.16)',
        textTransform: 'uppercase', whiteSpace: 'nowrap', transform: `scale(${zoom})` }}>{text.split(' ').at(-1)}</div>
    </AbsoluteFill>}
    {cut && <Cutout scale={zoom} origin="65% 35%" />}
    <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.15) 45%, rgba(0,0,0,0) 60%)' }} />
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'flex-start', paddingLeft: W * 0.06 }}>
      {lines.map((line, i) => <Keyword key={i} text={line} size={size} frame={frame} delay={i * 2} style={{ transformOrigin: 'left center' }} />)}
      {beat.accent_word && <Accent text={beat.accent_word} size={size * 0.62} frame={frame} style={{ marginTop: -size * 0.2, marginLeft: size * 0.5, transformOrigin: 'left center' }} />}
    </AbsoluteFill>
  </AbsoluteFill>;
}
