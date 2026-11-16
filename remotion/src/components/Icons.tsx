// Simple line icons for SPEAKER_CUTOUT_ICONS, chosen from the words of the beat. Original drawings.
const PATHS: Record<string, string> = {
  leaf: 'M12 2C6 6 4 11 6 17c1 3 4 5 6 5 0-6 2-11 8-15-5 0-9 3-11 7 0-5 1-8 3-12z',
  butterfly: 'M12 8c-2-4-7-6-9-4s0 7 4 8c-3 1-4 5-2 6s5-1 7-5c2 4 5 6 7 5s1-5-2-6c4-1 6-6 4-8s-7 0-9 4z',
  flower: 'M12 9a3 3 0 1 0 0.01 0M12 2c2 0 3 3 0 6-3-3-2-6 0-6zm0 20c-2 0-3-3 0-6 3 3 2 6 0 6zM2 12c0-2 3-3 6 0-3 3-6 2-6 0zm20 0c0 2-3 3-6 0 3-3 6-2 6 0z',
  frog: 'M6 10a3 3 0 1 1 4-3h4a3 3 0 1 1 4 3c2 1 3 3 3 5 0 4-4 6-9 6s-9-2-9-6c0-2 1-4 3-5zm2 6c2 2 6 2 8 0',
  note: 'M9 18a3 3 0 1 1-2-2.8V4l12-2v13a3 3 0 1 1-2-2.8V6l-8 1.3z',
  dollar: 'M12 2v20M17 6c-1-2-3-2-5-2-3 0-5 1-5 4 0 6 10 3 10 9 0 2-2 3-5 3-2 0-4-1-5-3',
  star: 'M12 2l3 7 7 .6-5.4 4.7L18.2 21 12 17.3 5.8 21l1.6-6.7L2 9.6 9 9z',
  globe: 'M12 2a10 10 0 1 0 .01 0M2 12h20M12 2c3 3 4 6 4 10s-1 7-4 10c-3-3-4-6-4-10s1-7 4-10z',
  heart: 'M12 21C5 15 2 12 2 8a5 5 0 0 1 10-1 5 5 0 0 1 10 1c0 4-3 7-10 13z',
  spark: 'M12 2l1.8 7.2L21 12l-7.2 1.8L12 21l-1.8-7.2L3 12l7.2-1.8z',
};
const THEMES: [RegExp, string[]][] = [
  [/life|nature|jungle|forest|species|bio|animal|plant|organism|green|proliferation/i, ['leaf', 'butterfly', 'flower', 'frog', 'spark']],
  [/music|song|sing|band|guitar|rap/i, ['note', 'note', 'spark', 'star']],
  [/money|dollar|cash|rich|debt|pay|price|finance/i, ['dollar', 'dollar', 'spark', 'star']],
  [/love|heart|family|friend/i, ['heart', 'spark', 'star']],
  [/world|earth|planet|travel/i, ['globe', 'spark', 'star']],
];
export function iconsFor(text: string) {
  return (THEMES.find(([re]) => re.test(text)) || [null, ['spark', 'star', 'spark']])[1];
}
export function Icon({ name, size, color, style }: { name: string; size: number; color: string; style?: object }) {
  return <svg viewBox="0 0 24 24" width={size} height={size} style={style}>
    <path d={PATHS[name] || PATHS.spark} fill={color} fillOpacity={0.9} stroke={color} strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}
