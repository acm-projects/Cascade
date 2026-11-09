import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./LeafTransition.css";
import { LeafTransitionContext } from "../context/leafTransitionValue";

// Page changes that feel like a camera moving through the world (like an isometric camera gliding across a model):
//   "dive" (Landing -> Projects): the words fade, the camera glides and zooms down into the splash where the last
//          waterfall meets the sea, the view sinks into deep blue, then on Projects the camera keeps sinking to the sea floor.
//   "push" (Projects -> AI Studio): the cards fade, the underwater camera pushes forward into the beam of light,
//          and AI Studio appears out of the water.
// The 3D scenes do the camera part when they hear a "cascade:camera" event. This file fades the page out,
// covers the swap with a wash of water, and fades it away again.
const MOVES = {
  dive: { camera: 1000, washFrom: 650, hold: 100, reveal: 800, color: "dive" },
  push: { camera: 800, washFrom: 450, hold: 80, reveal: 550, color: "push" },
};
const MAX_WAIT_MS = 4000;   // never keep someone waiting on the next page longer than this

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Wraps the pages. The wash of water lives here, above the pages, so it stays on screen while the page underneath changes.
function LeafTransition({ children }) {
  const navigate = useNavigate();
  const [phase, setPhase] = useState("idle");   // idle -> cover -> reveal -> idle
  const [style, setStyle] = useState("push");
  const running = useRef(false);

  // style: "push" (the default) or "dive" (from Landing). ready: an optional promise to wait for (the next page's code).
  const leafNavigate = useCallback(async (to, { state, ready, style: chosen = "push" } = {}) => {
    if (running.current) return;   // already on the way (a double click)

    // People who turned off animations on their device just go to the page
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      navigate(to, { state });
      return;
    }

    running.current = true;
    const move = MOVES[chosen] ?? MOVES.push;
    setStyle(chosen);
    setPhase("cover");
    document.documentElement.classList.add("is-camera-moving");   // fades the page's words and buttons
    window.dispatchEvent(new CustomEvent("cascade:camera", { detail: { move: chosen === "dive" ? "dive" : "forward", duration: move.camera } }));

    const nextPageReady = Promise.race([Promise.resolve(ready).catch(() => {}), wait(MAX_WAIT_MS)]);
    await Promise.all([wait(move.camera), nextPageReady]);
    if (chosen === "dive") window.cascadeCameraArrive = performance.now();   // Projects' camera sinks down as it appears
    navigate(to, { state });
    document.documentElement.classList.remove("is-camera-moving");
    await wait(move.hold);
    setPhase("reveal");
    await wait(move.reveal);
    setPhase("idle");
    running.current = false;
  }, [navigate]);

  const move = MOVES[style] ?? MOVES.push;
  return (
    <LeafTransitionContext.Provider value={leafNavigate}>
      {children}
      {phase !== "idle" && (
        <div
          className={`camera-transition camera-transition-${move.color} camera-transition-${phase}`}
          style={{ "--wash-from": `${move.washFrom}ms`, "--wash-for": `${move.camera - move.washFrom}ms`, "--reveal-for": `${move.reveal}ms` }}
          aria-hidden="true"
        />
      )}
    </LeafTransitionContext.Provider>
  );
}

export default LeafTransition;
