import { apiFetch } from "./client";

// Editor + export: backend/editor_backend.py
// A clip is named by the generation job it came from (jobId) and its position in that job (index, from 0).
//
// An "edit" (the draft state) looks like:
//   { start, end,                                   seconds, trimmed inside the clip
//     captions:    { enabled, font, size, color, stroke, thickness, background, opacity, position, bold },
//     composition: { ratio: "original" | "9:16" | "1:1" | "4:5" | "16:9" | "4:3", mode: "fit" | "fill", x, y, background },
//     effects:     { brightness, contrast, saturation, grayscale },
//     reframe:     { enabled, focus, selection, analysis_id },
//     texts: { [cueId]: "caption text" },  broll: [ ...b-roll segments ] }

function clipPath(projectId, jobId, index) {
  return `/api/projects/${encodeURIComponent(projectId)}/editor/${encodeURIComponent(jobId)}/${index}`;
}

/**
 * GET /api/projects/{projectId}/editor[?selected_only=true]
 * The clips you can edit, grouped by the AI Studio session ("wave") they came from.
 * selectedOnly: only the clips picked in AI Studio (the studio's editor_clips).
 * @returns {Promise<{ sessions: { job_id, prompt, session_name?, clips: { job_id, clip_index, start, end, title }[] }[],
 *                     selection: { job_id, clip_index } | null }>}  selection = the clip to open first
 */
export function getEditorIndex(token, projectId, { selectedOnly = false } = {}) {
  const query = selectedOnly ? "?selected_only=true" : "";
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/editor${query}`, { token });
}

/**
 * GET /api/projects/{projectId}/editor/{jobId}/{index}
 * One clip's details plus its saved draft (or a fresh one).
 * @returns {Promise<{ duration, width, height, cues, burned_in, warning,
 *                     draft: { state: Edit, chat: { role, text }[], updated_at } }>}
 */
export function getDraft(token, projectId, jobId, index) {
  return apiFetch(clipPath(projectId, jobId, index), { token });
}

/**
 * PUT /api/projects/{projectId}/editor/{jobId}/{index}
 * body: { state: Edit, chat: { role: "user" | "assistant", text }[], updated_at: number }
 * @returns {Promise<{ saved: true }>}
 */
export function saveDraft(token, projectId, jobId, index, draft) {
  return apiFetch(clipPath(projectId, jobId, index), { token, method: "PUT", body: draft });
}

/**
 * POST /api/projects/{projectId}/editor/{jobId}/{index}/chat - "make the captions yellow"
 * body: { state: Edit, chat: Message[], message: string (1-2000 chars), result_ids?: string[], selected_segment?: string }
 * @returns {Promise<{ state: Edit, message: string, actions: object[], broll_search: object | null }>}
 *          state = the edit with the AI's changes applied, message = the AI's reply
 */
export function sendEditorChat(token, projectId, jobId, index, body) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/chat`, { token, method: "POST", body });
}

/**
 * POST /api/projects/{projectId}/editor/{jobId}/{index}/export   body: Edit (+ optional overlays)
 * Renders one clip. 409 while automatic framing is still being prepared.
 * @returns {Promise<Blob>} the finished MP4
 */
export function exportClip(token, projectId, jobId, index, edit) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/export`, { token, method: "POST", body: edit });
}

/**
 * POST /api/projects/{projectId}/editor/export-selected
 * body: { clips: [{ job_id, clip_index, edit: Edit }] }   (1-100 clips, no duplicates)
 * @returns {Promise<Blob>} a .zip with one MP4 per clip
 */
export function exportSelected(token, projectId, clips) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/editor/export-selected`, {
    token,
    method: "POST",
    body: { clips },
  });
}

/**
 * POST .../editor/{jobId}/{index}/reframe   body: { composition, focus: "auto", selection: null }
 * Starts the "who is in the frame" analysis that Fill (crop) exports need, so the crop can follow people.
 * Safe to call again: a finished analysis for the same clip is reused (cache_hit).
 * @returns {Promise<{ analysis_id: string, status: "queued" | "processing" | "ready" }>}
 */
export function startReframe(token, projectId, jobId, index, body) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/reframe`, { token, method: "POST", body });
}

/**
 * GET .../editor/{jobId}/{index}/reframe/{analysisId} - how the analysis is going
 * @returns {Promise<{ status: "queued" | "processing" | "ready" | "error", progress: 0-1, message }>}
 */
export function getReframe(token, projectId, jobId, index, analysisId) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/reframe/${encodeURIComponent(analysisId)}`, { token });
}
