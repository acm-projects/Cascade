import { useEffect, useRef } from "react";
import { getSeaLife } from "./seaLife";
import { createCreatures } from "./seaCreatures";
import { seaDepthTarget } from "./seaDepth";
import "./WaterFlow.css";

// Moving underwater background for the work pages: deep blue water lit from the surface, with a sun glow and
// light rays fanning down, the waves' light and shadow rolling across, and ripples wherever the cursor moves.
// Minecraft-style 3D sea animals swim in front (seaCreatures.js), with bubbles, glowing plankton and kelp
// over them (seaLife.js). Opening Trends sinks it deeper (seaDepth.js): the view zooms in,
// the water darkens, the sunlight fades and the glowing creatures and plankton light up.
// The clock and the animals carry on across page changes. Stops when the tab is hidden; without WebGL the plain
// blue page background shows instead.
//   within - fill the parent element instead of the whole screen (the Trends header)
//   deep   - always at full depth (the Trends header, which is already "down there")
const TRAIL = 10;      // how many recent cursor positions are making ripples at once
const QUALITY = 0.5;   // fraction of the real pixels the water is drawn at (water is soft, nobody can tell)
const LIFE_SCALE = 2;  // screen pixels per sea-life canvas pixel
const EPOCH = performance.now();
let lastDepth = 0;     // so a new page starts at the depth the previous one was at

const VERTEX = "attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }";

const FRAGMENT = `
precision highp float;
uniform vec2 uSize;
uniform float uTime;
uniform float uDepth;
uniform vec3 uTrail[${TRAIL}];   // x, y (in screen units), strength

// the height of the water surface: long rolling waves, finer chop on top, and the ripples from the cursor
float height(vec2 q) {
  float t = uTime * 0.6;
  vec2 w = q + 0.18 * vec2(sin(q.y * 1.7 + t * 0.35), cos(q.x * 1.3 + t * 0.30));
  float h = 0.0;
  h += sin(dot(w, vec2(0.95, 0.30)) * 6.5 + t * 0.9) * 0.45;
  h += sin(dot(w, vec2(-0.40, 0.90)) * 10.0 - t * 0.7) * 0.30;
  h += sin(dot(w, vec2(0.70, -0.70)) * 17.0 + t * 1.3) * 0.18;
  h += sin(dot(w, vec2(0.20, 0.98)) * 27.0 - t * 1.7) * 0.11;
  for (int i = 0; i < ${TRAIL}; i++) {
    vec3 d = uTrail[i];
    float r = distance(q, d.xy);
    h += sin(r * 48.0 - (1.0 - d.z) * 16.0) * d.z * exp(-r * 6.0) * 0.40;
  }
  return h;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uSize;
  float aspect = uSize.x / uSize.y;
  vec2 q = vec2(uv.x * aspect, uv.y);
  float t = uTime;
  float lit = 1.0 - uDepth * 0.85;   // how much sunlight still reaches this deep

  // water color by height on screen: lighter toward the surface; everything darker deeper down
  vec3 surface = mix(vec3(0.17, 0.50, 0.74), vec3(0.04, 0.18, 0.34), uDepth);
  vec3 middle = mix(vec3(0.06, 0.27, 0.50), vec3(0.02, 0.09, 0.21), uDepth);
  vec3 bottom = mix(vec3(0.02, 0.10, 0.24), vec3(0.004, 0.025, 0.08), uDepth);
  vec3 color = mix(bottom, middle, smoothstep(0.0, 0.6, uv.y));
  color = mix(color, surface, smoothstep(0.55, 1.0, uv.y));

  // the moving water: crests a little lighter, troughs a little darker
  float e = 0.0015;
  float h = height(q);
  vec2 slope = vec2(height(q + vec2(e, 0.0)) - h, height(q + vec2(0.0, e)) - h) / e;
  vec3 n = normalize(vec3(-slope * 0.030, 1.0));
  color *= 1.0 + clamp(h * 0.55 + n.x * 0.9, -1.0, 1.0) * 0.14;

  // the sun above the surface: a soft glow at the top and rays fanning down from it
  vec2 sun = vec2(aspect * (0.5 + sin(t * 0.04) * 0.08), 1.18);
  vec2 d = q - sun;
  float angle = atan(d.x, -d.y);
  float rays = pow(0.5 + 0.5 * sin(angle * 23.0 + t * 0.12), 6.0) * 0.6
             + pow(0.5 + 0.5 * sin(angle * 37.0 - t * 0.09 + 2.0), 10.0) * 0.5
             + pow(0.5 + 0.5 * sin(angle * 11.0 + t * 0.06 + 4.0), 5.0) * 0.45;
  float reach = smoothstep(1.5, 0.15, length(d));
  color += vec3(0.50, 0.82, 1.0) * rays * reach * 0.20 * lit;
  color += vec3(0.55, 0.88, 1.0) * exp(-length(d) * 2.4) * 0.40 * lit;

  // sunlight glinting off the tilted surface
  vec3 light = normalize(vec3(-0.35, 0.55, 0.75));
  float shine = pow(max(dot(reflect(-light, n), vec3(0.0, 0.0, 1.0)), 0.0), 60.0);
  color += vec3(0.45, 0.80, 1.0) * shine * 0.35 * lit;

  // darker toward the edges, like looking out through deep water
  vec2 c = uv - 0.5;
  color *= 1.0 - dot(c, c) * (0.7 + uDepth * 0.6);
  gl_FragColor = vec4(color, 1.0);
}
`;

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
}

