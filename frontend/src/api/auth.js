import { apiFetch } from "./client";

/**
 * GET /api/auth-config (no sign-in needed). Used by AuthGate to choose dev mode or Clerk.
 * @returns {Promise<{ dev_auth?: boolean, publishable_key: string, domain: string }>}
 *          dev_auth only exists once the backend has dev sign-in (CAS-8)
 */
export function getAuthConfig() {
  return apiFetch("/api/auth-config");
}
