// The style bible (beats/MASTER_PROMPT.md section 5) as numbers. Change looks here, not in templates.
export const FONTS = {
  heading: 'Anton',                 // bold condensed sans (SIL OFL, from cinema/fonts)
  accent: 'Instrument Serif',       // italic serif accent word (SIL OFL)
  ui: 'Inter',
};

// Semantic colors: green = money/growth/life, red = debt/danger, yellow = creativity/music,
// orange = obsession/intensity, white = neutral.
export const COLORS: Record<string, string> = {
  green: '#3fd16f', red: '#ff2b2b', yellow: '#ffd21f', orange: '#ff8a1c', white: '#f4f1ea',
};
export const INK = '#141414';           // "white" text on light paper becomes ink
export const PAPER = '#e7e3d9';
export const NIGHT = '#0b0b0e';

export const color = (name?: string) => COLORS[name || 'white'] || COLORS.white;
export const textColor = (semantic: string, light: boolean) => (light && semantic === 'white' ? INK : color(semantic));
export const glow = (hex: string, strength = 1) =>
  `0 0 ${10 * strength}px ${hex}cc, 0 0 ${28 * strength}px ${hex}88, 0 0 ${64 * strength}px ${hex}44`;

export const GRADES: Record<string, string> = {
  bw: 'grayscale(1) contrast(1.32) brightness(0.92)',
  color: 'saturate(1.12) contrast(1.08)',
};

/** Deterministic pseudo-random numbers, so every render of a beat is identical (needed for the beat cache). */
export function rng(seed: number) {
  let s = (seed * 9301 + 49297) % 233280 || 1;
  return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
}
