import { useEffect, useRef, useState } from "react";
import logo from "../assets/icons/cascade-logo.svg";
import { createCurtainScene } from "./waterfallCurtainScene";
import "./WaterfallCurtain.css";

// The page change between AI Studio, the Editor and Export (LeafTransition.jsx runs it):
// a waterfall pours down and covers the screen, the next page loads behind it, and once that page says it's
// ready the waterfall keeps falling and drops away, showing the page fully loaded.
//   phase - "cover" (pouring down over the screen), "hold" (covering, while the next page loads),
//           "reveal" (falling away off the bottom)
//   label - what's loading, shown in the middle while it holds ("Opening the Editor")
//
// The water is a 3D scene (waterfallCurtainScene.js): curved sheets of water at different depths, foam,
// droplets and mist. If the device can't draw 3D, a flat pixel-art waterfall is drawn instead: streaks of
// light and dark water falling at different speeds, a bright lip at the top and churning foam at the bottom.
const PIXEL = 7;   // page pixels per water pixel

const DEEP = [31, 159, 214];
const MID = [56, 198, 220];
const LIGHT = [143, 227, 238];
const WHITE = [236, 252, 255];

function hash(n) {
  const x = Math.sin(n * 127.1) * 43758.5453;
  return x - Math.floor(x);
}

function WaterfallCurtain({ phase, label }) {
  const canvasRef = useRef(null);   // the flat fallback's canvas
  const holderRef = useRef(null);   // where the 3D canvas goes
  const sceneRef = useRef(null);
  const [flat, setFlat] = useState(false);   // true: no 3D on this device, use the pixel-art version

  // The 3D waterfall
  useEffect(() => {
    if (flat) return undefined;
    // A new canvas each time: once a canvas's 3D is shut down, it can't be started again
    const canvas = document.createElement("canvas");
    canvas.className = "waterfall-3d";
    holderRef.current.append(canvas);
    try {
      sceneRef.current = createCurtainScene(canvas);
      sceneRef.current.setPhase(phase);
    } catch {
      canvas.remove();
      setFlat(true);   // eslint-disable-line react-hooks/set-state-in-effect -- one-time fallback
    }
    return () => {
      sceneRef.current?.stop();
      sceneRef.current = null;
      canvas.remove();
    };
  }, [flat]);   // eslint-disable-line react-hooks/exhaustive-deps -- the phase is passed on below

  useEffect(() => {
    sceneRef.current?.setPhase(phase);
  }, [phase]);

  // The flat pixel-art fallback
  useEffect(() => {
    if (!flat) return undefined;
    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");
    let frame = 0;
    let columns = 0;
    let rows = 0;
    let image = null;
    const start = performance.now();

    function size() {
      columns = Math.ceil(window.innerWidth / PIXEL);
      rows = Math.ceil((window.innerHeight * 1.12) / PIXEL);   // a little taller than the screen (the foam edges)
      canvas.width = columns;
      canvas.height = rows;
      image = context.createImageData(columns, rows);
    }

    function draw() {
      const t = (performance.now() - start) / 1000;
      const data = image.data;
      for (let x = 0; x < columns; x += 1) {
        // every column of water falls at its own speed, with its own streak pattern
        const speed = 18 + hash(x) * 22;
        const offset = hash(x + 91) * 400;
        const band = 0.5 + 0.5 * Math.sin(x * 0.11 + Math.sin(x * 0.037) * 3);   // wide light / dark bands across
        for (let y = 0; y < rows; y += 1) {
          const along = y - t * speed - offset;
          const streak = hash(Math.floor(along / 9) * 13.7 + x * 0.5);
          let color = band > 0.55 ? MID : DEEP;
          if (streak > 0.86) color = LIGHT;
          else if (streak > 0.8 && band > 0.4) color = WHITE;
          else if (streak < 0.08) color = DEEP;
          // the lip at the top is bright; the bottom churns white
          const fromBottom = rows - y;
          if (y < 3) color = y < 1 ? WHITE : LIGHT;
          if (fromBottom < 14) {
            const churn = hash(Math.floor(x / 2) * 3.1 + Math.floor((y + t * 9) / 2) * 7.3 + Math.floor(t * 6));
            if (churn > 0.35 + fromBottom * 0.04) color = WHITE;
            else if (churn > 0.2) color = LIGHT;
          }
          const i = (y * columns + x) * 4;
          data[i] = color[0];
          data[i + 1] = color[1];
          data[i + 2] = color[2];
          data[i + 3] = 255;
        }
      }
      context.putImageData(image, 0, 0);
      frame = requestAnimationFrame(draw);
    }

    size();
    draw();
    window.addEventListener("resize", size);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", size);
    };
  }, [flat]);

  return (
    <div className={`waterfall-curtain is-${phase}${flat ? " is-flat" : " is-3d"}`} aria-hidden="true">
      {flat ? (
        <div className="waterfall-sheet">
          <span className="waterfall-foam is-top" />
          <canvas key="flat" ref={canvasRef} className="waterfall-canvas" />
          <span className="waterfall-foam is-bottom" />
          <span className="waterfall-mist" />
        </div>
      ) : (
        <div key="3d" ref={holderRef} className="waterfall-3d" />
      )}
      <div className="waterfall-label">
        <img src={logo} alt="" />
        <span>{label}</span>
      </div>
    </div>
  );
}

export default WaterfallCurtain;
