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
 * GET /api/projects/{projectId}/editor
 * The clips you can edit, grouped by the AI Studio session ("wave") they came from.
 * @returns {Promise<{ sessions: { job_id, prompt, clips: { job_id, clip_index, start, end, title }[] }[],
 *                     selection: { job_id, clip_index } | null }>}  selection = the clip you last edited
 */
export function getEditorIndex(token, projectId) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/editor`, { token });
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
