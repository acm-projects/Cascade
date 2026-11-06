import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./LeafTransition.css";
import { LeafTransitionContext } from "../context/leafTransitionValue";

// The steps, in milliseconds. These match the timings in LeafTransition.css.
const COVER_MS = 620;    // leaves blow in until the screen is covered
const HOLD_MS = 120;     // a beat for the next page to draw behind the leaves
const REVEAL_MS = 640;   // leaves blow away
const MAX_WAIT_MS = 4000; // never keep someone behind the leaves longer than this

const COLUMNS = 7;
const ROWS = 5;
const COLORS = [
  { base: "#1f8f4a", light: "#35ad5e", edge: "#0f5c32" },
  { base: "#178244", light: "#2a9c58", edge: "#0b5029" },
  { base: "#74c02f", light: "#98d63c", edge: "#478a22" },
  { base: "#2fa84f", light: "#54c46c", edge: "#177a3a" },
  { base: "#116a3a", light: "#1a8047", edge: "#0a4426" },
];

// A fixed pattern of overlapping leaves, one column at a time so they arrive like a gust from the left
const LEAVES = [];
for (let column = 0; column < COLUMNS; column += 1) {
  for (let row = 0; row < ROWS; row += 1) {
    const number = column * ROWS + row;
    LEAVES.push({
      id: number,
      x: ((column + 0.5) / COLUMNS) * 100 + ((number * 7) % 5) - 2,
      y: ((row + 0.5) / ROWS) * 100 + ((number * 11) % 9) - 4,
      rotate: (number * 47) % 360,
      delay: column * 32 + ((number * 13) % 40),
      color: COLORS[(number * 3 + row) % COLORS.length],
    });
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// A chunky low-poly leaf: a dark underside for its thickness, then two facets on top
function Leaf({ color }) {
  const left = "M50 4 L14 44 L6 88 L22 126 L50 156 Z";
  const right = "M50 4 L86 44 L94 88 L78 126 L50 156 Z";
  return (
    <svg viewBox="0 0 100 170">
      <path d={`${left} ${right}`} fill={color.edge} transform="translate(0 9)" />
      <path d={left} fill={color.base} />
      <path d={right} fill={color.light} />
      <path d="M50 40 L28 62 M50 40 L72 62 M50 86 L22 106 M50 86 L78 106" fill="none" stroke={color.edge} strokeWidth="3" strokeLinecap="square" opacity="0.55" />
    </svg>
  );
}

// Wraps the pages. The leaves live here, above the pages, so they stay on screen while the page underneath changes.
function LeafTransition({ children }) {
  const navigate = useNavigate();
  const [phase, setPhase] = useState("idle");   // idle -> cover -> reveal -> idle
  const running = useRef(false);

  const leafNavigate = useCallback(async (to, { state, ready } = {}) => {
    if (running.current) return;   // already on the way (a double click)

    // People who turned off animations on their device just go to the page
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      navigate(to, { state });
      return;
    }

    running.current = true;
    setPhase("cover");
    const nextPageReady = Promise.race([Promise.resolve(ready).catch(() => {}), wait(MAX_WAIT_MS)]);
    await Promise.all([wait(COVER_MS), nextPageReady]);
    navigate(to, { state });
    await wait(HOLD_MS);
    setPhase("reveal");
    await wait(REVEAL_MS);
    setPhase("idle");
    running.current = false;
  }, [navigate]);

  return (
    <LeafTransitionContext.Provider value={leafNavigate}>
      {children}
      {phase !== "idle" && (
        <div className={`leaf-transition leaf-transition-${phase}`} aria-hidden="true">
          <div className="leaf-transition-backdrop" />
          {LEAVES.map((leaf) => (
            <div
              key={leaf.id}
              className="leaf-transition-leaf"
              style={{
                left: `${leaf.x}%`,
                top: `${leaf.y}%`,
                "--leaf-rotate": `${leaf.rotate}deg`,
                "--leaf-delay": `${leaf.delay}ms`,
              }}
            >
              <Leaf color={leaf.color} />
            </div>
          ))}
        </div>
      )}
    </LeafTransitionContext.Provider>
  );
}

export default LeafTransition;
