import { createContext, useContext } from 'react';

export type Beat = {
  id: number; start: number; end: number; spoken_text: string; intent: string; template: string;
  emphasis_text: string | null; accent_word: string | null; semantic_color: string;
  background_mode: 'light' | 'dark'; grade: 'bw' | 'color'; transition_in: string;
  broll_query: string | null; broll_fallback_query: string | null;
  data: { number: number | null; place: string | null; screenshot_target: string | null }; sfx: string | null;
};
export type Media = { src: string; kind: 'video' | 'image'; width?: number; height?: number; credit?: string };
export type BeatAssets = {
  broll?: Media[];                                                // one per COLLAGE subject, else one
  cutout?: { dir: string; fps: number; count: number; from: number };  // RGBA PNG frames of the speaker
};
export type RenderProps = {
  plan: { source_window: { start: number; end: number }; beats: Beat[]; [k: string]: unknown };
  fps: number; width: number; height: number;
  source: string;                                                 // public-dir file, frame 0 = source_window.start
  assets: Record<string, BeatAssets>;
  options?: { grain?: boolean; labels?: boolean };
};

/** Where a beat sits: `from` is its first frame in the edit, `offset` the frame its Sequence starts at. */
export type BeatInfo = { beat: Beat; index: number; from: number; length: number; offset: number; assets: BeatAssets; props: RenderProps };
export const BeatContext = createContext<BeatInfo | null>(null);
export const useBeat = () => useContext(BeatContext)!;
