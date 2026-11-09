import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

// The 3D world behind Landing and Projects: a rainforest island in the sea, seen from an isometric camera.
// One big video screen feeds a river, and clip cards ride it down the waterfalls: one video becomes many clips.
// Everything is drawn from code (no image files), so colors and sizes can be changed right here.
//
// createIslandScene(canvas, { still, framing }) starts it and returns a function that stops it and frees its memory.
// In the world: +x is down-right on screen, +z is down-left, +y is up.

const COLORS = {
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

// The same "random" numbers every time, so the island always looks the same
function makeRandom(seed) {
  let value = seed;
  return () => {
    value = (value + 0x6d2b79f5) | 0;
    let mixed = Math.imul(value ^ (value >>> 15), 1 | value);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

function pick(list, random) {
  return list[Math.floor(random() * list.length)];
}

function groundHeight(z) {
  if (z <= -2.5) return HIGH;
  if (z <= 2.5) return MID;
  return LOW;
}

function material(color, options = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.82, flatShading: true, ...options });
}

function withShadow(mesh) {
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

// ---------- Shapes ----------

// A lumpy low-poly ball: a treetop, a rock or a cloud
function lumpyBall(radius, random, lumps = 0.14, detail = 1) {
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
function leafShape(length, width, droop, steps = 6) {
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

function paintTexture(width, height, paint) {
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

function waterTexture(random, repeatX, repeatY, streakWide) {
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

function clipTexture(background, accent) {
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
  if (isRiver(x)) return z >= -6 && z <= 6;   // the river runs right to the edge, so its last waterfall can be seen
  const wobble = Math.sin(x * 1.7 + z * 0.6) * 0.5 + Math.cos(z * 1.9 - x * 0.4) * 0.4;
  return Math.hypot(x, z) <= 7 + wobble * 0.55;
}

function isRiver(x) {
  return x > RIVER_MIN_X && x < RIVER_MAX_X;
}

function buildGround(root, random) {
  const columns = [];
  for (let x = -8; x <= 8; x += 1) {
    for (let z = -8; z <= 8; z += 1) {
      if (isLand(x, z)) columns.push({ x, z });
    }
  }
  // One shape drawn many times: much faster than hundreds of separate boxes
  const boxShape = new RoundedBoxGeometry(1, 1, 1, 2, 0.05);
  const blockMaterial = new THREE.MeshStandardMaterial({ roughness: 0.9, flatShading: false });
  const blocks = withShadow(new THREE.InstancedMesh(boxShape, blockMaterial, columns.length * 3));
  const matrix = new THREE.Matrix4();
  const color = new THREE.Color();
  let count = 0;

  function addBlock(x, z, bottom, top, tint, size = 1.001) {
    matrix.makeScale(size, top - bottom, size);
    matrix.setPosition(x, (top + bottom) / 2, z);
    blocks.setMatrixAt(count, matrix);
    blocks.setColorAt(count, color.set(tint));
    count += 1;
  }

  for (const { x, z } of columns) {
    const depth = SEA_LEVEL - 2;   // every column reaches below the water
    const river = isRiver(x);
    const top = groundHeight(z) - (river ? 0.34 : 0);
    addBlock(x, z, depth, Math.min(0.2, top - 0.9), pick(COLORS.deepRock, random));
    addBlock(x, z, Math.min(0.2, top - 0.9), top - (river ? 0 : 0.42), river ? "#5e5a58" : pick(top - 1 > 1 ? COLORS.rock : COLORS.dirt, random));
    if (!river) addBlock(x, z, top - 0.42, top + (random() - 0.5) * 0.05, pick(COLORS.grass, random), 1.012);
  }
  blocks.count = count;
  blocks.instanceMatrix.needsUpdate = true;
  blocks.instanceColor.needsUpdate = true;
  root.add(blocks);
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
  const RANGE = 18;
  const MAX_DISTANCE = 8;
  const land = [];
  for (let x = -8; x <= 8; x += 1) {
    for (let z = -8; z <= 8; z += 1) {
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
    uFall: { value: new THREE.Vector2(RIVER_X, 6.55) },
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
  for (const [x, z, size] of [[-8.6, 3.1, 0.62], [-7.9, 4.1, 0.34], [8.2, 2.9, 0.54], [6.2, 6.6, 0.48], [7, 6.1, 0.28], [-4.6, 8, 0.42]]) {
    const rockMesh = withShadow(new THREE.Mesh(lumpyBall(size, random, 0.2, 0), material(pick(COLORS.rock, random))));
    rockMesh.scale.y = 0.8;
    rockMesh.position.set(x, SEA_LEVEL + size * 0.2, z);
    root.add(rockMesh);
  }
  const padMaterial = material("#58b84a");
  for (const [x, z, size] of [[-2.8, 8.4, 0.34], [-2.1, 8.9, 0.24], [-3.3, 9, 0.2], [5.3, 7.9, 0.3], [5.9, 8.4, 0.22]]) {
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
  const stretches = [[-6.5, -2.5, HIGH], [-2.5, 2.5, MID], [2.5, 6.5, LOW]];
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
  const falls = [[-2.48, HIGH - 0.08, MID - 0.14], [2.52, MID - 0.08, LOW - 0.14], [6.53, LOW - 0.08, SEA_LEVEL]];
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
  const landings = [[-2.25, MID - 0.05], [2.75, LOW - 0.05], [6.85, SEA_LEVEL + 0.02], [-2.48, HIGH - 0.02], [2.52, MID - 0.02]];
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
  group.position.set(RIVER_X, HIGH, -6.05);
  const wood = material(COLORS.wood);
  const dark = material(COLORS.woodDark);

  for (const x of [-1.72, 1.72]) {
    const post = withShadow(new THREE.Mesh(new THREE.BoxGeometry(0.26, 2.7, 0.26), dark));
    post.position.set(x, 1.3, 0);
    group.add(post);
  }
  const frame = withShadow(new THREE.Mesh(new RoundedBoxGeometry(3.5, 2.12, 0.22, 2, 0.06), wood));
  frame.position.set(0, 1.72, 0);
  group.add(frame);
  const roof = withShadow(new THREE.Mesh(new THREE.BoxGeometry(3.95, 0.16, 0.72), dark));
  roof.position.set(0, 2.92, 0.04);
  roof.rotation.x = 0.18;
  group.add(roof);

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
    [-5.6, HIGH - 0.04], [-2.62, HIGH - 0.04], [-2.38, HIGH - 0.04], [-2.08, (HIGH + MID) / 2], [-1.93, MID + 0.05], [-1.7, MID - 0.04],
    [2.4, MID - 0.04], [2.62, MID - 0.04], [2.92, (MID + LOW) / 2], [3.07, LOW + 0.05], [3.3, LOW - 0.04],
    [6.42, LOW - 0.04], [6.63, LOW - 0.04], [6.93, (LOW + SEA_LEVEL) / 2], [7.08, SEA_LEVEL + 0.04], [7.35, SEA_LEVEL + 0.02], [13, SEA_LEVEL + 0.02],
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
      const fanOut = 1 + Math.max(0, z - 7) * 0.75;   // out at sea, the clips spread apart
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

function buildPlants(root, random) {
  const swaying = [];
  const trunkMaterial = material(COLORS.trunk);
  const leafMaterials = COLORS.leaves.map((color) => material(color));
  const brightMaterials = COLORS.brightLeaves.map((color) => material(color));
  const doubleLeaf = (color) => material(color, { side: THREE.DoubleSide });
  const leafSheets = [...COLORS.leaves, ...COLORS.brightLeaves].map(doubleLeaf);

  function sway(group, amount, speed) {
    swaying.push({ group, amount, speed, phase: random() * 6.28, baseX: group.rotation.x, baseZ: group.rotation.z });
  }

  function place(group, x, z) {
    group.position.set(x, groundHeight(z), z);
    root.add(group);
  }

  function tree(x, z, size = 1) {
    const group = new THREE.Group();
    const height = 1.5 * size;
    const trunk = withShadow(new THREE.Mesh(new THREE.CylinderGeometry(0.12 * size, 0.24 * size, height, 6), trunkMaterial));
    trunk.position.y = height / 2;
    group.add(trunk);
    const crown = new THREE.Group();
    crown.position.y = height;
    const blobs = [[0, 0.42, 0, 0.82], [0.48, 0.14, 0.14, 0.56], [-0.42, 0.2, 0.22, 0.6], [0.04, 0.2, -0.46, 0.56], [0.08, 0.92, 0.02, 0.5]];
    for (const [bx, by, bz, radius] of blobs) {
      const useBright = by > 0.8;
      const blob = withShadow(new THREE.Mesh(lumpyBall(radius * size, random), useBright ? pick(brightMaterials, random) : pick(leafMaterials, random)));
      blob.position.set(bx * size, by * size, bz * size);
      crown.add(blob);
    }
    group.add(crown);
    sway(crown, 0.022, 0.8 + random() * 0.4);
    place(group, x, z);
  }

  function palm(x, z, size = 1) {
    const group = new THREE.Group();
    const steps = 5;
    let lean = 0;
    let height = 0;
    for (let i = 0; i < steps; i += 1) {
      const piece = withShadow(new THREE.Mesh(new THREE.CylinderGeometry(0.1 * size * (1 - i * 0.08), 0.13 * size * (1 - i * 0.08), 0.5 * size, 6), trunkMaterial));
      lean = i * 0.055 * size;
      piece.position.set(lean, height + 0.25 * size, 0);
      piece.rotation.z = -0.1;
      group.add(piece);
      height += 0.47 * size;
    }
    const crown = new THREE.Group();
    crown.position.set(lean + 0.06, height, 0);
    const count = 8;
    for (let i = 0; i < count; i += 1) {
      const frond = withShadow(new THREE.Mesh(leafShape(1.35 * size, 0.46 * size, 0.72 * size), pick(leafSheets, random)));
      frond.rotation.order = "YXZ";
      frond.rotation.y = (i / count) * Math.PI * 2;
      frond.rotation.x = -0.34;
      crown.add(frond);
    }
    group.add(crown);
    sway(crown, 0.05, 1.05 + random() * 0.5);
    place(group, x, z);
  }

  function leafyPlant(x, z, size = 1, bright = false) {
    const group = new THREE.Group();
    const count = 6 + Math.floor(random() * 3);
    for (let i = 0; i < count; i += 1) {
      const holder = new THREE.Group();
      holder.rotation.y = (i / count) * Math.PI * 2 + random() * 0.4;
      const color = bright ? COLORS.brightLeaves[i % 2] : COLORS.leaves[i % 4];
      const leaf = withShadow(new THREE.Mesh(leafShape((0.74 + random() * 0.32) * size, 0.42 * size, 0.42 * size), doubleLeaf(color)));
      leaf.rotation.x = -0.72;
      holder.add(leaf);
      group.add(holder);
      sway(holder, 0.05, 1.3 + random() * 0.8);
    }
    place(group, x, z);
  }

  function rock(x, z, size = 0.4) {
    const mesh = withShadow(new THREE.Mesh(lumpyBall(size, random, 0.2, 0), material(pick(COLORS.rock, random))));
    mesh.scale.y = 0.72;
    mesh.position.set(x, groundHeight(z) + size * 0.32, z);
    root.add(mesh);
  }

  function mushroom(x, z, size = 1) {
    const group = new THREE.Group();
    const stem = withShadow(new THREE.Mesh(new THREE.CylinderGeometry(0.05 * size, 0.07 * size, 0.2 * size, 6), material(COLORS.cream)));
    stem.position.y = 0.1 * size;
    group.add(stem);
    const cap = withShadow(new THREE.Mesh(new THREE.SphereGeometry(0.16 * size, 8, 5, 0, Math.PI * 2, 0, Math.PI / 2), material("#ef5b4a")));
    cap.position.y = 0.18 * size;
    group.add(cap);
    place(group, x, z);
  }

  function flowers(x, z, color) {
    const group = new THREE.Group();
    for (let i = 0; i < 5; i += 1) {
      const bloom = new THREE.Mesh(new THREE.IcosahedronGeometry(0.075, 0), material(color));
      bloom.position.set((random() - 0.5) * 0.65, 0.09 + random() * 0.08, (random() - 0.5) * 0.65);
      group.add(bloom);
    }
    place(group, x, z);
  }

  // Back step
  tree(-3.6, -4.5, 1.3);
  tree(-1.3, -5.2, 1.08);
  tree(-5.1, -2.9, 0.95);
  tree(5.4, -2.8, 0.85);   // low enough not to block the video screen
  palm(3.5, -3.2, 0.92);
  leafyPlant(-1.8, -3.15, 0.95, true);
  leafyPlant(3.3, -5.3, 0.85);
  rock(0, -3.2, 0.34);
  rock(2.95, -2.95, 0.28);
  mushroom(-0.4, -4.2, 1.3);
  flowers(-3, -3.1, "#ff9ec7");

  // Middle step
  tree(-5.5, 0.1, 1.22);
  palm(-3.1, 1.75, 1.15);
  palm(5.6, -0.6, 1.1);
  tree(4.1, -1.7, 0.9);
  leafyPlant(3.6, 1.8, 1.08, true);
  leafyPlant(-0.4, -1.7, 0.9);
  leafyPlant(-4.9, 2.1, 0.9);
  rock(-0.1, 1.8, 0.36);
  rock(3, -0.3, 0.26);
  mushroom(5.2, 2, 1.2);
  mushroom(5.5, 1.6, 0.85);
  flowers(-2.2, -1.5, "#ffd34d");

  // Front step
  palm(-1.9, 5.1, 0.98);
  tree(4.6, 4.1, 0.86);
  leafyPlant(-3.4, 3.8, 1.2);
  leafyPlant(3.4, 5.5, 1.18, true);
  leafyPlant(-0.3, 3.3, 0.72, true);
  rock(0.05, 5.8, 0.3);
  rock(3.3, 3.2, 0.32);
  mushroom(-4.7, 3.2, 1.3);
  flowers(5.3, 3.1, "#ff9ec7");
  flowers(-2.4, 3.15, "#ffd34d");

  return (time) => {
    for (const item of swaying) {
      item.group.rotation.x = item.baseX + Math.sin(time * item.speed + item.phase) * item.amount;
      item.group.rotation.z = item.baseZ + Math.cos(time * item.speed * 0.8 + item.phase) * item.amount;
    }
  };
}

function buildHutAndBridge(root) {
  const wood = material(COLORS.wood);
  const dark = material(COLORS.woodDark);

  // A little hut on stilts
  const hut = new THREE.Group();
  hut.position.set(-2.1, MID, 0);
  for (const [x, z] of [[-0.7, -0.7], [0.7, -0.7], [-0.7, 0.7], [0.7, 0.7]]) {
    const stilt = withShadow(new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.42, 0.14), dark));
    stilt.position.set(x, 0.21, z);
    hut.add(stilt);
  }
  const deck = withShadow(new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.12, 1.8), dark));
  deck.position.y = 0.46;
  hut.add(deck);
  const walls = withShadow(new THREE.Mesh(new THREE.BoxGeometry(1.26, 0.86, 1.26), wood));
  walls.position.y = 0.94;
  hut.add(walls);
  const door = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.58, 0.02), material("#3f2815"));
  door.position.set(0.1, 0.82, 0.64);
  hut.add(door);
  const window_ = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.28, 0.32), new THREE.MeshBasicMaterial({ color: "#ffdf8a", toneMapped: false }));
  window_.position.set(0.64, 1, 0);
  hut.add(window_);
  const roof = withShadow(new THREE.Mesh(new THREE.ConeGeometry(1.32, 0.86, 4), material(COLORS.thatch)));
  roof.position.y = 1.8;
  roof.rotation.y = Math.PI / 4;
  hut.add(roof);
  root.add(hut);

  // A plank bridge over the river
  const bridge = new THREE.Group();
  const span = RIVER_MAX_X - RIVER_MIN_X + 0.7;
  for (let i = 0; i < 9; i += 1) {
    const along = i / 8;
    const plank = withShadow(new THREE.Mesh(new THREE.BoxGeometry(span / 9, 0.08, 0.92), i % 2 ? wood : dark));
    plank.position.set(RIVER_X - span / 2 + along * span, MID + 0.1 + Math.sin(along * Math.PI) * 0.26, 0.3);
    plank.rotation.z = Math.cos(along * Math.PI) * 0.34;
    bridge.add(plank);
    if (i % 2 === 0) {
      for (const z of [-0.14, 0.74]) {
        const post = withShadow(new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.34, 0.07), dark));
        post.position.set(plank.position.x, plank.position.y + 0.18, z);
        bridge.add(post);
      }
    }
  }
  root.add(bridge);
}

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
    return { group, left, right, radius: 8.4 + index * 1.2, height: 7.4 + index * 0.8, speed: 0.13 + index * 0.05, phase: index * 2.2 };
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
  sun.shadow.camera.left = -13;
  sun.shadow.camera.right = 13;
  sun.shadow.camera.top = 13;
  sun.shadow.camera.bottom = -13;
  sun.shadow.bias = -0.0006;
  sun.shadow.normalBias = 0.025;
  scene.add(sun);

  const random = makeRandom(20261105);
  const root = new THREE.Group();
  scene.add(root);
  buildGround(root, random);
  buildHutAndBridge(root);
  const updates = [
    buildWater(root, random),
    buildScreen(root),
    buildClipCards(root, random),
    buildPlants(root, random),
    buildCrystals(root, random),
    buildVines(root, random),
    buildBirds(root),
    buildClouds(scene, random),
    buildSea(root, random, renderer.getPixelRatio()),
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
    const halfHeight = backdrop ? Math.max(8, 10 / aspect) : wide ? 9 : Math.max(11, 12.5 / aspect);
    const halfWidth = halfHeight * aspect;
    let shiftX = wide ? halfWidth * 0.42 : 0;
    let shiftY = wide ? 0.3 : -halfHeight * 0.36;   // narrow screens: the island sits below the words
    if (backdrop) {   // low on the screen, behind the page's content
      shiftX = wide ? halfWidth * 0.2 : 0;
      shiftY = -halfHeight * 0.62;
    }
    camera.left = -halfWidth - shiftX;
    camera.right = halfWidth - shiftX;
    camera.top = halfHeight - shiftY;
    camera.bottom = -halfHeight - shiftY;
    camera.updateProjectionMatrix();
    draw();
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
    mouse.smoothX += (mouse.x - mouse.smoothX) * 0.04;
    root.rotation.y = mouse.smoothX * 0.055;
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
    frame = requestAnimationFrame(loop);
  }

  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("pointermove", handleMouse);
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
