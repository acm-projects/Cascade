import { apiFetch } from "./client";

// "Feature" jobs (research, caption styles): backend/integration.py
// Same idea as generations: start one, get { job_id }, then poll getFeature(job_id).

/**
 * GET /api/features/{jobId}
 * Running:  { state: "queued" | "processing", message, ... }
 * Finished: { state: "done", clips: [...], ... }
 * Failed:   { state: "error", message }
 * @returns {Promise<{ state: string, message?: string, clips?: object[] }>}
 */
export function getFeature(token, jobId) {
  return apiFetch(`/api/features/${encodeURIComponent(jobId)}`, { token });
}

/**
 * POST /api/features/{jobId}/cancel
 * Asks a running job to stop after its current step. 409 if it already finished.
 * @returns {Promise<{ message: string }>}
 */
export function cancelFeature(token, jobId) {
  return apiFetch(`/api/features/${encodeURIComponent(jobId)}/cancel`, { token, method: "POST" });
}
