import { useEffect, useState } from "react";
import useApi from "../../api/useApi";
import { clipMediaPath } from "./clips";
import { filmstripTimes } from "./timelineMath";

const FRAME_COUNT = 30;    // frames grabbed per clip
const FRAME_HEIGHT = 96;   // pixels: sharp enough for a small tile, and small to keep in memory
const SEEK_TIMEOUT = 8000; // give up on a frame the browser can't reach

// Frames we already grabbed, so switching clips or layouts doesn't grab them again.
// clip key -> { frames, aspect, listeners }
const strips = new Map();

// Wait for one event from the video
function waitFor(video, eventName) {
  return new Promise((resolve, reject) => {
    const finish = (done) => {
      clearTimeout(timer);
      video.removeEventListener(eventName, onEvent);
      video.removeEventListener("error", onError);
      done();
    };
    const onEvent = () => finish(resolve);
    const onError = () => finish(() => reject(new Error("The video couldn't be read")));
    const timer = setTimeout(() => finish(() => reject(new Error("The video took too long"))), SEEK_TIMEOUT);
    video.addEventListener(eventName, onEvent);
    video.addEventListener("error", onError);
  });
}

// Play the clip in a hidden <video>, jump to each time and draw that frame into a small picture
async function grabFrames(blob, duration, strip) {
  const url = URL.createObjectURL(blob);
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = url;
  try {
    await waitFor(video, "loadeddata");
    if (!video.videoWidth) return;   // an audio recording has no frames
    const canvas = document.createElement("canvas");
    canvas.height = FRAME_HEIGHT;
    canvas.width = Math.round(FRAME_HEIGHT * (video.videoWidth / video.videoHeight));
    const context = canvas.getContext("2d");
    strip.aspect = video.videoWidth / video.videoHeight;
    for (const time of filmstripTimes(duration, FRAME_COUNT)) {
      const seeked = waitFor(video, "seeked");
      video.currentTime = time;
      await seeked;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      strip.frames = [...strip.frames, canvas.toDataURL("image/jpeg", 0.6)];
      strip.listeners.forEach((listener) => listener());   // frames appear left to right as they're ready
    }
  } finally {
    video.removeAttribute("src");
    video.load();
    URL.revokeObjectURL(url);
  }
}

// The clip's frames for the timeline: { frames: [picture URLs], aspect: width / height, total }
export default function useFilmstrip(projectId, clip, duration, enabled = true) {
  const api = useApi();
  const key = `${projectId}:${clip.job_id}:${clip.clip_index}`;
  const [, redraw] = useState(0);

  useEffect(() => {
    if (!enabled) return undefined;
    let strip = strips.get(key);
    if (!strip) {
      strip = { frames: [], aspect: 0, listeners: new Set() };
      strips.set(key, strip);
      const started = strip;
      api.getMedia(clipMediaPath(projectId, clip))
        .then((blob) => grabFrames(blob, duration, started))
        .catch(() => {
          // Keep any frames we got. With none, forget it so the next visit tries again; the track shows its lines.
          if (!started.frames.length) strips.delete(key);
        });
    }
    const listener = () => redraw((n) => n + 1);
    strip.listeners.add(listener);
    listener();
    return () => strip.listeners.delete(listener);
  }, [api, key, projectId, clip, duration, enabled]);

  const strip = enabled ? strips.get(key) : null;
  return { frames: strip?.frames ?? [], aspect: strip?.aspect ?? 0, total: FRAME_COUNT };
}
