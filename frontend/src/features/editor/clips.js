// Small helpers shared by the Editor and Export pages.
// (Not in src/api/: useApi() adds the sign-in token to every api function, and these take none.)

/** "<jobId>:<index>": a stable name for one clip */
export const clipKey = (clip) => `${clip.job_id}:${clip.clip_index}`;

/** The address of one clip's video for the editor. Download it with api.getMedia(path). */
export function clipMediaPath(projectId, clip) {
  return `/api/projects/${encodeURIComponent(projectId)}/editor/${encodeURIComponent(clip.job_id)}/${clip.clip_index}/media`;
}

/** Flatten the editor index ({ sessions: [{ clips }] }) into one list, each clip knowing its session */
export function flattenClips(index) {
  return index.sessions.flatMap((session) =>
    session.clips.map((clip) => ({ ...clip, sessionName: session.session_name || session.prompt })));
}

/** Save a Blob (e.g. a rendered MP4 or ZIP) to the user's Downloads folder as `filename` */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

/** "Funny moment!" -> "funny-moment" for file names */
export function fileSafe(text, fallback = "clip") {
  return (text || fallback).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || fallback;
}