// Sets up the WebGL water on a canvas. Returns { resize, draw, stop }, or null if this device can't draw it.
function createWater(canvas) {
  const gl = canvas.getContext("webgl", { antialias: false, alpha: false, powerPreference: "low-power" });
  const vertex = gl && compile(gl, gl.VERTEX_SHADER, VERTEX);
  const fragment = gl && compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
  const program = vertex && fragment ? gl.createProgram() : null;
  if (!program) return null;
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  gl.useProgram(program);

  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, "p");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

  const uSize = gl.getUniformLocation(program, "uSize");
  const uTime = gl.getUniformLocation(program, "uTime");
  const uDepth = gl.getUniformLocation(program, "uDepth");
  const uTrail = gl.getUniformLocation(program, "uTrail");
  let width = 1;
  let height = 1;

  return {
    resize(w, h) {
      width = w;
      height = h;
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    },
    draw(seconds, depth, trail) {
      gl.uniform2f(uSize, width, height);
      gl.uniform1f(uTime, seconds);
      gl.uniform1f(uDepth, depth);
      gl.uniform3fv(uTrail, trail);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    },
    stop() {
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    },
  };
}

function WaterFlow({ within = false, deep = false }) {
  const holderRef = useRef(null);

  useEffect(() => {
    const holder = holderRef.current;
    // New canvases each time: once a canvas's WebGL is shut down (our cleanup does that), it can't be started
    // again, and React's StrictMode runs this effect twice in development.
    const waterCanvas = document.createElement("canvas");
    waterCanvas.className = "water-flow-water";
    const creatureCanvas = document.createElement("canvas");
    creatureCanvas.className = "water-flow-creatures";
    const lifeCanvas = document.createElement("canvas");
    lifeCanvas.className = "water-flow-life";
    holder.append(waterCanvas, creatureCanvas, lifeCanvas);

    const water = createWater(waterCanvas);
    if (!water) waterCanvas.remove();   // the plain blue background shows through instead
    let creatures = null;
    try {
      creatures = createCreatures(creatureCanvas);
    } catch {
      creatureCanvas.remove();   // no WebGL: just the water (or the plain blue) and the particles
    }
    const life = getSeaLife(within ? "within" : "page", lifeCanvas);
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const resize = () => {
      const box = within ? holder.getBoundingClientRect() : { width: window.innerWidth, height: window.innerHeight };
      water?.resize(Math.max(2, Math.round(box.width * QUALITY)), Math.max(2, Math.round(box.height * QUALITY)));
      const lifeW = Math.max(2, Math.ceil(box.width / LIFE_SCALE));
      const lifeH = Math.max(2, Math.ceil(box.height / LIFE_SCALE));
      creatures?.resize(lifeW, lifeH);
      life.resize(lifeW, lifeH);
    };
    resize();

    // recent cursor positions, newest first; each fades as it ages
    const trail = Array.from({ length: TRAIL }, () => ({ x: -9, y: -9, age: 1 }));
    const flat = new Float32Array(TRAIL * 3);
    let lastDrop = null;
    const onMove = (event) => {
      const box = holder.getBoundingClientRect();
      const x = (event.clientX - box.left) / box.height;   // same units as the shader: height = 1
      const y = 1 - (event.clientY - box.top) / box.height;
      if (!lastDrop || Math.hypot(x - lastDrop.x, y - lastDrop.y) > 0.035) {   // one ripple every little distance moved
        trail.pop();
        trail.unshift({ x, y, age: 0 });
        lastDrop = { x, y };
      }
    };

    let depth = deep ? 1 : lastDepth;
    let shownDepth = -1;
    let previous = performance.now();
    let frame = 0;
    const draw = (now) => {
      const seconds = (now - EPOCH) / 1000;
      const dt = Math.min(0.05, (now - previous) / 1000);
      previous = now;

      // ease toward the wanted depth over about two seconds
      const goal = deep ? 1 : seaDepthTarget();
      depth += (goal - depth) * Math.min(1, dt * 1.8);
      if (Math.abs(goal - depth) < 0.001) depth = goal;
      if (!deep) lastDepth = depth;
      if (Math.abs(depth - shownDepth) > 0.002) {
        shownDepth = depth;
        if (!within) holder.style.transform = `scale(${1 + depth * 0.12})`;   // swimming down into it
        lifeCanvas.style.filter = `brightness(${1 - depth * 0.3})`;
      }

      trail.forEach((d, i) => {
        d.age = Math.min(1, d.age + 0.012);
        flat[i * 3] = d.x;
        flat[i * 3 + 1] = d.y;
        flat[i * 3 + 2] = Math.pow(1 - d.age, 1.6);
      });
      water?.draw(seconds, depth, flat);
      creatures?.frame(seconds, still ? 0 : dt, depth);
      life.frame(seconds, still ? 0 : dt, depth);
      if (!still || Math.abs(goal - depth) > 0) frame = requestAnimationFrame(draw);
    };
    const visibility = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden) {
        previous = performance.now();
        frame = requestAnimationFrame(draw);
      }
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", visibility);
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", visibility);
      water?.stop();
      creatures?.dispose();
      waterCanvas.remove();
      creatureCanvas.remove();
      lifeCanvas.remove();
    };
  }, [within, deep]);

  return <div ref={holderRef} className={`water-flow${within ? " water-flow-within" : ""}`} aria-hidden="true" />;
}

export default WaterFlow;
