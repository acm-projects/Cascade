import { continueRender, delayRender, staticFile } from 'remotion';

const FILES: [string, string, Record<string, string>][] = [
  ['Anton', 'fonts/Anton-Regular.ttf', {}],
  ['Instrument Serif', 'fonts/InstrumentSerif-Italic.ttf', { style: 'italic' }],
  ['Instrument Serif', 'fonts/InstrumentSerif-Regular.ttf', {}],
  ['Inter', 'fonts/Inter.ttf', { weight: '100 900' }],
];

let loading: Promise<unknown> | null = null;

/** Load the bundled fonts once and hold the render until they are ready (text never falls back to a system font). */
export function useFonts() {
  if (typeof document === 'undefined') return;
  if (!loading) {
    const handle = delayRender('Loading fonts');
    loading = Promise.all(FILES.map(([family, file, descriptors]) =>
      new FontFace(family, `url(${staticFile(file)})`, descriptors).load().then(face => document.fonts.add(face))))
      .then(() => continueRender(handle))
      .catch(error => { console.error('font load failed', error); continueRender(handle); });
  }
}
