// Development-only examples for CAS-26. No API calls or paid generation required.
const demoVideo = new URL("../../assets/studio-demo.webm", import.meta.url).href;
export function mockNodes(actions = {}) {
  return [
    { id: "demo-source", type: "source", position: { x: 0, y: 180 }, data: {
      title: "Interview.mp4", durationSeconds: 245, status: "ready", ...actions,
    } },
    { id: "demo-done", type: "prompt", position: { x: 400, y: 0 }, data: {
      prompt: "Find the funniest moments", clipCount: 2, state: "done", number: 1,
      referenceNumbers: [2, 4], ...actions,
    } },
    { id: "demo-processing", type: "prompt", position: { x: 400, y: 240 }, data: {
      prompt: "Find a stronger ending", clipCount: 0, state: "processing", number: 2,
      message: "Finding candidate moments…", ...actions,
    } },
    { id: "demo-error", type: "prompt", position: { x: 400, y: 480 }, data: {
      prompt: "Find the next reaction", clipCount: 0, state: "error", number: 3,
      message: "Generation failed. Try again.", ...actions,
    } },
    { id: "demo-clip", type: "clip", position: { x: 820, y: 0 }, data: {
      jobId: "demo", clipIndex: 0, title: "A surprising answer and everyone's reaction",
      start: 41, end: 72, clipUrl: demoVideo, selectionNumber: 3, grade: { score: 88, letter: "A" }, ...actions,
    } },
    { id: "demo-unselected", type: "clip", position: { x: 820, y: 380 }, data: {
      jobId: "demo", clipIndex: 1, title: "The follow-up question", start: 94, end: 121,
      clipUrl: demoVideo, selectionNumber: null, grade: null, ...actions,
    } },
  ];
}

export const mockEdges = [
  { id: "demo-e1", source: "demo-source", target: "demo-done", type: "vine" },
  { id: "demo-e2", source: "demo-source", target: "demo-processing", type: "vine", animated: true },
  { id: "demo-e3", source: "demo-source", target: "demo-error", type: "vine" },
  { id: "demo-e4", source: "demo-done", target: "demo-clip", type: "vine" },
  { id: "demo-e5", source: "demo-done", target: "demo-unselected", type: "vine" },
];
