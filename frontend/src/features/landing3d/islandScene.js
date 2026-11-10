import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";

// The 3D world behind Landing and Projects: a rainforest island in the sea, seen from an isometric camera.
// One big video screen feeds a river, and clip cards ride it down the waterfalls: one video becomes many clips.
// The island itself is made in Blender (frontend/blender/island.py); the sea, water, cards and animals are drawn here.
//
// createIslandScene(canvas, { still, framing }) starts it and returns a function that stops it and frees its memory.
// In the world: +x is down-right on screen, +z is down-left, +y is up.

export const COLORS = {
  grass: ["#6cc644", "#5dbb3f", "#7ace4c", "#55b03c"],
  dirt: ["#9a6a3c", "#8d5f35"],
  rock: ["#6f6a68", "#65615f", "#77716c"],
  deepRock: ["#4d4f58", "#454751"],
  leaves: ["#2fa84f", "#1f8f4a", "#3cb95a", "#178244"],
  brightLeaves: ["#7cc52f", "#93d436"],
  trunk: "#7a5230",
  wood: "#a06f3c",
  woodDark: "#70492a",
  thatch: "#d9b35c",
  water: "#38c6dc",
  foam: "#ecfdff",
  cream: "#f6ecd2",
  glow: "#7ff5e0",
};

// Tops of the three steps of the island
const HIGH = 3.8;
const MID = 2.4;
const LOW = 1.2;
const RIVER_MIN_X = 0.5;
const RIVER_MAX_X = 2.5;
const RIVER_X = (RIVER_MIN_X + RIVER_MAX_X) / 2;
const SEA_LEVEL = -0.6;
// How big the island is: about this many tiles out from the middle. The river runs from RIVER_BACK to RIVER_FRONT,
// and its last waterfall drops into the sea at the front edge (RIVER_FRONT + 0.5).
const ISLAND_RADIUS = 9;
const RIVER_BACK = -8;
const RIVER_FRONT = 8;
const EDGE = RIVER_FRONT + 0.5;
const GRID = ISLAND_RADIUS + 2;   // the land is looked for in this many tiles each way from the middle

// The same "random" numbers every time, so the island always looks the same
export function makeRandom(seed) {
  let value = seed;
  return () => {
    value = (value + 0x6d2b79f5) | 0;
    let mixed = Math.imul(value ^ (value >>> 15), 1 | value);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

export function pick(list, random) {
  return list[Math.floor(random() * list.length)];
}

function groundHeight(z) {
  if (z <= -2.5) return HIGH;
  if (z <= 2.5) return MID;
  return LOW;
}

export function material(color, options = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.82, flatShading: true, ...options });
}

