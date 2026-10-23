// Sizes and placement for nodes on the AI Studio canvas (in canvas pixels, before zoom)
export const SOURCE_SIZE = { w: 340, h: 300 };   // the dropped video
export const CLIP_SIZE = { w: 300, h: 190 };     // each generated clip
const COLUMN_GAP = 170;                          // space between the video and the first column of clips
const BATCH_GAP = 110;                           // space between columns (one column per prompt)
const ROW_GAP = 40;                              // space between clips in a column

// Where the clips from one prompt go: a column to the right of the video, centered on it
export function layoutBatch(sourcePos, batchIndex, count) {
  const x = sourcePos.x + SOURCE_SIZE.w + COLUMN_GAP + batchIndex * (CLIP_SIZE.w + BATCH_GAP);
  const total = count * CLIP_SIZE.h + (count - 1) * ROW_GAP;
  const top = sourcePos.y + SOURCE_SIZE.h / 2 - total / 2;
  return Array.from({ length: count }, (_, i) => ({ x, y: top + i * (CLIP_SIZE.h + ROW_GAP) }));
}

// "Arrange": put every clip back into tidy columns, one per prompt
export function arrangeClips(clips, sourcePos) {
  const batches = [...new Set(clips.map((clip) => clip.batch))];
  return clips.map((clip) => {
    const batchClips = clips.filter((c) => c.batch === clip.batch);
    const spots = layoutBatch(sourcePos, batches.indexOf(clip.batch), batchClips.length);
    return { ...clip, ...spots[batchClips.indexOf(clip)] };
  });
}
