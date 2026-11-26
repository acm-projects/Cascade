import { isDemoFiles } from "../demo";
import { apiFetch, apiUpload } from "./client";

// AI Studio: backend/studio.py (Kashmine). Everything lives under /api/projects/{projectId}/studio.
//
// The studio "document" looks like:
//   { project: { id, name },
//     sessions: [{ id, name, source_job, job_ids: [...], messages: [{ id, role, text, job_id?, references? }],
//                  positions: { "<node id>": { x, y } }, viewport, references: [ClipRef], clip_revisions }],
//     active_session_id,
//     editor_clips: [ClipRef] }       the checked clips: AI context AND what goes to the Editor
// A ClipRef is { job_id, clip_index }. The clips themselves come from listGenerations() (api/generations.js).

const studioPath = (projectId) => `/api/projects/${encodeURIComponent(projectId)}/studio`;

/**
 * GET /api/projects/{projectId}/studio - the whole studio document (creates a "Main session" if there are none)
 * @returns {Promise<StudioDocument>}
 */
export function getStudio(token, projectId) {
  return apiFetch(studioPath(projectId), { token });
}

/**
 * POST .../studio/sessions   body: { name (1-80 chars) }
 * Each new session starts empty and accepts its own uploaded video. Max 30 sessions.
 * @returns {Promise<Session>} status 201
 */
export function createStudioSession(token, projectId, name) {
  return apiFetch(`${studioPath(projectId)}/sessions`, {
    token, method: "POST", body: { name },
  });
}

/**
 * PATCH .../studio/sessions/{sessionId}   body: { name }
 * @returns {Promise<Session>}
 */
export function renameStudioSession(token, projectId, sessionId, name) {
  return apiFetch(`${studioPath(projectId)}/sessions/${encodeURIComponent(sessionId)}`, {
    token, method: "PATCH", body: { name },
  });
}

/**
 * PATCH .../studio/sessions/{sessionId}/state - save where boxes were dragged (and/or the zoom).
 * body: { positions?: { "source:<job>" | "generation:<job>" | "clip:<job>:<index>": { x, y } }, viewport?: { x, y, zoom } }
 * Only ids that exist in this session are accepted. Also marks the session as active.
 * @returns {Promise<{ saved: true }>}
 */
export function saveStudioState(token, projectId, sessionId, patch) {
  return apiFetch(`${studioPath(projectId)}/sessions/${encodeURIComponent(sessionId)}/state`, {
    token, method: "PATCH", body: patch,
  });
}

/**
 * PUT .../studio/editor-selection   body: { clips: [ClipRef] } (up to 100)
 * The checked clips. They guide the next AI request and are what the Editor opens.
 * @returns {Promise<{ clips: ClipRef[] }>}
 */
export function setEditorSelection(token, projectId, clips) {
  return apiFetch(`${studioPath(projectId)}/editor-selection`, { token, method: "PUT", body: { clips } });
}

/**
 * POST .../studio/sessions/{sessionId}/generate - a prompt on a session that already has its video.
 * body: { prompt, clip_count: 1-12, clip_length: 5 | 15 | 30 | 60 (seconds per clip; 5 = short moments), references: [ClipRef] (checked clips, max 12),
 *         operation: "generate" | "revise" ("revise" = find more like the checked clips), request_id }
 * Sending the same request_id twice never starts a second (paid) job.
 * @returns {Promise<{ job_id: string }>} status 202
 */
export function studioGenerate(token, projectId, sessionId, body) {
  return apiFetch(`${studioPath(projectId)}/sessions/${encodeURIComponent(sessionId)}/generate`, {
    token, method: "POST", body,
  });
}

/**
 * POST .../studio/sessions/{sessionId}/upload   (multipart form) - the FIRST prompt: uploads the footage too.
 * videos: one or more files; several are joined end to end into one source on the server.
 * onProgress(percent) is called while the files upload.
 * @returns {Promise<{ job_id: string }>} status 202
 */
// Demo mode (demo_final branch): the hike recordings are already joined and searched on the server, so only their
// names are sent (about 19 GB would otherwise upload). Any other files upload as usual.
function demoStandIns(videos) {
  const list = Array.from(videos || []);
  if (!isDemoFiles(list)) return list;
  return list.map((video) => new File([new Uint8Array(1)], video.name, { type: video.type || "video/mp4" }));
}

export function studioUpload(token, projectId, sessionId, { videos, prompt, clipCount, clipLength = 30, requestId, onProgress }) {
  const form = new FormData();
  for (const video of demoStandIns(videos)) form.append("video", video);
  form.append("prompt", prompt);
  form.append("clip_count", String(clipCount));
  form.append("clip_length", String(clipLength));
  form.append("request_id", requestId);
  return apiUpload(`${studioPath(projectId)}/sessions/${encodeURIComponent(sessionId)}/upload`, {
    token, form, onProgress,
  });
}

/**
 * GET a protected media file whole (a clip's clip_url like "/clips/<job>/clip_1.mp4", or
 * "/api/projects/<id>/source/<job>" for the original). Only for code that needs the bytes
 * (filmstrip frames, audio waveforms); to play a video use mediaUrl, which streams.
 * @returns {Promise<Blob>}
 */
export function getMedia(token, path) {
  if (!path.startsWith("/clips/") && !path.startsWith("/api/projects/")) {
    return Promise.reject(new Error("Invalid media address."));
  }
  return apiFetch(path, { token });
}

/**
 * A link to play a protected video or audio file in a <video>/<audio> tag. Those tags can't send the
 * sign-in token, so the backend signs a short-lived link for this one file; the browser then streams it
 * in pieces (and can seek) instead of downloading the whole file into memory first.
 * @returns {Promise<string>}
 */
export async function mediaUrl(token, path) {
  if (!path.startsWith("/clips/") && !path.startsWith("/api/projects/")) {
    throw new Error("Invalid media address.");
  }
  const { url } = await apiFetch(`/api/media-link?path=${encodeURIComponent(path)}`, { token });
  return url;
}
