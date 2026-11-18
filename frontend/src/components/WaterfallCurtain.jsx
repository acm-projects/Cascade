import { useEffect, useRef } from "react";
import "./WaterfallCurtain.css";

// The page change between AI Studio, the Editor and Export (LeafTransition.jsx runs it):
// The waterfall covers the route swap, then falls away to reveal the next page.
// The water is pixel art: it's drawn on a small canvas (one canvas pixel = PIXEL page pixels) and stretched
// up without smoothing, so every pixel stays a crisp square. What's drawn, back to front:
//   flat blue water -> long deep streams (slow) -> lighter streams (faster) -> white glints (fastest)
//   -> the lighter lip where the water curves over the top -> scalloped foam with a navy outline, top and bottom
const PIXEL = 6;   // page pixels per art pixel

const COLOR = {
  water: "#2aa6d1",
  deep: "#1f8cbf",
  light: "#4fbfe0",
  glint: "#effcff",
  lip: "#86dbee",
  foam: "#f4fcf8",
  foamShade: "#d3eff3",
  outline: "#12324f",
};

// A repeatable random number generator, so the streams are laid out the same way every time
function makeRandom(seed) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

// Streams across the screen for one layer. Each lane (a strip of columns) has one or two streams
// that fall at the layer's speed and loop back to the top.
function layoutStreams(random, columns, rows, { minWidth, maxWidth, minGap, maxGap, minLength, maxLength, speed, perLane }) {
  const streams = [];
  let x = Math.floor(random() * maxGap);
  while (x < columns) {
    const width = minWidth + Math.floor(random() * (maxWidth - minWidth + 1));
    const count = random() < perLane ? 2 : 1;
    const period = Math.round(rows * (0.9 + random() * 0.7));
    for (let i = 0; i < count; i += 1) {
      streams.push({
        x, width, period,
        length: Math.round(minLength + random() * (maxLength - minLength)),
        phase: random() * period + (i * period) / 2,
        speed: speed * (0.9 + random() * 0.2),
      });
    }
    x += width + minGap + Math.floor(random() * (maxGap - minGap + 1));
  }
  return streams;
}

// A stream as a long pill: full width in the middle, corners cut on the end rows so the ends look round
function drawStream(context, stream, top, rows) {
  const { x, width, length } = stream;
  if (top >= rows || top + length <= 0) return;
  const cut = width >= 6 ? 2 : width >= 3 ? 1 : 0;
  context.fillRect(x, top + cut, width, length - cut * 2);
  for (let r = 0; r < cut; r += 1) {
    const inset = cut - r;
    context.fillRect(x + inset, top + r, width - inset * 2, 1);
    context.fillRect(x + inset, top + length - 1 - r, width - inset * 2, 1);
  }
}

// Scalloped foam along one edge. Each scallop is a half circle; down = true bulges toward the bottom
// (the top edge's foam), down = false bulges up (the bottom edge's foam).
function drawFoam(context, columns, rows, { edge, radius, offset, down }) {
  for (let x = 0; x < columns; x += 1) {
    const span = radius * 2;
    const dx = ((x + offset) % span + span) % span - radius + 0.5;
    const bulge = Math.round(Math.sqrt(Math.max(0, radius * radius - dx * dx)) * 0.75);
    if (down) {
      const bottom = edge + bulge;          // the foam fills from the top of the sheet down to here
      context.fillStyle = COLOR.foam;
      context.fillRect(x, 0, 1, bottom);
      context.fillStyle = COLOR.foamShade;
      context.fillRect(x, bottom - 3, 1, 2);
      context.fillStyle = COLOR.outline;
      context.fillRect(x, bottom, 1, 1);
    } else {
      const top = rows - edge - bulge;      // the foam fills from here to the bottom of the sheet
      context.fillStyle = COLOR.foam;
      context.fillRect(x, top, 1, rows - top);
      context.fillStyle = COLOR.foamShade;
      context.fillRect(x, top + 2, 1, 2);
      context.fillStyle = COLOR.outline;
      context.fillRect(x, top - 1, 1, 1);
    }
  }
  // the outline also runs up the sides of each scallop, so neighbours don't blur together
  context.fillStyle = COLOR.outline;
  for (let x = 1; x < columns; x += 1) {
    const span = radius * 2;
    const height = (col) => {
      const dx = ((col + offset) % span + span) % span - radius + 0.5;
      return Math.round(Math.sqrt(Math.max(0, radius * radius - dx * dx)) * 0.75);
    };
    const a = height(x - 1);
    const b = height(x);
    if (Math.abs(a - b) <= 1) continue;
    const from = Math.min(a, b);
    const to = Math.max(a, b);
    const col = a > b ? x : x - 1;   // the outline goes on the shorter column's side
    for (let h = from + 1; h < to; h += 1) {
      context.fillRect(col, down ? edge + h : rows - edge - h - 1, 1, 1);
    }
  }
}

