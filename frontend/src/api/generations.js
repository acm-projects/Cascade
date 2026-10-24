import { apiFetch } from "./client";

// AI Studio clip generation: backend/project_actions.py and app1.py (/upload, /jobs)
// Generating is an async job: the backend answers 202 { job_id } right away,
// then you poll getJob(job_id) (see hooks/useJobPolling.js) until state is "done" or "error".

/**
 * POST /upload   (multipart form) - the first generation for a video file.
 * @param {object} fields
 * @param {File} fields.video
 * @param {string} fields.search      the prompt
 * @param {string} fields.projectId
 * @param {number} [fields.clipCount] 1-12 (default 4)
 * @param {string} [fields.engine]    "agent" (default), "visual" or "speech"
 * @returns {Promise<{ job_id: string }>} status 202
 */
export function uploadVideo(token, { video, search, projectId, clipCount = 4, engine = "agent" }) {
  const form = new FormData();
  form.append("video", video);
  form.append("search", search);
  form.append("project_id", projectId);
  form.append("clip_count", String(clipCount));
  form.append("engine", engine);
  return apiFetch("/upload", { token, method: "POST", form });
}

/**
 * GET /api/projects/{projectId}/generations
 * Every generation in the project, grouped into "waves" for the AI Studio canvas.
 * Each group: { job_id, kind: "generation", state, message, prompt, order, search_type: "full-video" | "follow-up",
 *               clips: [{ clip_id: "<job_id>:<index>", clip_index, start, end, title, ... }], ... }
 * @returns {Promise<{ groups: object[] }>}
 */
export function listGenerations(token, projectId) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/generations`, { token });
}

/**
 * POST /api/projects/{projectId}/generations - a new prompt on a video that's already uploaded.
 * body: { prompt (1-2000 chars), source_job, request_id, clip_count?: 1-12, engine?: "agent",
 *         parent_job?, parent_clip_index? }   (parent_* = "find more like this clip")
 * request_id is any unique id you make up (letters, digits, _ or -): sending the same one twice
 * won't start a second paid job.
 * @returns {Promise<{ job_id: string }>} status 202
 */
export function createGeneration(token, projectId, body) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/generations`, {
    token,
    method: "POST",
    body,
  });
}

/**
 * POST /api/projects/{projectId}/generations/{jobId}/retry   body: { request_id }
 * Re-runs a generation that failed. 409 if it already finished.
 * @returns {Promise<{ job_id: string }>} status 202
 */
export function retryGeneration(token, projectId, jobId, requestId) {
  return apiFetch(
    `/api/projects/${encodeURIComponent(projectId)}/generations/${encodeURIComponent(jobId)}/retry`,
    { token, method: "POST", body: { request_id: requestId } }
  );
}

/**
 * GET /jobs/{jobId} - "is it ready yet?" for a generation.
 * While running: { state: "queued" | "processing", message, clips: [...] }
 * Finished:      { state: "done", message, clips: [...], steps_log, selection_note, ... }
 * Failed:        { state: "error", message }
 * @returns {Promise<{ state: string, message: string, clips?: object[] }>}
 */
export function getJob(token, jobId) {
  return apiFetch(`/jobs/${encodeURIComponent(jobId)}`, { token });
}
