import { apiFetch } from "./client";

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
 * POST .../studio/sessions   body: { name (1-80 chars), source_job? }
 * Reuse the current session's source_job so the new session works on the same video. Max 30 sessions.
 * @returns {Promise<Session>} status 201
 */
export function createStudioSession(token, projectId, name, sourceJob = null) {
  return apiFetch(`${studioPath(projectId)}/sessions`, {
    token, method: "POST", body: { name, source_job: sourceJob },
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
 * body: { prompt, clip_count: 1-12, references: [ClipRef] (checked clips, max 12),
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
 * POST .../studio/sessions/{sessionId}/upload   (multipart form) - the FIRST prompt: uploads the video too.
 * @returns {Promise<{ job_id: string }>} status 202
 */
export function studioUpload(token, projectId, sessionId, { video, prompt, clipCount, requestId }) {
  const form = new FormData();
  form.append("video", video);
  form.append("prompt", prompt);
  form.append("clip_count", String(clipCount));
  form.append("request_id", requestId);
  return apiFetch(`${studioPath(projectId)}/sessions/${encodeURIComponent(sessionId)}/upload`, {
    token, method: "POST", form,
  });
}

/**
 * GET a protected video file (a clip's clip_url like "/clips/<job>/clip_1.mp4", or
 * "/api/projects/<id>/source/<job>" for the original). Videos can't send the sign-in token on
 * their own, so we download them with it and play the downloaded copy.
 * @returns {Promise<Blob>}
 */
export function getMedia(token, path) {
  if (!path.startsWith("/clips/") && !path.startsWith("/api/projects/")) {
    return Promise.reject(new Error("Invalid media address."));
  }
  return apiFetch(path, { token });
}