function WaterfallCurtain({ phase, durations }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let columns = 0;
    let rows = 0;
    let layers = [];
    const start = performance.now();

    function size() {
      columns = Math.ceil((canvas.clientWidth || window.innerWidth) / PIXEL);
      rows = Math.ceil((canvas.clientHeight || window.innerHeight) / PIXEL);
      canvas.width = columns;
      canvas.height = rows;
      const random = makeRandom(11);
      // speeds are in art pixels per second
      layers = [
        { color: COLOR.deep, streams: layoutStreams(random, columns, rows, { minWidth: 6, maxWidth: 13, minGap: 3, maxGap: 9, minLength: rows * 0.35, maxLength: rows * 0.8, speed: 46, perLane: 0.5 }) },
        { color: COLOR.light, streams: layoutStreams(random, columns, rows, { minWidth: 2, maxWidth: 4, minGap: 8, maxGap: 18, minLength: rows * 0.25, maxLength: rows * 0.55, speed: 70, perLane: 0.4 }) },
        { color: COLOR.glint, streams: layoutStreams(random, columns, rows, { minWidth: 1, maxWidth: 1, minGap: 18, maxGap: 34, minLength: 8, maxLength: 16, speed: 120, perLane: 0.6 }) },
      ];
    }

    function draw() {
      const time = still ? 0 : (performance.now() - start) / 1000;
      context.fillStyle = COLOR.water;
      context.fillRect(0, 0, columns, rows);
      for (const layer of layers) {
        context.fillStyle = layer.color;
        for (const stream of layer.streams) {
          const loop = stream.period + stream.length;
          const top = Math.floor((stream.phase + time * stream.speed) % loop) - stream.length;
          drawStream(context, stream, top, rows);
        }
      }
      // the sheet is a little taller than the screen (WaterfallCurtain.css): this is where the screen's top is
      const screenTop = Math.round(rows * (4 / 108));
      // the lip: lighter water with a wavy bottom, just under the top foam
      context.fillStyle = COLOR.lip;
      for (let x = 0; x < columns; x += 1) {
        context.fillRect(x, 0, 1, screenTop + 12 + Math.round(Math.sin(x * 0.22) * 1.6));
      }
      // the foam bobs one pixel up and down
      const bob = still ? 0 : Math.round(Math.sin(time * 4)) ;
      drawFoam(context, columns, rows, { edge: screenTop + 3 + bob, radius: 9, offset: 0, down: true });
      drawFoam(context, columns, rows, { edge: screenTop + 2 - bob, radius: 12, offset: 5, down: false });
      if (!still) frame = requestAnimationFrame(draw);
    }

    function resize() {
      size();
      if (still) draw();
    }

    size();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div className={`waterfall-curtain is-${phase}`} style={{ "--waterfall-duration": `${durations[phase]}ms` }} aria-hidden="true">
      <div className="waterfall-sheet">
        <canvas ref={canvasRef} className="waterfall-canvas" />
      </div>
    </div>
  );
}

export default WaterfallCurtain;
