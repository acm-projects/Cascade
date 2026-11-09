import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
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
  { base: "#1f8f4a", light: "#35ad5e" },
  { base: "#0f7a3e", light: "#1f9550" },
  { base: "#7cc52f", light: "#a3d637" },
  { base: "#2fa84f", light: "#56c168" },
  { base: "#0b5a30", light: "#127043" },
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

// Wraps the pages. The leaves live here, above the pages, so they stay on screen while the page underneath changes.
function LeafTransition({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [shownLocation, setShownLocation] = useState(location);
  const shown = useRef(location);
  const [phase, setPhase] = useState("idle");
  const [backward, setBackward] = useState(false);
  const readyPage = useRef(null);

  // Existing callers can preload a page; every router navigation uses the same animation.
  const leafNavigate = useCallback((to, { ready, ...options } = {}) => {
    readyPage.current = ready ? Promise.resolve(ready).catch(() => {}) : null;
    navigate(to, options);
  }, [navigate]);

  useLayoutEffect(() => {
    let cancelled = false;
    const timers = new Set();
    const delay = ms => new Promise(resolve => {
      const timer = setTimeout(() => { timers.delete(timer); resolve(); }, ms);
      timers.add(timer);
    });
    const commit = () => {
      shown.current = location;
      setShownLocation(location);
    };
    // Session switches, query changes and redirects within a page stay immediate.
    const page = pathname => pathname.replace(/(\/studio)(?:\/[^/]+)?\/?$/, "$1");
    if (page(location.pathname) === page(shown.current.pathname) ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      commit();
      setPhase("idle");
      return;
    }
    const ready = readyPage.current;
    readyPage.current = null;
    const workflowStep = pathname => {
      const step = pathname.match(/^\/projects\/[^/]+\/(studio|editor|export)(?:\/|$)/)?.[1];
      return { studio: 1, editor: 2, export: 3 }[step] ?? 0;
    };
    setBackward(workflowStep(location.pathname) < workflowStep(shown.current.pathname));
    setPhase("cover");
    async function transition() {
      await Promise.all([delay(COVER_MS), Promise.race([ready, delay(MAX_WAIT_MS)])]);
      if (cancelled) return;
      commit();
      await delay(HOLD_MS);
      if (cancelled) return;
      setPhase("reveal");
      await delay(REVEAL_MS);
      if (!cancelled) setPhase("idle");
    }
    transition();
    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, [location]);

  return (
    <LeafTransitionContext.Provider value={leafNavigate}>
      {children(shownLocation)}
      {phase !== "idle" && (
        <div className={`leaf-transition leaf-transition-${phase}${backward ? " leaf-transition-backward" : ""}`} aria-hidden="true">
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
