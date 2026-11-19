// The clip's latest Trend Analysis, fetched when the clip opens in the Editor, so Trends opens with it already there.
const records = new Map();   // key -> Promise<record>, with .settled once it arrives
const key = (projectId, clip) => `${projectId}:${clip.job_id}:${clip.clip_index}`;

export function prefetchTrends(api, projectId, clip) {
  const k = key(projectId, clip);
  if (!records.has(k)) {
    const request = api.getTrends(projectId, clip.job_id, clip.clip_index).then((record) => { request.settled = record; return record; });
    request.catch(() => records.delete(k));
    records.set(k, request);
  }
  return records.get(k);
}

export function cachedTrends(projectId, clip) {
  return records.get(key(projectId, clip))?.settled ?? null;
}

export function forgetTrends(projectId, clip) {
  records.delete(key(projectId, clip));
}
