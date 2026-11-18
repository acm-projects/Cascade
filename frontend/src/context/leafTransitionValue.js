import { createContext, useCallback, useContext } from "react";
import { useLocation } from "react-router-dom";

export const LeafTransitionContext = createContext(null);

// Go to another page with a camera move through the 3D world:
//   const leafNavigate = useLeafNavigate();
//   leafNavigate("/somewhere", { state, ready, style });
// "ready" is optional: a promise to wait for while the screen is covered (like downloading the next page).
// "style" is "push" (the default: the underwater camera pushes forward, used when opening a project)
// "dive" (the island camera zooms down into the sea, used by Landing's Get Started)
// "rise" (the underwater camera swims up to the surface, used by "How it works")
// "falls" (a brief waterfall covers the route swap)
// or "instant" (navigate directly between project steps without an animation).
export function useLeafNavigate() {
  return useContext(LeafTransitionContext);
}

export const WATERFALL_READY = "cascade:waterfall-ready";

export function useWaterfallReady() {
  const { pathname } = useLocation();
  return useCallback(() => {
    window.dispatchEvent(new CustomEvent(WATERFALL_READY, { detail: pathname }));
  }, [pathname]);
}
