import { createContext, useContext } from "react";

export const LeafTransitionContext = createContext(null);

// AI Studio, the Editor and Export call this once they're fully loaded, so the waterfall page change
// (style "falls") knows it can fall away and show them. Harmless when no page change is running.
export const PAGE_READY = "cascade:page-ready";
export function markPageReady() {
  window.dispatchEvent(new Event(PAGE_READY));
}

// Go to another page with a camera move through the 3D world:
//   const leafNavigate = useLeafNavigate();
//   leafNavigate("/somewhere", { state, ready, style });
// "ready" is optional: a promise to wait for while the screen is covered (like downloading the next page).
// "style" is "push" (the default: the underwater camera pushes forward, used when opening a project)
// "dive" (the island camera zooms down into the sea, used by Landing's Get Started)
// "rise" (the underwater camera swims up to the surface, used by "How it works")
// or "falls" (a waterfall covers the screen while AI Studio, the Editor or Export loads; see markPageReady).
export function useLeafNavigate() {
  return useContext(LeafTransitionContext);
}
