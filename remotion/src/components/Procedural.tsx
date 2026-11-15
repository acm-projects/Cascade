import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { rng } from '../lib/style';

// Generated motion backgrounds, used for a b-roll subject when no stock clip was found (or the stock service is
// unreachable). Chosen from the words of the b-roll query; deterministic, so cached beats stay identical.

type Kind = 'space' | 'earth' | 'forest' | 'mountain' | 'water' | 'sun' | 'crowd' | 'default';
const WORDS: [Kind, RegExp][] = [
  ['earth', /\b(earth|planet|globe|orbit|world)\b/i],
  ['space', /\b(space|star|stars|starfield|universe|void|galaxy|night sky|cosmos)\b/i],
  ['mountain', /\b(mountain|mountains|peak|peaks|alpine|ridge|hills?)\b/i],
  ['forest', /\b(forest|jungle|rainforest|canopy|tree|trees|leaf|leaves|frog|butterfly|orchid|jaguar|wildlife|plant|green)\b/i],
  ['water', /\b(ocean|sea|wave|waves|river|water|lake|rain|underwater)\b/i],
  ['sun', /\b(sun|sunlight|sunbeams?|rays|dawn|sunrise|sunset|light)\b/i],
  ['crowd', /\b(crowd|people|concert|city|street)\b/i],
];
export const kindOf = (query = ''): Kind => (WORDS.find(([, re]) => re.test(query)) || ['default'])[0];

