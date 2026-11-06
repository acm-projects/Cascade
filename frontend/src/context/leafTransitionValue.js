import { createContext, useContext } from "react";

export const LeafTransitionContext = createContext(null);

// Go to another page with the leaves blowing across the screen:
//   const leafNavigate = useLeafNavigate();
//   leafNavigate("/somewhere", { state, ready });
// "ready" is optional: a promise to wait for while the screen is covered (like downloading the next page).
export function useLeafNavigate() {
  return useContext(LeafTransitionContext);
}
