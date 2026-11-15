import { createContext, useContext } from "react";

export const LeafTransitionContext = createContext(null);

// Go to another page with a camera move through the 3D world:
//   const leafNavigate = useLeafNavigate();
//   leafNavigate("/somewhere", { state, ready, style });
// "ready" is optional: a promise to wait for while the screen is covered (like downloading the next page).
// "style" is "push" (the default: the underwater camera pushes forward, used when opening a project)
// or "dive" (the island camera zooms down into the sea, used by Landing's Get Started).
export function useLeafNavigate() {
  return useContext(LeafTransitionContext);
}
