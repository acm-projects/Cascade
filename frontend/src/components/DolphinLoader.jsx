import { useEffect, useRef, useState } from "react";
import "./DolphinLoader.css";

// The loading screen: blocky 3D dolphins leaping out of the page's own pixel sea, one after another
// (dolphinLoaderScene.js). Each one bursts out of the surface in a ring of pixel ripples, arcs over the water with
// its shadow sliding beneath it, and dives back in with a splash of square droplets. There is no box: it all
// happens on the water the page already shows.
// The 3D code downloads on its own. Until it's ready, or if the device can't draw 3D, the older flat version shows
// instead (FlatDolphins below: Blender-rendered frames from frontend/blender/dolphin.py, flown along the leap by CSS).
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

// The older flat version: picture frames of a dolphin, flown along the leap by CSS
function FlatDolphins() {
  return (
    <div className="dolphin-loader-water" aria-hidden="true">
      {LEAPS.map((n) => (
        <span key={n} className="dolphin-loader-group" style={{ "--leap": n }}>
          <Ripple className="is-out" leap={n} />
          <Ripple className="is-in" leap={n} />
          <span className="dolphin-loader-shadow" />
          <span className="dolphin-loader-leap">
            <span className="dolphin-loader-dolphin" />
          </span>
          <span className="dolphin-loader-splash"><i /><i /><i /><i /><i /><i /></span>
        </span>
      ))}
    </div>
  );
}

function DolphinLoader({ label = "Loading" }) {
  const holderRef = useRef(null);
  const [mode, setMode] = useState("flat");   // "flat" until the 3D is running, then "3d"

  useEffect(() => {
    let stop = null;
    let cancelled = false;
    const holder = holderRef.current;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    import("./dolphinLoaderScene").then(({ createDolphinLoaderScene }) => {
      if (cancelled || !holder) return;
      try {
        // a new canvas each time: once a canvas's 3D is shut down, it can't be started again
        const canvas = document.createElement("canvas");
        canvas.className = "dolphin-loader-canvas";
        holder.append(canvas);
        stop = createDolphinLoaderScene(canvas, { still });
        setMode("3d");
      } catch {
        holder.replaceChildren();   // no 3D here: keep the flat dolphins
      }
    }).catch(() => {});
    return () => {
      cancelled = true;
      stop?.();
      holder?.replaceChildren();
    };
  }, []);

  return (
    <div className={`dolphin-loader is-${mode}`} role="status" aria-label={label}>
      <div ref={holderRef} className="dolphin-loader-3d" aria-hidden="true" />
      {mode === "flat" && <FlatDolphins />}
      <p className="dolphin-loader-label">{label}…</p>
    </div>
  );
}

export default DolphinLoader;
