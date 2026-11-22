import "./DolphinLoader.css";

// The loading screen: dolphins leaping out of the page's own pixel sea, one after another. Each one breaks the
// surface in a blocky pixel ripple, arcs over the water with its shadow sliding beneath it, and dives back in with
// a burst of square droplets. There is no box: it all happens on the water the page already shows.
// The dolphin is a Blender render (frontend/blender/dolphin.py -> public/loader/dolphin.webp, about 5 KB); the
// ripples, splashes and leaps are CSS, so nothing heavy downloads just to say "loading".
//   <DolphinLoader label="Opening Studio Island" />
//   label - what's loading; read out by screen readers and shown under the dolphins
const LEAPS = [0, 1, 2];   // three dolphins, staggered so one is always in the air

// A pixel ripple: the outline of a flat ellipse on a coarse grid, so it looks like the sea's own pixel dashes
const RX = 9, RY = 3;
const RIPPLE = [...new Set(Array.from({ length: 64 }, (_, i) => {
  const a = (i / 64) * Math.PI * 2;
  return `${Math.round(RX + RX * Math.cos(a))},${Math.round(RY + RY * Math.sin(a))}`;
}))].map((point) => point.split(",").map(Number));

function Ripple({ className, leap }) {
  return (
    <svg className={`dolphin-loader-ripple ${className}`} style={{ "--leap": leap }} viewBox={`-1 -1 ${RX * 2 + 3} ${RY * 2 + 3}`}
      shapeRendering="crispEdges">
      {RIPPLE.map(([x, y]) => <rect key={`${x},${y}`} x={x} y={y} width="1" height="1" />)}
    </svg>
  );
}

function DolphinLoader({ label = "Loading" }) {
  return (
    <div className="dolphin-loader" role="status" aria-label={label}>
      <div className="dolphin-loader-water" aria-hidden="true">
        {LEAPS.map((n) => (
          <span key={n} className="dolphin-loader-group" style={{ "--leap": n }}>
            <Ripple className="is-out" leap={n} />
            <Ripple className="is-in" leap={n} />
            <span className="dolphin-loader-shadow" />
            <span className="dolphin-loader-leap">
              <img className="dolphin-loader-dolphin" src="/loader/dolphin.webp" alt="" width="104" height="58" draggable="false" />
            </span>
            <span className="dolphin-loader-splash"><i /><i /><i /><i /><i /><i /></span>
          </span>
        ))}
      </div>
      <p className="dolphin-loader-label">{label}…</p>
    </div>
  );
}

export default DolphinLoader;
