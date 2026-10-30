import { apiFetch } from "./client";

// Projects: backend/routers/projects.py and backend/routers/generations.py
// A project looks like: { id, name, user_id, created_at (unix seconds), saved_clips: [{ job_id, clip_index }] }

/**
 * GET /api/projects
 * @returns {Promise<{ projects: Project[] }>} newest first
 */
export function listProjects(token) {
  return apiFetch("/api/projects", { token });
}

/**
 * POST /api/projects   body: { name } (1-100 characters)
 * @returns {Promise<Project>} the new project (status 201)
 */
export function createProject(token, name) {
  return apiFetch("/api/projects", { token, method: "POST", body: { name } });
}

/**
 * GET /api/projects/{projectId}
 * @returns {Promise<Project & { jobs: Job[] }>} the project plus every job (upload, generation, research...) in it
 */
export function getProject(token, projectId) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, { token });
}

export function updateProject(token, projectId, changes) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, { token, method: "PATCH", body: changes });
}

/**
 * DELETE /api/projects/{projectId}
 * Fails with 409 while a generation or research job in it is still running.
 * @returns {Promise<{ deleted: true, project_id: string, job_ids: string[] }>}
 */
export function deleteProject(token, projectId) {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, { token, method: "DELETE" });
}