export function Procedural({ query, seed, tone = '#3fd16f' }: { query: string; seed: number; tone?: string }) {
  const frame = useCurrentFrame();
  const kind = kindOf(query);
  const r = rng(seed * 31 + 7);
  const push = 1.04 + frame * 0.0009;
  if (kind === 'space' || kind === 'earth') {
    const stars = Array.from({ length: 220 }, () => [r(), r(), r() * 1.8 + 0.4, r()]);
    return <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 60%, #0d1424 0%, #020306 70%)', overflow: 'hidden' }}>
      <svg viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%', transform: `scale(${push})` }}>
        {stars.map(([x, y, s, t], i) => <circle key={i} cx={x * 1000} cy={y * 560} r={s} fill="#fff" opacity={0.35 + 0.65 * Math.abs(Math.sin(frame / 18 + t * 9))} />)}
        {kind === 'earth' && <>
          <defs>
            <radialGradient id={`planet${seed}`} cx="38%" cy="35%" r="70%"><stop offset="0%" stopColor="#7fd4ff" /><stop offset="45%" stopColor="#1e6fb8" /><stop offset="80%" stopColor="#0a2a55" /><stop offset="100%" stopColor="#020a18" /></radialGradient>
            <radialGradient id={`air${seed}`} cx="50%" cy="50%" r="50%"><stop offset="86%" stopColor="#5fc8ff" stopOpacity="0" /><stop offset="93%" stopColor="#8fe0ff" stopOpacity="0.9" /><stop offset="100%" stopColor="#8fe0ff" stopOpacity="0" /></radialGradient>
          </defs>
          <circle cx={500} cy={720 - frame * 0.15} r={420} fill={`url(#air${seed})`} transform="scale(1.08) translate(-38 -50)" />
          <circle cx={500} cy={720 - frame * 0.15} r={400} fill={`url(#planet${seed})`} />
          {Array.from({ length: 9 }, (_, i) => <ellipse key={i} cx={360 + i * 40 + ((frame * 0.6) % 40)} cy={520 - (i % 3) * 60} rx={60 + (i % 4) * 25} ry={14} fill="#2f8a4a" opacity={0.55} />)}
        </>}
      </svg>
    </AbsoluteFill>;
  }
  if (kind === 'mountain') {
    const ridge = (base: number, amp: number, k: number) => {
      const pts = Array.from({ length: 13 }, (_, i) => `${i * 90 - 40},${base - Math.abs(Math.sin(i * 1.7 + k)) * amp - r() * 30}`);
      return `M-40,600 L${pts.join(' L')} L1100,600 Z`;
    };
    return <AbsoluteFill style={{ background: 'linear-gradient(#f6c38b 0%, #e98e6c 35%, #6d6f9a 70%, #2b2f4a 100%)', overflow: 'hidden' }}>
      <svg viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%' }}>
        <circle cx={700} cy={250 - frame * 0.08} r={70} fill="#fff4d6" opacity={0.9} />
        {[[430, 140, 1, '#8d86a8', 0.25], [470, 170, 2, '#5c5a7d', 0.45], [520, 120, 3, '#34324f', 0.7]].map(([b, a, k, c, sp], i) =>
          <path key={i} d={ridge(b as number, a as number, k as number)} fill={c as string} transform={`translate(${-frame * (sp as number)} 0)`} />)}
        <rect x="0" y="380" width="1000" height="180" fill="url(#mist)" opacity={0.6} />
        <defs><linearGradient id="mist" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#fff" stopOpacity="0" /><stop offset="1" stopColor="#fff" stopOpacity="0.55" /></linearGradient></defs>
      </svg>
    </AbsoluteFill>;
  }
  if (kind === 'water') {
    return <AbsoluteFill style={{ background: 'linear-gradient(#0b3c5d 0%, #0e5f7a 45%, #04202f 100%)', overflow: 'hidden' }}>
      <svg viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%' }}>
        {Array.from({ length: 7 }, (_, i) => {
          const y = 200 + i * 55, amp = 14 + i * 4, ph = frame / (14 - i) + i;
          const d = `M-20,${y} ` + Array.from({ length: 22 }, (_, k) => `L${k * 50},${y + Math.sin(k * 0.7 + ph) * amp}`).join(' ') + ` L1020,600 L-20,600 Z`;
          return <path key={i} d={d} fill={`rgba(${40 + i * 8},${150 + i * 10},${190 + i * 6},${0.18 + i * 0.05})`} />;
        })}
        {Array.from({ length: 40 }, (_, i) => <circle key={i} cx={r() * 1000} cy={180 + r() * 360} r={1.5} fill="#bff" opacity={0.3 + 0.6 * Math.abs(Math.sin(frame / 9 + i))} />)}
      </svg>
    </AbsoluteFill>;
  }
  if (kind === 'crowd') {
    return <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 20%, #555 0%, #0a0a0a 70%)', overflow: 'hidden' }}>
      <svg viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%' }}>
        {Array.from({ length: 160 }, (_, i) => <circle key={i} cx={r() * 1000} cy={250 + r() * 310} r={2 + r() * 4} fill="#fff" opacity={0.2 + 0.8 * Math.abs(Math.sin(frame / 7 + i))} />)}
        {Array.from({ length: 30 }, (_, i) => <ellipse key={`h${i}`} cx={i * 36 + 10} cy={560} rx={22} ry={60 + (i % 4) * 14} fill="#000" />)}
      </svg>
    </AbsoluteFill>;
  }
  // forest, sun, default: layered light rays and drifting bokeh in the beat's colour
  const base = kind === 'forest' ? ['#0f2a17', '#1f5a2c', '#3e8f3d'] : kind === 'sun' ? ['#3a2208', '#a8611a', '#f2b34c'] : ['#101010', '#2a2a2a', tone];
  const rays = Array.from({ length: 9 }, () => [r() * 1000, 40 + r() * 70, r()]);
  const bokeh = Array.from({ length: 36 }, () => [r() * 1000, r() * 560, 6 + r() * 26, r()]);
  return <AbsoluteFill style={{ background: `linear-gradient(160deg, ${base[2]} 0%, ${base[1]} 45%, ${base[0]} 100%)`, overflow: 'hidden' }}>
    <svg viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%', transform: `scale(${push})` }}>
      <defs><linearGradient id={`ray${seed}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#fff8d0" stopOpacity="0.55" /><stop offset="1" stopColor="#fff8d0" stopOpacity="0" /></linearGradient></defs>
      {rays.map(([x, w, t], i) => <polygon key={i} points={`${x},-20 ${x + w},-20 ${x + w * 3 - 200},600 ${x - 200},600`} fill={`url(#ray${seed})`}
        opacity={0.25 + 0.25 * Math.sin(frame / 25 + t * 6)} />)}
      {kind === 'forest' && Array.from({ length: 14 }, (_, i) => <ellipse key={`l${i}`} cx={(i * 83 + frame * (0.4 + (i % 3) * 0.2)) % 1100 - 50} cy={(i * 47) % 560}
        rx={38} ry={13} fill="#1c4d23" opacity={0.75} transform={`rotate(${(i * 37 + frame) % 360} ${(i * 83) % 1000} ${(i * 47) % 560})`} />)}
      {bokeh.map(([x, y, s, t], i) => <circle key={`b${i}`} cx={x + Math.sin(frame / 40 + t * 6) * 12} cy={y - frame * 0.25 * t} r={s} fill="#fff6c8"
        opacity={interpolate(Math.sin(frame / 30 + t * 9), [-1, 1], [0.04, 0.22])} />)}
    </svg>
  </AbsoluteFill>;
}
