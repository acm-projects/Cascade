import { createContext, useContext } from "react";

// Shared by AuthGate (which fills it in) and any component that needs to know about sign-in.
//   mode     - "dev" (no sign-in needed) or "clerk" (real Clerk sign-in)
//   getToken - async function that returns the signed-in user's token (null in dev mode)
export const AuthContext = createContext({ mode: "dev", getToken: async () => null });

export function useAuthMode() {
  return useContext(AuthContext).mode;
}

// The API client (ticket 1.6) uses this to add "Authorization: Bearer <token>" to requests:
//   const getToken = useAuthToken();
//   const token = await getToken();
export function useAuthToken() {
  return useContext(AuthContext).getToken;
}
