import { useEffect, useState, useSyncExternalStore } from "react";
import { cachedDraft, draftKey } from "./draftCache";

// A finished AI edit is one fixed video file. Fetch it once per version and share it between the Editor's player,
// the edited timeline and Trends, so none of them waits on it again.
const films = new Map();   // key -> Promise<object URL>

function filmKey(projectId, clip, state) {
  return `${projectId}:${clip.job_id}:${clip.clip_index}:${state.ai_edit.version}:${state.composition?.ratio ?? "original"}`;
}

export function loadAIFilm(api, projectId, clip, state) {
  const key = filmKey(projectId, clip, state);
  if (!films.has(key)) {
    const request = api.exportClip(projectId, clip.job_id, clip.clip_index, { ...state, preview: true, resolution: "540p" })
      .then((blob) => URL.createObjectURL(blob));
    request.catch(() => films.delete(key));
    films.set(key, request);
  }
  return films.get(key);
}

/** The AI edit's file as an object URL (null until it arrives), or null when the clip has no AI edit. */
export function useAIFilm(api, projectId, clip, state) {
  const key = state?.ai_edit ? filmKey(projectId, clip, state) : null;
  const [film, setFilm] = useState({ key: null, url: null });
  useEffect(() => {
    if (!key) return undefined;
    let active = true;
    loadAIFilm(api, projectId, clip, state).then((url) => { if (active) setFilm({ key, url }); }).catch(() => {});
    return () => { active = false; };
  }, [api, projectId, clip, state, key]);
  return film.key === key ? film.url : null;
}

/** A few still frames from a video URL (for the edited timeline's filmstrip). */
export function useVideoFrames(url, count = 10) {
  const [frames, setFrames] = useState({ url: null, list: [], aspect: 16 / 9 });
  useEffect(() => {
    if (!url) return undefined;
    let active = true;
    const video = document.createElement("video");
    video.muted = true; video.preload = "auto"; video.src = url;
    const canvas = document.createElement("canvas");
    const list = [];
    const seekTo = (t) => new Promise((resolve) => { video.onseeked = resolve; video.currentTime = t; });
    (async () => {
      await new Promise((resolve, reject) => { video.onloadeddata = resolve; video.onerror = reject; });
      const aspect = video.videoWidth / video.videoHeight || 16 / 9;
      canvas.height = 90; canvas.width = Math.round(90 * aspect);
      for (let i = 0; i < count && active; i += 1) {
        await seekTo(((i + 0.5) / count) * video.duration);
        canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
        list.push(canvas.toDataURL("image/jpeg", 0.7));
        if (active) setFrames({ url, list: [...list], aspect });
      }
    })().catch(() => {});
    return () => { active = false; video.removeAttribute("src"); video.load(); };
  }, [url, count]);
  return frames.url === url ? frames : { list: [], aspect: 16 / 9 };
}

// ---------- a clip's length as people see it: the AI edit's length once there is one ----------
const CHANGED = "cascade:clip-length";

export function announceClipLength() {
  window.dispatchEvent(new Event(CHANGED));
}

function subscribe(callback) {
  window.addEventListener(CHANGED, callback);
  return () => window.removeEventListener(CHANGED, callback);
}

export function clipLength(projectId, clip) {
  const edited = cachedDraft(draftKey(projectId, clip.job_id, clip.clip_index))?.state?.ai_edit?.duration;
  return edited ?? clip.end - clip.start;
}

export function useClipLength(projectId, clip) {
  return useSyncExternalStore(subscribe, () => clipLength(projectId, clip));
}
