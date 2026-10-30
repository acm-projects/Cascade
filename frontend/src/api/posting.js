import { apiFetch } from "./client";

// Posting a clip: backend/post_metadata.py and backend/social_youtube.py (Manila).
// Each clip is named by its generation job (jobId) and position (index), like in api/editor.js.

function clipPath(projectId, jobId, index) {
  return `/api/projects/${encodeURIComponent(projectId)}/editor/${encodeURIComponent(jobId)}/${index}`;
}

// ---------- Post copy (title, caption, hashtags) ----------

/**
 * GET .../editor/{jobId}/{index}/post - the saved post copy (or a starter using the clip's title)
 * @returns {Promise<{ name: string, caption: string, hashtags: string[], cover_time: number | null }>}
 */
export function getPost(token, projectId, jobId, index) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/post`, { token });
}

/**
 * PUT .../editor/{jobId}/{index}/post   body: { name (≤160), caption (≤5000), hashtags (≤30), cover_time }
 * Hashtags come back cleaned up ("#funny", no duplicates).
 * @returns {Promise<PostMetadata>}
 */
export function savePost(token, projectId, jobId, index, post) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/post`, { token, method: "PUT", body: post });
}

/**
 * POST .../editor/{jobId}/{index}/post/generate   body: { action, metadata }
 * action: "generate" (write a caption + hashtags), "rewrite" (improve the caption), "tags" (suggest hashtags).
 * Uses the clip's transcript. Needs OPENAI_API_KEY on the server (503 otherwise). Doesn't save anything.
 * @returns {Promise<{ caption: string, hashtags: string[] }>}
 */
export function generatePost(token, projectId, jobId, index, action, metadata) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/post/generate`, {
    token, method: "POST", body: { action, metadata },
  });
}

// ---------- YouTube ----------

/**
 * GET /api/projects/{projectId}/social/youtube - is a YouTube channel connected?
 * Fails (503) when the server has no Google keys (GOOGLE_YOUTUBE_CLIENT_ID/SECRET in .env).
 * @returns {Promise<{ connected: boolean, channel: string | null, can_schedule: boolean }>}
 */
export function getYoutubeConnection(token, projectId) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/social/youtube`, { token });
}

/**
 * POST /api/projects/{projectId}/social/youtube/connect
 * @returns {Promise<{ url: string }>} Google's sign-in page; open it, and Google sends you back to the server
 */
export function connectYoutube(token, projectId) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/social/youtube/connect`, { token, method: "POST" });
}

/**
 * POST .../editor/{jobId}/{index}/publish/youtube
 * body: { title (1-100), description, privacy: "private" | "unlisted" | "public", submission_id (a UUID),
 *         edit (the clip's draft state, rendered first), hashtags }
 * Re-sending the same submission_id never uploads twice.
 * @returns {Promise<{ status: "Rendering" | "Uploading" | "Processing" | "Public" | "Private" | "Failed" | ..., url?, error? }>}
 */
export function publishYoutube(token, projectId, jobId, index, body) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/publish/youtube`, { token, method: "POST", body });
}

/**
 * GET .../editor/{jobId}/{index}/publish/youtube - how the upload is going ({ status: "Ready" } if never started)
 */
export function getYoutubeStatus(token, projectId, jobId, index) {
  return apiFetch(`${clipPath(projectId, jobId, index)}/publish/youtube`, { token });
}
