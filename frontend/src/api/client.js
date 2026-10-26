// The ONE place in the app that calls fetch(). Every other api/ file goes through apiFetch().
// Backend paths (/api, /upload, /jobs, /clips) are forwarded to FastAPI by the Vite proxy.

const SERVER_DOWN = "Can't reach the server. Is the backend running?";

// Thrown when the backend says no. Check error.status (401 = not signed in, 404 = not found, ...)
// and show error.message to the user (it's the backend's "detail" text).
export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Call the backend.
 * @param {string} path       e.g. "/api/projects"
 * @param {object} [options]
 * @param {string|null} [options.token]  Clerk token; adds "Authorization: Bearer <token>" (null in dev mode)
 * @param {string} [options.method]      "GET" (default), "POST", "PUT", "DELETE"
 * @param {any} [options.body]           sent as JSON
 * @param {FormData} [options.form]      sent as a file upload instead of JSON
 * @returns {Promise<any>} parsed JSON, or a Blob for files (videos, zips)
 */
export async function apiFetch(path, { token, method = "GET", body, form } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch {
    // fetch only throws when it can't reach the server at all
    throw new ApiError(0, SERVER_DOWN);
  }

  const isJson = res.headers.get("content-type")?.includes("json");
  const data = isJson ? await res.json() : await res.blob();

  if (!res.ok) {
    // 502-504 with no message from FastAPI = the Vite proxy couldn't reach the backend
    const proxyFailed = !isJson && res.status >= 502 && res.status <= 504;
    throw new ApiError(res.status, (isJson && data?.detail) || (proxyFailed ? SERVER_DOWN : res.statusText));
  }
  return data;
}
