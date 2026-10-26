// PRETEND AI Studio data, for demos until the backend is wired in (ticket 3.4).
// The video is real (it stays in your browser); the "AI" just picks random moments from it.

export const mockSession = { id: "demo", name: "Session 1" };

// Where things sit on the canvas (React Flow units, before zooming)
export const SOURCE_POSITION = { x: 0, y: 0 };
const PROMPT_X = 500;        // gaps of ~160px between columns leave room for the leafy vines
const CLIP_X = 920;
const CLIP_HEIGHT = 170;    // clip box height + gap
const BATCH_GAP = 60;       // space between one prompt's clips and the next prompt's

// FAKE results: `count` random moments of 2-6 seconds from a video of `duration` seconds
export function makeFakeClips(duration, count) {
  const length = Number.isFinite(duration) && duration > 0 ? duration : 30;
  const clips = [];
  for (let i = 0; i < count; i++) {
    const clipLength = Math.min(2 + Math.random() * 4, length);
    const start = Math.random() * (length - clipLength);
    clips.push({ start, end: start + clipLength });
  }
  return clips.sort((a, b) => a.start - b.start);
}

// Where the next prompt and its clips go: below everything already on the canvas.
// The clips stack in ONE column to the right of the prompt, with the prompt level with
// their middle, so every vine has a clear path to its own clip (none run behind another clip).
export function layoutBatch(prompts, clips, clipCount) {
  const bottoms = [...prompts.map((p) => p.y + 80), ...clips.map((c) => c.y + CLIP_HEIGHT)];
  const top = bottoms.length ? Math.max(...bottoms) + BATCH_GAP : 0;
  const columnMiddle = top + (clipCount * CLIP_HEIGHT) / 2;
  return {
    prompt: { x: PROMPT_X, y: columnMiddle - 40 },
    spots: Array.from({ length: clipCount }, (_, i) => ({ x: CLIP_X, y: top + i * CLIP_HEIGHT })),
  };
}

// Turn the project's video, prompts and clips into React Flow boxes and lines.
// (Ticket 3.3's buildGraph() will do this for real backend data.)
//   video -> each prompt -> that prompt's clips, joined by leafy vines (features/studio/edges)
export function buildPretendGraph({ sourceVideo, prompts, clips, sourceActions }) {
  const nodes = [
    { id: "source", type: "source", position: SOURCE_POSITION, data: { video: sourceVideo, ...sourceActions } },
  ];
  const edges = [];

  for (const prompt of prompts) {
    nodes.push({ id: prompt.id, type: "prompt", position: { x: prompt.x, y: prompt.y }, data: prompt });
    edges.push({ id: `source-${prompt.id}`, type: "vine", source: "source", target: prompt.id });
  }
  for (const clip of clips) {
    const id = `clip-${clip.id}`;
    const promptId = `prompt-${clip.batch}`;
    nodes.push({ id, type: "clip", position: { x: clip.x, y: clip.y }, data: { clip } });
    edges.push({ id: `${promptId}-${id}`, type: "vine", source: promptId, target: id });
  }
  return { nodes, edges };
}
