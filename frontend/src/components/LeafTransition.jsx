import { useCallback, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "./LeafTransition.css";
import { LeafTransitionContext, PAGE_READY } from "../context/leafTransitionValue";
import WaterfallCurtain from "./WaterfallCurtain";

// Page changes that feel like a camera moving through the world (like an isometric camera gliding across a model):
//   "dive" (Landing -> Projects): the words fade, the camera glides and zooms down into the splash where the last
//          waterfall meets the sea, the view sinks into deep blue, then on Projects the camera keeps sinking to the sea floor.
//   "push" (Projects -> AI Studio): the cards fade, the underwater camera pushes forward into the beam of light,
//          and AI Studio appears out of the water.
//   "falls" (between AI Studio, the Editor and Export): a waterfall pours down over the screen, the next page
//          loads behind it, and the water falls away once that page says it's ready (see WaterfallCurtain.jsx).
//   "rise" (Projects -> How it works): the underwater camera swims up to the bright surface, then on How it works
//          the camera comes down onto the pond from above.
// The 3D scenes do the camera part when they hear a "cascade:camera" event. This file fades the page out,
// covers the swap with a wash of water, and fades it away again.
const MOVES = {
  dive: { camera: 1000, washFrom: 650, hold: 100, reveal: 800, color: "dive" },
  push: { camera: 800, washFrom: 450, hold: 80, reveal: 550, color: "push" },
  rise: { camera: 1000, washFrom: 600, hold: 100, reveal: 800, color: "rise" },
};
const MAX_WAIT_MS = 4000;   // never keep someone waiting on the next page longer than this
const FALLS = { cover: 650, reveal: 750, least: 250, most: 8000 };   // the waterfall: pour in, at least / at most hold, fall away

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// One cartoon leaf drawing.
export function Leaf({ color, preserveAspectRatio }) {
  return (
    <svg viewBox="0 0 100 160" preserveAspectRatio={preserveAspectRatio}>
      <path
        d="M50 3C69 16 81 31 88 47L78 50L93 62C96 76 95 88 90 100L77 99L86 113C78 128 66 143 50 157C34 143 22 128 14 113L23 99L10 100C5 88 4 76 7 62L22 50L12 47C19 31 31 16 50 3Z"
        fill={color.base}
        stroke="#0a4426"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />
      <path d="M50 3C69 16 81 31 88 47L78 50L93 62C96 76 95 88 90 100L77 99L86 113C78 128 66 143 50 157Z" fill={color.light} />
      <path
        d="M50 12V150M50 45L27 30M50 45L73 30M50 76L20 58M50 76L80 58M50 108L27 92M50 108L73 92"
        fill="none"
        stroke="#0a4426"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.65"
      />
    </svg>
  );
}

// Wraps the pages. The wash of water lives here, above the pages, so it stays on screen while the page underneath changes.
function LeafTransition({ children }) {
  const navigate = useNavigate();
  const [phase, setPhase] = useState("idle");   // idle -> cover (-> hold) -> reveal -> idle
  const [label, setLabel] = useState("");
  const [style, setStyle] = useState("push");
  const running = useRef(false);
  const shownLocation = useLocation();   // the page to draw (App.jsx passes it to <Routes>)

  // style: "push" (the default) or "dive" (from Landing). ready: an optional promise to wait for (the next page's code).
  const leafNavigate = useCallback(async (to, { state, ready, style: chosen = "push" } = {}) => {
    if (running.current) return;   // already on the way (a double click)

    // People who turned off animations on their device just go to the page
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      navigate(to, { state });
      return;
    }

    running.current = true;

    // The waterfall: pour in, switch pages behind it, wait for the new page to be ready, then fall away
    if (chosen === "falls") {
      setStyle("falls");
      setLabel(to.endsWith("/editor") ? "Opening the Editor" : to.endsWith("/export") ? "Getting your export ready" : "Back to AI Studio");
      setPhase("cover");
      let settle;
      const pageReady = new Promise((resolve) => { settle = resolve; });
      const onReady = () => settle();
      window.addEventListener(PAGE_READY, onReady);
      await Promise.all([wait(FALLS.cover), Promise.resolve(ready).catch(() => {})]);
      setPhase("hold");
      navigate(to, { state });
      await Promise.all([Promise.race([pageReady, wait(FALLS.most)]), wait(FALLS.least)]);
      window.removeEventListener(PAGE_READY, onReady);
      setPhase("reveal");
      await wait(FALLS.reveal);
      setPhase("idle");
      running.current = false;
      return;
    }

    const move = MOVES[chosen] ?? MOVES.push;
    setStyle(chosen);
    setPhase("cover");
    document.documentElement.classList.add("is-camera-moving");   // fades the page's words and buttons
    window.dispatchEvent(new CustomEvent("cascade:camera", { detail: { move: { dive: "dive", rise: "rise" }[chosen] ?? "forward", duration: move.camera } }));

    const nextPageReady = Promise.race([Promise.resolve(ready).catch(() => {}), wait(MAX_WAIT_MS)]);
    await Promise.all([wait(move.camera), nextPageReady]);
    if (chosen === "dive") window.cascadeCameraArrive = performance.now();   // Projects' camera sinks down as it appears
    if (chosen === "rise") window.cascadePondArrive = performance.now();     // the pond's camera comes down as it appears
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
      {children(shownLocation)}
      {phase !== "idle" && style === "falls" && <WaterfallCurtain phase={phase} label={label} />}
      {phase !== "idle" && style !== "falls" && (
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
