// The track list for each clip, fetched once when the clip opens (prefetchMusic), so the Music tab shows it at once
export const trackLists = new Map();
export const trackKey = (projectId, clip) => `${projectId}:${clip.job_id}:${clip.clip_index}`;

export function prefetchMusic(api, projectId, clip) {
  const key = trackKey(projectId, clip);
  if (!trackLists.has(key)) {
    const request = api.listAudioAssets(projectId, clip.job_id, clip.clip_index).then((data) => {
      request.settled = data.assets;   // kept so the tab can draw the list straight away next time
      return data.assets;
    });
    trackLists.set(key, request);
    request.catch(() => trackLists.delete(key));
  }
  return trackLists.get(key);
}
