// The Export page's left list: AI Studio session -> wave (one prompt's results) -> clips.
// Takes clips from flattenClips(), in their order, and returns
//   [{ name: "Main session", waves: [{ id, name: "Wave 1", prompt, clips: [clip, …] }] }]
export function exportTree(clips) {
  const sessions = [];
  for (const clip of clips) {
    const name = clip.studioSession || "Main session";
    const id = clip.studioSessionId || `legacy:${name}`;
    let session = sessions.find((s) => s.id === id);
    if (!session) sessions.push((session = { id, name, waves: [] }));
    let wave = session.waves.find((w) => w.id === clip.waveId);
    if (!wave) {
      wave = { id: clip.waveId, name: `Wave ${session.waves.length + 1}`, prompt: clip.wavePrompt, clips: [] };
      session.waves.push(wave);
    }
    wave.clips.push(clip);
  }
  return sessions;
}