export function withShadow(mesh) {
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

// ---------- Shapes ----------

// A lumpy low-poly ball: a treetop, a rock or a cloud
export function lumpyBall(radius, random, lumps = 0.14, detail = 1) {
  const geometry = new THREE.IcosahedronGeometry(radius, detail);
  const position = geometry.attributes.position;
  const moved = new Map();
  const point = new THREE.Vector3();
  for (let i = 0; i < position.count; i += 1) {
    point.fromBufferAttribute(position, i);
    const key = `${point.x.toFixed(3)},${point.y.toFixed(3)},${point.z.toFixed(3)}`;   // corners that touch must move together
    if (!moved.has(key)) moved.set(key, 1 + (random() - 0.5) * lumps * 2);
    point.multiplyScalar(moved.get(key));
    position.setXYZ(i, point.x, point.y, point.z);
  }
  geometry.computeVertexNormals();
  return geometry;
}

// A curved leaf with a crease down the middle, growing along +z and drooping down
export function leafShape(length, width, droop, steps = 6) {
  const vertices = [];
  const indices = [];
  for (let step = 0; step <= steps; step += 1) {
    const along = step / steps;
    const z = along * length;
    const y = -droop * along * along;
    const half = (width / 2) * Math.sin(Math.PI * Math.min(1, along * 0.92 + 0.04)) * (1 - along * 0.2);
    vertices.push(-half, y + half * 0.28, z, 0, y, z, half, y + half * 0.28, z);
    if (step < steps) {
      const row = step * 3;
      indices.push(row, row + 1, row + 3, row + 1, row + 4, row + 3, row + 1, row + 2, row + 4, row + 2, row + 5, row + 4);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

// ---------- Pictures painted on small canvases ----------

export function paintTexture(width, height, paint) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  paint(canvas.getContext("2d"), width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

function playTriangle(context, x, y, size, color) {
  context.fillStyle = color;
  context.beginPath();
  context.moveTo(x - size * 0.4, y - size * 0.55);
  context.lineTo(x + size * 0.6, y);
  context.lineTo(x - size * 0.4, y + size * 0.55);
  context.closePath();
  context.fill();
}

export function waterTexture(random, repeatX, repeatY, streakWide) {
  const texture = paintTexture(256, 256, (context, width, height) => {
    context.fillStyle = COLORS.water;
    context.fillRect(0, 0, width, height);
    for (let i = 0; i < 46; i += 1) {
      const x = random() * width;
      const y = random() * height;
      const light = random() > 0.45;
      context.fillStyle = light ? "rgba(236, 253, 255, 0.5)" : "rgba(24, 150, 186, 0.42)";
      const w = streakWide ? 10 + random() * 26 : 3 + random() * 6;
      const h = streakWide ? 3 + random() * 7 : 28 + random() * 58;
      // Drawn twice so the pattern loops without a seam
      for (const dy of [0, -height, height]) {
        for (const dx of [0, -width, width]) {
          context.beginPath();
          context.ellipse(x + dx, y + dy, w, h, 0, 0, Math.PI * 2);
          context.fill();
        }
      }
    }
  });
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(repeatX, repeatY);
  return texture;
}

export function clipTexture(background, accent) {
  return paintTexture(192, 108, (context, width, height) => {
    const gradient = context.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, background);
    gradient.addColorStop(1, accent);
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
    playTriangle(context, width / 2 - 4, height / 2, 58, "#ffffff");
  });
}

function screenTexture() {
  return paintTexture(512, 300, (context, width, height) => {
    const gradient = context.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#0c4f5a");
    gradient.addColorStop(0.55, "#167a6c");
    gradient.addColorStop(1, "#5fd08a");
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
    // Little hills, so it reads as a video of the jungle
    context.fillStyle = "rgba(8, 60, 50, 0.65)";
    context.beginPath();
    context.moveTo(0, height);
    context.quadraticCurveTo(width * 0.25, height * 0.45, width * 0.55, height * 0.78);
    context.quadraticCurveTo(width * 0.8, height * 0.55, width, height * 0.8);
    context.lineTo(width, height);
    context.fill();
    context.fillStyle = COLORS.cream;
    context.beginPath();
    context.arc(width / 2, height * 0.45, 58, 0, Math.PI * 2);
    context.fill();
    playTriangle(context, width / 2, height * 0.45, 58, "#167a6c");
    // Progress bar
    context.fillStyle = "rgba(255, 255, 255, 0.35)";
    context.fillRect(32, height - 34, width - 64, 10);
    context.fillStyle = COLORS.glow;
    context.fillRect(32, height - 34, (width - 64) * 0.38, 10);
  });
}

// ---------- The ground ----------

function isLand(x, z) {
  if (isRiver(x)) return z >= RIVER_BACK && z <= RIVER_FRONT;   // the river runs right to the edge, so its last waterfall can be seen
  const wobble = Math.sin(x * 1.7 + z * 0.6) * 0.5 + Math.cos(z * 1.9 - x * 0.4) * 0.4;
  return Math.hypot(x, z) <= ISLAND_RADIUS + wobble * 0.55;
}

function isRiver(x) {
  return x > RIVER_MIN_X && x < RIVER_MAX_X;
}

// ---------- The sea ----------

const SEA_VERTEX = `
  varying vec2 vPlace;
  void main() {
    vPlace = position.xz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const SEA_FRAGMENT = `
  uniform float uTime;
  uniform sampler2D uShore;
  uniform float uRange;
  uniform float uMaxDistance;
  uniform vec2 uFall;
  uniform vec3 uDeep;
  uniform vec3 uShallow;
  uniform vec3 uFoam;
  uniform float uPixel;
  varying vec2 vPlace;

  float hash(vec2 value) {
    return fract(sin(dot(value, vec2(127.1, 311.7))) * 43758.5453);
  }

  void main() {
    // Every screen pixel inside one big square uses that square's spot on the sea, so the water draws as chunky pixels
    vec2 grid = gl_FragCoord.xy / uPixel;
    vec2 p = vPlace - dFdx(vPlace) * fract(grid.x) * uPixel - dFdy(vPlace) * fract(grid.y) * uPixel;
    vec2 cell = floor(grid);
    float t = uTime;
    float shore = texture2D(uShore, (p + uRange) / (2.0 * uRange)).r * uMaxDistance;

    // Turquoise in the shallows, deeper blue further out
    vec3 color = mix(uShallow, uDeep, floor(smoothstep(0.1, 6.0, shore) * 9.0 + 0.5) / 9.0);   // in color steps, like pixel art

    // Little dashes of pixels gliding across the surface, each row at its own speed, twinkling on and off
    if (mod(cell.y, 3.0) < 1.0) {
      float rowSeed = hash(vec2(cell.y, 4.0));
      float along = cell.x + floor(t * (0.7 + rowSeed * 1.3)) + floor(rowSeed * 97.0);
      float dash = floor(along / 11.0);
      float dashSeed = hash(vec2(dash, cell.y));
      float dashLength = 2.0 + floor(hash(vec2(cell.y, dash + 7.0)) * 4.0);
      float twinkle = step(0.3, sin(t * (0.5 + dashSeed) + dashSeed * 40.0) * 0.5 + 0.5);
      float lit = step(0.84, dashSeed) * step(mod(along, 11.0), dashLength - 1.0) * twinkle;
      color = mix(color, uFoam, lit * 0.62);
    }

    // Waves rolling away from the island
    float wave = smoothstep(0.07, 0.0, abs(fract(shore * 0.85 - t * 0.16) - 0.5));
    color = mix(color, uFoam, step(0.5, wave) * step(shore, 2.4) * 0.32);

    // Water streaming away from the bottom of the waterfall
    float spread = 1.05 + max(0.0, p.y - uFall.y) * 0.3;
    float inStream = smoothstep(spread, spread * 0.45, abs(p.x - uFall.x)) * smoothstep(uFall.y - 0.05, uFall.y + 0.1, p.y) * smoothstep(13.5, 7.5, p.y);
    float dashes = smoothstep(0.55, 0.95, sin(p.y * 2.3 - t * 2.4 + sin(p.x * 3.1) * 0.9));
    color = mix(color, uShallow, inStream * 0.6);
    color = mix(color, uFoam, step(0.5, inStream * dashes) * 0.55);

    // Rings where the waterfall lands
    float fromFall = length((p - uFall) * vec2(1.0, 1.25));
    float rings = smoothstep(0.25, 0.9, sin(fromFall * 5.0 - t * 3.2)) * smoothstep(4.6, 0.8, fromFall);
    color = mix(color, uFoam, step(0.5, rings) * step(uFall.y - 0.05, p.y) * 0.5);
    float splash = smoothstep(1.5, 0.75, fromFall + sin(atan(p.y - uFall.y, p.x - uFall.x) * 7.0 + t * 3.0) * 0.1);
    color = mix(color, uFoam, step(0.5, splash) * step(uFall.y - 0.05, p.y) * 0.9);

    // White foam hugging the shore
    float edge = 0.2 + sin(p.x * 2.1 + t) * 0.07 + sin(p.y * 1.7 - t * 1.2) * 0.07;
    color = mix(color, uFoam, step(shore, edge));

    gl_FragColor = vec4(color, 1.0);
    #include <colorspace_fragment>
  }
`;

function buildSea(root, random, pixelRatio) {
  // How far every spot of sea is from the island, worked out once and stored as a small picture
  const SIZE = 128;
  const RANGE = 22;
  const MAX_DISTANCE = 8;
  const land = [];
  for (let x = -GRID; x <= GRID; x += 1) {
    for (let z = -GRID; z <= GRID; z += 1) {
      if (isLand(x, z)) land.push([x, z]);
    }
  }
  const distances = new Uint8Array(SIZE * SIZE);
  for (let row = 0; row < SIZE; row += 1) {
    for (let column = 0; column < SIZE; column += 1) {
      const x = ((column + 0.5) / SIZE) * RANGE * 2 - RANGE;
      const z = ((row + 0.5) / SIZE) * RANGE * 2 - RANGE;
      let nearest = Infinity;
      for (const [landX, landZ] of land) {
        const across = Math.max(Math.abs(x - landX) - 0.5, 0);
        const down = Math.max(Math.abs(z - landZ) - 0.5, 0);
        nearest = Math.min(nearest, across * across + down * down);
      }
      distances[row * SIZE + column] = Math.min(1, Math.sqrt(nearest) / MAX_DISTANCE) * 255;
    }
  }
  const shore = new THREE.DataTexture(distances, SIZE, SIZE, THREE.RedFormat);
  shore.magFilter = THREE.LinearFilter;
  shore.minFilter = THREE.LinearFilter;
  shore.needsUpdate = true;

  const uniforms = {
    uTime: { value: 0 },
    uShore: { value: shore },
    uRange: { value: RANGE },
    uMaxDistance: { value: MAX_DISTANCE },
    uFall: { value: new THREE.Vector2(RIVER_X, EDGE + 0.05) },
    uDeep: { value: new THREE.Color("#1f9fd6") },
    uShallow: { value: new THREE.Color("#63e6df") },
    uFoam: { value: new THREE.Color("#f3fffd") },
    uPixel: { value: 5 * pixelRatio },   // how big the water's pixels are, in page pixels
  };
  const geometry = new THREE.PlaneGeometry(240, 240);
  geometry.rotateX(-Math.PI / 2);
  const surface = new THREE.Mesh(geometry, new THREE.ShaderMaterial({ uniforms, vertexShader: SEA_VERTEX, fragmentShader: SEA_FRAGMENT, toneMapped: false }));
  surface.position.y = SEA_LEVEL;
  root.add(surface);

  // Rocks and lily pads scattered near the island
  for (const [x, z, size] of [[-11.1, 4, 0.7], [-10.2, 5.3, 0.38], [10.6, 3.7, 0.6], [8, 8.5, 0.52], [9, 7.9, 0.3], [-5.9, 10.3, 0.46]]) {
    const rockMesh = withShadow(new THREE.Mesh(lumpyBall(size, random, 0.2, 0), material(pick(COLORS.rock, random))));
    rockMesh.scale.y = 0.8;
    rockMesh.position.set(x, SEA_LEVEL + size * 0.2, z);
    root.add(rockMesh);
  }
  const padMaterial = material("#58b84a");
  for (const [x, z, size] of [[-3.6, 10.8, 0.36], [-2.7, 11.5, 0.26], [-4.3, 11.6, 0.22], [6.8, 10.2, 0.32], [7.6, 10.8, 0.24]]) {
    const pad = new THREE.Mesh(new THREE.CylinderGeometry(size, size, 0.04, 9), padMaterial);
    pad.position.set(x, SEA_LEVEL + 0.03, z);
    root.add(pad);
  }

  return (time) => { uniforms.uTime.value = time; };
}

// ---------- Water ----------

function buildWater(root, random) {
  const textures = [];
  const add = (texture, speed) => { textures.push({ texture, speed }); return texture; };
  const waterMaterial = (map) => new THREE.MeshStandardMaterial({ map, roughness: 0.28, metalness: 0.05, emissive: "#0b6f86", emissiveIntensity: 0.28 });

  // Flat parts of the river: [from z, to z, height]
  const stretches = [[RIVER_BACK - 0.5, -2.5, HIGH], [-2.5, 2.5, MID], [2.5, EDGE, LOW]];
  for (const [from, to, y] of stretches) {
    const length = to - from;
    const texture = add(waterTexture(random, 1, length / 2.4, false), 0.28);
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(RIVER_MAX_X - RIVER_MIN_X, length), waterMaterial(texture));
    plane.rotation.x = -Math.PI / 2;
    plane.position.set(RIVER_X, y - 0.1, (from + to) / 2);
    plane.receiveShadow = true;
    root.add(plane);
  }

  // Waterfalls: [z, top, bottom]
  const falls = [[-2.48, HIGH - 0.08, MID - 0.14], [2.52, MID - 0.08, LOW - 0.14], [EDGE + 0.03, LOW - 0.08, SEA_LEVEL]];
  for (const [z, top, bottom] of falls) {
    const height = top - bottom;
    const texture = add(waterTexture(random, 1, height / 2.4, false), 0.95);
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(RIVER_MAX_X - RIVER_MIN_X, height), waterMaterial(texture));
    plane.position.set(RIVER_X, (top + bottom) / 2, z);
    root.add(plane);
  }

  // Foam where each waterfall lands
  const foamMaterial = new THREE.MeshStandardMaterial({ color: COLORS.foam, roughness: 0.7, flatShading: true });
  const foam = [];
  const SEA_SPLASH = 2;   // the big splash where the last waterfall hits the sea
  const landings = [[-2.25, MID - 0.05], [2.75, LOW - 0.05], [EDGE + 0.35, SEA_LEVEL + 0.02], [-2.48, HIGH - 0.02], [2.52, MID - 0.02]];
  landings.forEach(([z, y], landing) => {
    const big = landing <= SEA_SPLASH;
    const seaSplash = landing === SEA_SPLASH;
    const puffs = seaSplash ? 20 : big ? 11 : 6;
    for (let i = 0; i < puffs; i += 1) {
      const size = seaSplash ? 0.14 + random() * 0.2 : big ? 0.12 + random() * 0.14 : 0.05 + random() * 0.07;
      const puff = new THREE.Mesh(lumpyBall(size, random, 0.1, 0), foamMaterial);
      puff.position.set(RIVER_MIN_X + 0.1 + random() * 1.8, y, z + (random() - 0.5) * (seaSplash ? 0.7 : big ? 0.34 : 0.05));
      foam.push({ mesh: puff, phase: random() * 6.28, speed: 2.2 + random() * 2.2, baseY: y });
      root.add(puff);
    }
  });

  return (time, delta) => {
    for (const { texture, speed } of textures) texture.offset.y = (texture.offset.y + delta * speed) % 1;
    for (const puff of foam) {
      const wave = Math.sin(time * puff.speed + puff.phase);
      puff.mesh.scale.setScalar(1 + wave * 0.28);
      puff.mesh.position.y = puff.baseY + (wave + 1) * 0.045;
    }
  };
}

// ---------- The video screen and the clip cards ----------

function buildScreen(root) {
  const group = new THREE.Group();
  group.position.set(RIVER_X, HIGH, RIVER_BACK - 0.05);
  // The wooden posts, frame and roof come from the Blender island (frontend/blender/island.py)

  const screenMaterial = new THREE.MeshBasicMaterial({ map: screenTexture(), toneMapped: false });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(3.14, 1.8), screenMaterial);
  screen.position.set(0, 1.72, 0.125);
  group.add(screen);

  // Soft glow from the screen on the water
  const glow = new THREE.PointLight(COLORS.glow, 6, 6, 1.8);
  glow.position.set(0, 1.5, 1);
  group.add(glow);
  root.add(group);
  return () => {};
}

function buildClipCards(root, random) {
  // The route down the river, from the screen to the edge of the island, then out across the sea
  // Each waterfall: float past its edge, then arc down in front of the falling water (never through it)
  const route = [
    [RIVER_BACK + 0.4, HIGH - 0.04], [-2.62, HIGH - 0.04], [-2.38, HIGH - 0.04], [-2.08, (HIGH + MID) / 2], [-1.93, MID + 0.05], [-1.7, MID - 0.04],
    [2.4, MID - 0.04], [2.62, MID - 0.04], [2.92, (MID + LOW) / 2], [3.07, LOW + 0.05], [3.3, LOW - 0.04],
    [EDGE - 0.08, LOW - 0.04], [EDGE + 0.13, LOW - 0.04], [EDGE + 0.43, (LOW + SEA_LEVEL) / 2], [EDGE + 0.58, SEA_LEVEL + 0.04], [EDGE + 0.85, SEA_LEVEL + 0.02], [EDGE + 6.5, SEA_LEVEL + 0.02],
  ].map(([z, y]) => new THREE.Vector2(z, y));
  const lengths = [0];
  for (let i = 1; i < route.length; i += 1) lengths.push(lengths[i - 1] + route[i].distanceTo(route[i - 1]));
  const total = lengths[lengths.length - 1];

  const palettes = [["#f06a4a", "#f7b267"], ["#2d6cdf", "#4fd1e0"], ["#7b4ddb", "#e36bb0"], ["#159a6b", "#b7e34d"]];
  const textures = palettes.map(([from, to]) => clipTexture(from, to));
  const cardBody = new RoundedBoxGeometry(0.86, 0.09, 0.52, 2, 0.03);
  const bodyMaterial = material(COLORS.cream, { flatShading: false });
  const faceShape = new THREE.PlaneGeometry(0.74, 0.42);
  const cards = [];

  const COUNT = 14;
  for (let i = 0; i < COUNT; i += 1) {
    const card = new THREE.Group();
    card.add(withShadow(new THREE.Mesh(cardBody, bodyMaterial)));
    const face = new THREE.Mesh(faceShape, new THREE.MeshStandardMaterial({ map: textures[i % textures.length], roughness: 0.5, emissive: "#ffffff", emissiveMap: textures[i % textures.length], emissiveIntensity: 0.18 }));
    face.rotation.x = -Math.PI / 2;
    face.position.y = 0.052;
    card.add(face);
    root.add(card);
    cards.push({ card, start: i / COUNT, lane: (random() - 0.5) * 0.92, phase: random() * 6.28, spin: (random() - 0.5) * 0.7 });
  }

  // Where a card is after travelling this far along the route (x = along the river, y = height)
  const point = new THREE.Vector2();
  function placeAt(distance) {
    const clamped = Math.min(total, Math.max(0, distance));
    let segment = 0;
    while (segment < route.length - 2 && lengths[segment + 1] < clamped) segment += 1;
    const along = (clamped - lengths[segment]) / (lengths[segment + 1] - lengths[segment]);
    return point.copy(route[segment]).lerp(route[segment + 1], along);
  }

  const SECONDS_PER_TRIP = 34;
  return (time) => {
    for (const item of cards) {
      const progress = ((time / SECONDS_PER_TRIP + item.start) % 1);
      const distance = progress * total;
      // Tip by looking a little behind and ahead, so a card tilts smoothly over each edge
      const behind = placeAt(distance - 0.08).clone();
      const ahead = placeAt(distance + 0.18).clone();
      const slope = Math.atan2(behind.y - ahead.y, ahead.x - behind.x);
      const here = placeAt(distance);
      const bob = slope < 0.2 ? Math.sin(time * 2 + item.phase) * 0.018 : 0;
      const z = here.x;
      const fanOut = 1 + Math.max(0, z - (EDGE + 0.5)) * 0.75;   // out at sea, the clips spread apart
      const level = Math.cos(Math.min(slope, Math.PI / 2));   // 1 when flat, 0 when dropping straight down
      item.card.position.set(RIVER_X + item.lane * fanOut + Math.sin(time * 0.7 + item.phase) * 0.05, here.y + 0.07 + bob, z);
      // While falling a card stays square to the waterfall, so no corner swings back into the water
      item.card.rotation.set(slope + Math.sin(time * 1.4 + item.phase) * 0.03 * level, (item.spin + Math.sin(time * 0.5 + item.phase) * 0.12) * level, Math.cos(time * 1.2 + item.phase) * 0.03 * level);
      // Grow as they leave the screen, shrink as they fall off the island
      const fadeIn = Math.min(1, progress / 0.035);
      const fadeOut = Math.min(1, (1 - progress) / 0.05);
      item.card.scale.setScalar(Math.max(0.001, Math.min(fadeIn, fadeOut)));
    }
  };
}

// ---------- Plants and things ----------

function buildCrystals(root, random) {
  const shape = new THREE.OctahedronGeometry(0.2, 0);
  const crystalMaterial = new THREE.MeshStandardMaterial({ color: COLORS.glow, emissive: "#22d6c4", emissiveIntensity: 0.65, roughness: 0.25, flatShading: true });
  const crystals = [[-4.3, -1.7, 1.15], [3.25, 3.9, 1.1], [-2.8, -5.1, 1.5], [4.3, -4.6, 1.25]].map(([x, z, lift]) => {
    const mesh = withShadow(new THREE.Mesh(shape, crystalMaterial));
    mesh.scale.y = 1.5;
    const baseY = groundHeight(z) + lift * 0.7;
    mesh.position.set(x, baseY, z);
    root.add(mesh);
    return { mesh, baseY, phase: random() * 6.28 };
  });
  return (time) => {
    for (const crystal of crystals) {
      crystal.mesh.rotation.y = time * 0.9 + crystal.phase;
      crystal.mesh.position.y = crystal.baseY + Math.sin(time * 1.5 + crystal.phase) * 0.1;
    }
  };
}

function buildVines(root, random) {
  const vine = material("#2d8f46");
  const swaying = [];
  const spots = [[-4.2, -2.45, HIGH, 1.15], [-2.9, -2.45, HIGH, 0.8], [-0.9, -2.45, HIGH, 1.1], [3.6, -2.45, HIGH, 1], [-3.9, 2.55, MID, 0.8], [-1.2, 2.55, MID, 0.72], [3.5, 2.55, MID, 0.85], [5, 2.55, MID, 0.62]];
  for (const [x, z, top, length] of spots) {
    const group = new THREE.Group();
    group.position.set(x, top - 0.04, z);
    const strand = new THREE.Mesh(new THREE.BoxGeometry(0.05, length, 0.05), vine);
    strand.position.y = -length / 2;
    group.add(strand);
    for (let i = 1; i <= 3; i += 1) {
      const leaf = new THREE.Mesh(lumpyBall(0.09, random, 0.08, 0), material(pick(COLORS.leaves, random)));
      leaf.position.set(i % 2 ? 0.07 : -0.07, -length * (i / 3.3), 0.03);
      leaf.scale.set(1, 1.4, 0.4);
      group.add(leaf);
    }
    root.add(group);
    swaying.push({ group, phase: random() * 6.28 });
  }
  return (time) => {
    for (const item of swaying) item.group.rotation.z = Math.sin(time * 1.2 + item.phase) * 0.05;
  };
}

function buildBirds(root) {
  const wing = new THREE.BufferGeometry();
  wing.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, -0.1, 0, 0, 0.12, 0.42, 0, -0.04], 3));
  wing.computeVertexNormals();
  const palette = ["#f06a4a", "#2d6cdf"];
  const birds = palette.map((color, index) => {
    const group = new THREE.Group();
    const skin = material(color, { side: THREE.DoubleSide });
    const body = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.42, 5), skin);
    body.rotation.x = Math.PI / 2;
    group.add(body);
    const left = new THREE.Mesh(wing, skin);
    const right = new THREE.Mesh(wing, skin);
    right.scale.x = -1;
    group.add(left, right);
    root.add(group);
    return { group, left, right, radius: 10.8 + index * 1.2, height: 8.4 + index * 0.8, speed: 0.13 + index * 0.05, phase: index * 2.2 };
  });
  return (time) => {
    for (const bird of birds) {
      const angle = time * bird.speed + bird.phase;
      bird.group.position.set(Math.cos(angle) * bird.radius, bird.height + Math.sin(angle * 2.4) * 0.4, Math.sin(angle) * bird.radius);
      bird.group.rotation.y = -angle;
      const flap = Math.sin(time * 9 + bird.phase) * 0.65;
      bird.left.rotation.z = flap;
      bird.right.rotation.z = -flap;
    }
  };
}

function buildClouds(scene, random) {
  const whiteMaterial = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 1, transparent: true, opacity: 0.92 });
  const clouds = [[14, 9.5, -8, 0.8, 0.12], [-8, 11, -11, 1, 0.08]].map(([x, y, z, size, speed]) => {
    const group = new THREE.Group();
    for (let i = 0; i < 6; i += 1) {
      const puff = new THREE.Mesh(new THREE.SphereGeometry((0.62 + random() * 0.6) * size, 14, 10), whiteMaterial);
      puff.position.set((i - 2.5) * 0.76 * size, random() * 0.32 * size, (random() - 0.5) * 0.9 * size);
      puff.scale.y = 0.68;
      group.add(puff);
    }
    group.position.set(x, y, z);
    scene.add(group);
    return { group, speed, startX: x, startZ: z };
  });
  return (time) => {
    for (const cloud of clouds) {
      // Drift across the screen and wrap around, far enough out that the jump can't be seen
      const travel = ((time * cloud.speed * 2 + 22) % 44) - 22;
      cloud.group.position.x = cloud.startX + travel * 0.7;
      cloud.group.position.z = cloud.startZ - travel * 0.7;
    }
  };
}

// ---------- Small details: grass, stones, moss, a campfire, a dock, and little animals ----------

// Many copies of one small shape, drawn in one go. items: [{ x, y, z, rx, ry, rz, sx, sy, sz, color }]
export function instanced(root, geometry, baseMaterial, items, shadows = false) {
  if (!items.length) return;
  const mesh = new THREE.InstancedMesh(geometry, baseMaterial, items.length);
  const matrix = new THREE.Matrix4();
  const rotation = new THREE.Quaternion();
  const euler = new THREE.Euler();
  const position = new THREE.Vector3();
  const scale = new THREE.Vector3();
  const color = new THREE.Color();
  items.forEach((item, i) => {
    rotation.setFromEuler(euler.set(item.rx ?? 0, item.ry ?? 0, item.rz ?? 0));
    matrix.compose(position.set(item.x, item.y, item.z), rotation, scale.set(item.sx ?? 1, item.sy ?? 1, item.sz ?? 1));
    mesh.setMatrixAt(i, matrix);
    mesh.setColorAt(i, color.set(item.color));
  });
  mesh.castShadow = shadows;
  mesh.receiveShadow = true;
  root.add(mesh);
}

function buildCampfire(root) {
  const fire = new THREE.Group();
  fire.position.set(-3.6, MID, -0.9);
  // The ring of stones and the logs come from the Blender island; code adds the flames, glow and smoke
  const outer = new THREE.Mesh(new THREE.ConeGeometry(0.15, 0.42, 6), new THREE.MeshBasicMaterial({ color: "#ff8a1f", toneMapped: false }));
  outer.position.y = 0.3;
  const inner = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.28, 6), new THREE.MeshBasicMaterial({ color: "#ffe066", toneMapped: false }));
  inner.position.y = 0.26;
  fire.add(outer, inner);
  const glow = new THREE.PointLight("#ff9a3c", 3.5, 3.2, 1.8);
  glow.position.y = 0.5;
  fire.add(glow);
  // Smoke puffs that rise, grow and fade, one after another
  const puffs = [];
  for (let i = 0; i < 5; i += 1) {
    const puff = new THREE.Mesh(new THREE.IcosahedronGeometry(0.11, 0), new THREE.MeshStandardMaterial({ color: "#eef3f2", roughness: 1, flatShading: true, transparent: true, depthWrite: false }));
    fire.add(puff);
    puffs.push(puff);
  }
  root.add(fire);
  return (time) => {
    const flicker = 1 + Math.sin(time * 13) * 0.08 + Math.sin(time * 21.7) * 0.06;
    outer.scale.set(1, flicker, 1);
    inner.scale.set(1, 2 - flicker, 1);
    glow.intensity = 3.2 * flicker;
    puffs.forEach((puff, i) => {
      const rise = ((time / 3.2) + i / puffs.length) % 1;
      puff.position.set(Math.sin(time * 0.8 + i) * 0.12 + rise * 0.35, 0.55 + rise * 1.7, -rise * 0.2);
      puff.scale.setScalar(0.6 + rise * 1.1);
      puff.material.opacity = 0.6 * (1 - rise);
    });
  };
}

function buildBoat(root) {
  // The pier sticks out from the low step of the island on the right, with a ladder up the cliff
  let edgeX = GRID;
  while (edgeX > 0 && !isLand(edgeX, 4)) edgeX -= 1;
  const start = edgeX + 0.5;
  const wood = material(COLORS.wood);
  // The pier and the ladder up the cliff come from the Blender island; code adds the bobbing boat

  // A little rowboat tied up at the end, bobbing on the waves
  const boat = new THREE.Group();
  const hull = withShadow(new THREE.Mesh(new RoundedBoxGeometry(1.1, 0.26, 0.5, 2, 0.08), material("#b5653a")));
  boat.add(hull);
  const inside = new THREE.Mesh(new RoundedBoxGeometry(0.92, 0.1, 0.36, 2, 0.04), material("#7d4325"));
  inside.position.y = 0.1;
  boat.add(inside);
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.05, 0.38), wood);
  seat.position.y = 0.14;
  boat.add(seat);
  for (const side of [-1, 1]) {
    const oar = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.03, 0.06), material(COLORS.cream));
    oar.position.set(0.05, 0.15, side * 0.28);
    oar.rotation.y = side * 0.35;
    boat.add(oar);
  }
  boat.position.set(start + 2.6, SEA_LEVEL + 0.1, 4.7);
  boat.rotation.y = 0.5;
  root.add(boat);
  return (time) => {
    boat.position.y = SEA_LEVEL + 0.1 + Math.sin(time * 1.3) * 0.04;
    boat.rotation.z = Math.sin(time * 1.1) * 0.05;
    boat.rotation.x = Math.cos(time * 0.9) * 0.04;
  };
}

function buildCritters(root) {
  // Butterflies wandering over the grass, wings flapping
  const wingShape = new THREE.CircleGeometry(0.07, 5);
  wingShape.translate(0.06, 0, 0);
  const butterflies = [["#ffd34d", -2.5, -3, HIGH], ["#ff9ec7", 3.6, 2, MID], ["#ffffff", -3.5, 4, LOW]].map(([color, x, z, ground], index) => {
    const group = new THREE.Group();
    const skin = new THREE.MeshStandardMaterial({ color, roughness: 0.8, side: THREE.DoubleSide });
    const left = new THREE.Mesh(wingShape, skin);
    const right = new THREE.Mesh(wingShape, skin);
    left.rotation.x = -Math.PI / 2;
    right.rotation.x = -Math.PI / 2;
    right.scale.x = -1;
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.02, 0.1), material("#3a2a1a"));
    group.add(left, right, body);
    root.add(group);
    return { group, left, right, x, z, ground, phase: index * 2.1 };
  });

  // Fish that leap out of the sea now and then
  const fishBody = new THREE.ConeGeometry(0.07, 0.3, 6);
  fishBody.rotateZ(-Math.PI / 2);
  const fishTail = new THREE.ConeGeometry(0.06, 0.12, 4);
  fishTail.rotateZ(Math.PI / 2);
  fishTail.translate(-0.2, 0, 0);
  const fish = [["#ff8a3d", -7, 12, 0], ["#ffd34d", 12, -2, Math.PI / 2]].map(([color, x, z, heading], index) => {
    const group = new THREE.Group();
    const skin = material(color);
    group.add(new THREE.Mesh(fishBody, skin), new THREE.Mesh(fishTail, skin));
    group.rotation.y = heading;
    root.add(group);
    const splash = new THREE.Mesh(new THREE.TorusGeometry(0.22, 0.04, 4, 12), new THREE.MeshBasicMaterial({ color: "#f3fffd", transparent: true, depthWrite: false }));
    splash.rotation.x = Math.PI / 2;
    splash.position.set(x, SEA_LEVEL + 0.02, z);
    root.add(splash);
    return { group, splash, x, z, heading, offset: index * 3.4 };
  });

  // A parrot sitting on top of the video screen
  const parrot = new THREE.Group();
  const feathers = material("#e8443a");
  const bodyMesh = withShadow(new THREE.Mesh(new THREE.IcosahedronGeometry(0.13, 1), feathers));
  bodyMesh.scale.set(0.85, 1.25, 0.85);
  parrot.add(bodyMesh);
  const head = new THREE.Group();
  head.position.y = 0.2;
  head.add(new THREE.Mesh(new THREE.IcosahedronGeometry(0.09, 1), feathers));
  const beak = new THREE.Mesh(new THREE.ConeGeometry(0.035, 0.09, 4), material("#ffcf3d"));
  beak.rotation.x = Math.PI / 2;
  beak.position.set(0, -0.01, 0.1);
  head.add(beak);
  parrot.add(head);
  const blue = material("#2d6cdf");
  for (const side of [1, -1]) {   // a folded wing on each side, tucked against the body
    const wing = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.17, 0.13), blue);
    wing.position.set(side * 0.1, -0.02, -0.02);
    wing.rotation.x = 0.15;
    parrot.add(wing);
  }
  // The tail sweeps back and down behind it, over the back of the roof
  const tail = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.22, 0.03), blue);
  tail.position.set(0, -0.08, -0.13);
  tail.rotation.x = 1.1;
  parrot.add(tail);
  // Two little yellow feet gripping the roof
  for (const side of [1, -1]) {
    const foot = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.06, 0.06), material("#ffcf3d"));
    foot.position.set(side * 0.045, -0.18, 0.02);
    parrot.add(foot);
  }
  // Perched on the screen's roof (the frame stands at z = RIVER_BACK - 0.05; its roof top is 3 above HIGH)
  parrot.position.set(RIVER_X + 1.25, HIGH + 3.2, RIVER_BACK - 0.02);
  parrot.rotation.y = 0.6;
  root.add(parrot);

  return (time) => {
    for (const item of butterflies) {
      const t = time * 0.45 + item.phase;
      item.group.position.set(item.x + Math.sin(t) * 1.1, item.ground + 0.7 + Math.sin(t * 2.3) * 0.25, item.z + Math.sin(t * 0.7) * 1.1);
      item.group.rotation.y = Math.atan2(Math.cos(t) * 1.1, Math.cos(t * 0.7) * 0.77);
      const flap = Math.sin(time * 18 + item.phase) * 0.9;
      item.left.rotation.y = flap;
      item.right.rotation.y = -flap;
    }
    for (const item of fish) {
      const cycle = ((time + item.offset) % 7) / 1.1;   // a 1.1 second leap every 7 seconds
      const leaping = cycle < 1;
      item.group.visible = leaping;
      if (leaping) {
        const along = (cycle - 0.5) * 1.3;
        item.group.position.set(item.x + Math.cos(item.heading) * along, SEA_LEVEL + Math.sin(cycle * Math.PI) * 0.8, item.z - Math.sin(item.heading) * along);
        item.group.rotation.z = Math.cos(cycle * Math.PI) * 0.9;
      }
      const ripple = Math.min(1, cycle % 1.6);
      item.splash.scale.setScalar(0.4 + ripple * 1.4);
      item.splash.material.opacity = cycle < 1.6 ? 0.7 * (1 - ripple) : 0;
    }
    head.rotation.x = Math.max(0, Math.sin(time * 1.7)) * 0.35;
    head.rotation.y = Math.sin(time * 0.6) * 0.5;
  };
}

// ---------- The island itself, made in Blender ----------

// Everything solid and still - ground, cliffs, trees, plants, rocks, hut, bridge, dock, screen frame -
// is built by frontend/blender/island.py (with soft shadows baked in) and saved as public/models/island.glb.
// Plants that sway are separate objects with "sway" and "speed" numbers (glTF extras -> userData).
const ISLAND_URL = "/models/island.glb";
let islandPromise = null;
function loadIslandModel() {
  if (!islandPromise) {
    const draco = new DRACOLoader().setDecoderPath("/draco/");   // the island is Draco-compressed
    islandPromise = new GLTFLoader().setDRACOLoader(draco).loadAsync(ISLAND_URL).finally(() => draco.dispose());
    islandPromise.catch(() => { islandPromise = null; });   // let a later visit try again
  }
  return islandPromise;
}

function loadIsland(root, onReady) {
  const swaying = [];
  let island = null;
  loadIslandModel().then((gltf) => {
    island = gltf.scene.clone(true);
    island.traverse((object) => {
      if (object.isMesh) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
      if (object.userData.sway) {
        swaying.push({ object, amount: object.userData.sway, speed: object.userData.speed ?? 1,
          phase: Math.random() * 6.28, baseX: object.rotation.x, baseZ: object.rotation.z });
      }
    });
    root.add(island);
    onReady();
  }).catch(() => {});   // no island file: the sea, river and cards still show
  return (time) => {
    for (const item of swaying) {
      item.object.rotation.x = item.baseX + Math.sin(time * item.speed + item.phase) * item.amount;
      item.object.rotation.z = item.baseZ + Math.cos(time * item.speed * 0.8 + item.phase) * item.amount;
    }
  };
}

// ---------- Putting it together ----------

export function createIslandScene(canvas, { still = false, framing = "hero" } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, framing === "backdrop" ? 1.5 : 2));   // a backdrop can be a little softer, and lighter to draw
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 200);
  camera.position.set(30, 25.5, 30);   // the isometric angle
  camera.lookAt(0, 1.4, 0);

  scene.add(new THREE.HemisphereLight("#e6fbff", "#47703a", 1.9));
  const sun = new THREE.DirectionalLight("#fff3d6", 3.1);
  sun.position.set(5, 18, 13);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -16;
  sun.shadow.camera.right = 16;
  sun.shadow.camera.top = 16;
  sun.shadow.camera.bottom = -16;
  sun.shadow.bias = -0.0006;
  sun.shadow.normalBias = 0.025;
  scene.add(sun);

  const random = makeRandom(20261105);
  const root = new THREE.Group();
  scene.add(root);
  const updates = [
    loadIsland(root, () => { if (still) draw(); }),
    buildWater(root, random),
    buildScreen(root),
    buildClipCards(root, random),
    buildCrystals(root, random),
    buildVines(root, random),
    buildBirds(root),
    buildClouds(scene, random),
    buildSea(root, random, renderer.getPixelRatio()),
    buildCampfire(root),
    buildBoat(root),
    buildCritters(root),
  ];

  // Fit the island to the page: on wide screens it sits on the right, next to the words
  function fit() {
    const parent = canvas.parentElement;
    const width = parent.clientWidth;
    const height = parent.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    const aspect = width / height;
    const wide = aspect > 1.15;
    const backdrop = framing === "backdrop";
    // The camera was set up for an island 7 tiles out; step back to fit this one (less on phones, where it sits below the words)
    const bigger = wide ? ISLAND_RADIUS / 7 : 1 + (ISLAND_RADIUS / 7 - 1) * 0.35;
    const halfHeight = (backdrop ? Math.max(8, 10 / aspect) : wide ? 9 : Math.max(11, 12.5 / aspect)) * bigger;
    const halfWidth = halfHeight * aspect;
    let shiftX = wide ? halfWidth * 0.42 : 0;
    let shiftY = wide ? 0.3 : -halfHeight * 0.36;   // narrow screens: the island sits below the words
    if (backdrop) {   // low on the screen, behind the page's content
      shiftX = wide ? halfWidth * 0.2 : 0;
      shiftY = -halfHeight * 0.62;
    }
    view.left = -halfWidth - shiftX;
    view.right = halfWidth - shiftX;
    view.top = halfHeight - shiftY;
    view.bottom = -halfHeight - shiftY;
    aim();
    draw();
  }

  // What the camera shows (set by fit), and the "dive" camera move: a glide and zoom down into the splash
  // where the last waterfall meets the sea. Started by a "cascade:camera" event (see components/LeafTransition.jsx).
  const view = { left: -10, right: 10, top: 10, bottom: -10 };
  let move = null;
  const smooth = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
  function aim() {
    let zoom = 1;
    let centreX = (view.left + view.right) / 2;
    let centreY = (view.top + view.bottom) / 2;
    if (move) {
      const eased = smooth(Math.min(1, (performance.now() - move.start) / move.duration));
      zoom = 1 + eased * 9;
      centreX += (move.x - centreX) * eased;
      centreY += (move.y - centreY) * eased;
    }
    const halfWidth = (view.right - view.left) / 2 / zoom;
    const halfHeight = (view.top - view.bottom) / 2 / zoom;
    camera.left = centreX - halfWidth;
    camera.right = centreX + halfWidth;
    camera.top = centreY + halfHeight;
    camera.bottom = centreY - halfHeight;
    camera.updateProjectionMatrix();
  }
  function handleCamera(event) {
    if (event.detail?.move !== "dive" || still) return;
    const splash = root.localToWorld(new THREE.Vector3(RIVER_X, SEA_LEVEL, EDGE + 0.9)).applyMatrix4(camera.matrixWorldInverse);
    move = { start: performance.now(), duration: event.detail.duration ?? 1000, x: splash.x, y: splash.y };
  }

  // The island turns very slightly toward the mouse
  const mouse = { x: 0, smoothX: 0 };
  function handleMouse(event) {
    mouse.x = (event.clientX / window.innerWidth - 0.5) * 2;
  }

  let frame = 0;
  let lastTime = 0;
  const startTime = performance.now();

  function draw(delta = 0) {
    const time = still ? 7 : (performance.now() - startTime) / 1000 + 7;
    for (const update of updates) update(time, delta);
    if (move) {
      aim();   // during the dive the island stops turning toward the mouse
    } else {
      mouse.smoothX += (mouse.x - mouse.smoothX) * 0.04;
      root.rotation.y = mouse.smoothX * 0.055;
    }
    renderer.render(scene, camera);
  }

  function loop(now) {
    const delta = Math.min(0.05, (now - lastTime) / 1000 || 0);
    lastTime = now;
    draw(delta);
    frame = requestAnimationFrame(loop);
  }

  const observer = new ResizeObserver(fit);
  observer.observe(canvas.parentElement);
  fit();
  if (!still) {
    window.addEventListener("pointermove", handleMouse);
    window.addEventListener("cascade:camera", handleCamera);
    frame = requestAnimationFrame(loop);
  }

  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("pointermove", handleMouse);
    window.removeEventListener("cascade:camera", handleCamera);
    observer.disconnect();
    const seen = new Set();
    const free = (thing) => { if (thing && !seen.has(thing)) { seen.add(thing); thing.dispose?.(); } };
    scene.traverse((object) => {
      free(object.geometry);
      for (const item of [object.material].flat()) {
        if (!item) continue;
        free(item.map);
        free(item.emissiveMap);
        free(item);
      }
    });
    renderer.dispose();
    renderer.forceContextLoss();
  };
}
