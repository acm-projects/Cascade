import * as THREE from "three";
import { COLORS, instanced, leafShape, lumpyBall, makeRandom, material, pick, waterTexture } from "./islandScene";

// The 3D lake behind the AI Studio canvas: the pool at the foot of a waterfall, deep in the rainforest.
// A mossy cliff at the back with the waterfall pouring in, pixel water with ripples and foam, and jungle banks
// with trees, palms, ferns, reeds and rocks. The cards, lily pads and vines (the React Flow canvas) float on top.
// Panning or zooming the canvas slides the view along a little behind them.
//
// It animates at a gentle 30 frames a second (enough for water) to stay light on a work page.
// createLakeScene(canvas, { still }) starts it and returns a function that stops it and frees its memory.
// In the world: +x is right, +z is toward you, +y is up. The water is at y = 0.

// The lake: x between -LAKE_X and LAKE_X, z between LAKE_BACK (the waterfall cliff) and LAKE_FRONT, with wobbly shores
const LAKE_X = 16;
const LAKE_BACK = -14.5;
const LAKE_FRONT = 10;
const CLIFF = 7;          // how tall the waterfall cliff is
const FALL_HALF = 2.5;    // half the waterfall's width
const SPLASH = new THREE.Vector2(0, LAKE_BACK + 0.6);

function shoreWobble(x, z) {
  return Math.sin(x * 0.35 + 1) * 0.8 + Math.cos(z * 0.4) * 0.7;
}

// How far a spot is inside the lake (negative = on land). The water shader uses the same sums.
function inLake(x, z) {
  const wobble = shoreWobble(x, z) * 0.6;
  const back = z - LAKE_BACK;   // the cliff is straight, no wobble
  return Math.min(Math.min(LAKE_X - Math.abs(x), LAKE_FRONT - z) + wobble, back);
}

function bankHeight(x, z) {
  if (z <= LAKE_BACK) return CLIFF;   // the waterfall cliff along the back
  const away = -inLake(x, z);
  return 0.35 + Math.min(1.6, away * 0.12) + Math.sin(x * 0.7 + z * 0.4) * 0.12;
}

// ---------- The water ----------

const LAKE_VERTEX = `
  varying vec3 vPlace;
  void main() {
    vPlace = (modelMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * viewMatrix * vec4(vPlace, 1.0);
  }
`;

const LAKE_FRAGMENT = `
  uniform float uTime;
  uniform float uPixel;
  uniform vec3 uDeep;
  uniform vec3 uShallow;
  uniform vec3 uFoam;
  varying vec3 vPlace;

  float hash(vec2 value) { return fract(sin(dot(value, vec2(127.1, 311.7))) * 43758.5453); }

  void main() {
    // Every screen pixel inside one big square uses that square's spot on the water, so it draws as chunky pixels
    vec2 grid = gl_FragCoord.xy / uPixel;
    vec2 cell = floor(grid);
    vec2 p = vPlace.xz - dFdx(vPlace.xz) * fract(grid.x) * uPixel - dFdy(vPlace.xz) * fract(grid.y) * uPixel;
    float t = uTime;

    float wobble = (sin(p.x * 0.35 + 1.0) * 0.8 + cos(p.y * 0.4) * 0.7) * 0.6;
    float shore = min(min(${LAKE_X.toFixed(1)} - abs(p.x), ${LAKE_FRONT.toFixed(1)} - p.y) + wobble, p.y - (${LAKE_BACK.toFixed(1)}));

    // Shallow green-turquoise near the banks, deeper teal in the middle, in color steps like pixel art
    vec3 color = mix(uShallow, uDeep, floor(smoothstep(0.0, 6.0, shore) * 8.0 + 0.5) / 8.0);

    // Ripple lines drifting across the surface
    float a = sin(p.x * 0.9 + t * 0.35 + sin(p.y * 0.7 + t * 0.25) * 1.6);
    float b = sin(p.y * 1.2 - t * 0.3 + sin(p.x * 0.6 - t * 0.2) * 1.5);
    float ripple = a + b;
    color = mix(color, uFoam, (step(abs(ripple - 0.9), 0.07) + step(abs(ripple + 0.7), 0.05) * 0.6) * 0.18);

    // Where the waterfall lands: churning foam, then rings spreading out across the lake
    vec2 fromFall = (p - vec2(${SPLASH.x.toFixed(1)}, ${SPLASH.y.toFixed(1)})) * vec2(0.55, 1.0);
    float fall = length(fromFall);
    float splash = step(fall + sin(atan(fromFall.y, fromFall.x) * 7.0 + t * 3.0) * 0.18, 1.6);
    float rings = step(0.5, smoothstep(0.25, 0.9, sin(fall * 2.6 - t * 2.4)) * smoothstep(9.0, 1.5, fall));
    color = mix(color, uFoam, rings * 0.4);
    color = mix(color, uFoam, splash * 0.9);

    // White foam along the shore
    float edge = 0.25 + sin(p.x * 2.1 + t) * 0.08 + sin(p.y * 1.7 - t * 1.2) * 0.08;
    color = mix(color, uFoam, step(shore, edge));

    // Little dashes of pixels gliding across, twinkling (the same as the Landing sea)
    if (mod(cell.y, 3.0) < 1.0) {
      float rowSeed = hash(vec2(cell.y, 4.0));
      float along = cell.x + floor(t * (0.6 + rowSeed * 1.1)) + floor(rowSeed * 97.0);
      float dash = floor(along / 11.0);
      float dashSeed = hash(vec2(dash, cell.y));
      float twinkle = step(0.3, sin(t * (0.5 + dashSeed) + dashSeed * 40.0) * 0.5 + 0.5);
      color = mix(color, uFoam, step(0.88, dashSeed) * step(mod(along, 11.0), 2.0 + floor(dashSeed * 3.0)) * twinkle * 0.5);
    }

    gl_FragColor = vec4(color, 1.0);
    #include <colorspace_fragment>
  }
`;

function buildWater(scene, pixelRatio) {
  const uniforms = {
    uTime: { value: 0 },
    uPixel: { value: 5 * pixelRatio },
    uDeep: { value: new THREE.Color("#1d8fb0") },
    uShallow: { value: new THREE.Color("#4fd0c4") },
    uFoam: { value: new THREE.Color("#f3fffd") },
  };
  const geometry = new THREE.PlaneGeometry(200, 160);
  geometry.rotateX(-Math.PI / 2);
  scene.add(new THREE.Mesh(geometry, new THREE.ShaderMaterial({ uniforms, vertexShader: LAKE_VERTEX, fragmentShader: LAKE_FRAGMENT })));
  return uniforms;
}

// ---------- The banks and the waterfall cliff ----------

function buildBanks(scene, random) {
  const cells = [];
  for (let x = -58; x <= 58; x += 1) {
    for (let z = -32; z <= 44; z += 1) {
      if (inLake(x, z) < -0.2 || z <= LAKE_BACK) cells.push({ x, z });
    }
  }
  const box = new THREE.BoxGeometry(1, 1, 1);
  const blocks = new THREE.InstancedMesh(box, new THREE.MeshStandardMaterial({ roughness: 0.9, flatShading: true }), cells.length * 2);
  blocks.castShadow = true;
  blocks.receiveShadow = true;
  const matrix = new THREE.Matrix4();
  const color = new THREE.Color();
  let count = 0;
  const add = (x, z, bottom, top, tint) => {
    matrix.makeScale(1.001, top - bottom, 1.001);
    matrix.setPosition(x, (top + bottom) / 2, z);
    blocks.setMatrixAt(count, matrix);
    blocks.setColorAt(count, color.set(tint));
    count += 1;
  };
  for (const { x, z } of cells) {
    const inChannel = z <= LAKE_BACK && Math.abs(x) <= FALL_HALF - 0.5;   // the river on top of the cliff, feeding the waterfall
    const top = bankHeight(x, z) - (inChannel ? 0.35 : 0);
    add(x, z, -2, top - 0.35, top > 3 ? pick(COLORS.rock, random) : pick(COLORS.dirt, random));
    if (!inChannel) add(x, z, top - 0.35, top, pick(COLORS.grass, random));
  }
  blocks.count = count;
  blocks.instanceMatrix.needsUpdate = true;
  blocks.instanceColor.needsUpdate = true;
  scene.add(blocks);

  // Moss and vines hanging down the cliff face
  const moss = [];
  for (let x = -24; x <= 24; x += 1) {
    if (Math.abs(x) < FALL_HALF + 0.3) continue;
    for (let i = 0; i < 3; i += 1) {
      const length = 0.4 + random() * 2.2;
      moss.push({ x: x + (random() - 0.5) * 0.8, y: CLIFF - 0.35 - length / 2 - random() * 1.5, z: LAKE_BACK + 0.04, sx: 0.12 + random() * 0.3, sy: length, sz: 0.06, color: pick(["#2f8a3a", "#3f9a36", "#4caa3a"], random) });
    }
  }
  instanced(scene, new THREE.BoxGeometry(1, 1, 1), material("#ffffff"), moss);
}

function buildWaterfall(scene, random) {
  const textures = [];
  const waterMaterial = (map) => new THREE.MeshStandardMaterial({ map, roughness: 0.3, emissive: "#0b6f86", emissiveIntensity: 0.3 });

  // The river on top of the cliff
  const riverTexture = waterTexture(random, 1, 4, false);
  textures.push({ texture: riverTexture, speed: 0.35 });
  const river = new THREE.Mesh(new THREE.PlaneGeometry(FALL_HALF * 2 - 1, 18), waterMaterial(riverTexture));
  river.rotation.x = -Math.PI / 2;
  river.position.set(0, CLIFF - 0.12, LAKE_BACK - 9);
  scene.add(river);

  // The waterfall itself, down the front of the cliff
  const fallTexture = waterTexture(random, 1.5, 2.5, false);
  textures.push({ texture: fallTexture, speed: 1.1 });
  const fall = new THREE.Mesh(new THREE.PlaneGeometry(FALL_HALF * 2, CLIFF), waterMaterial(fallTexture));
  fall.position.set(0, CLIFF / 2 - 0.05, LAKE_BACK + 0.06);
  scene.add(fall);

  // Foam where it lands, and spray drifting up
  const foamMaterial = new THREE.MeshStandardMaterial({ color: COLORS.foam, roughness: 0.7, flatShading: true });
  const puffs = [];
  for (let i = 0; i < 22; i += 1) {
    const size = 0.25 + random() * 0.4;
    const puff = new THREE.Mesh(lumpyBall(size, random, 0.1, 0), foamMaterial);
    const baseY = 0.05 + random() * 0.2;
    puff.position.set((random() - 0.5) * FALL_HALF * 2.4, baseY, LAKE_BACK + 0.4 + random() * 1.2);
    scene.add(puff);
    puffs.push({ puff, baseY, phase: random() * 6, speed: 2 + random() * 2 });
  }
  const sprayMaterial = new THREE.MeshStandardMaterial({ color: "#ffffff", transparent: true, opacity: 0.35, roughness: 1, depthWrite: false });
  const spray = [];
  for (let i = 0; i < 10; i += 1) {
    const mist = new THREE.Mesh(new THREE.SphereGeometry(0.9 + random() * 0.7, 10, 8), sprayMaterial);
    scene.add(mist);
    spray.push({ mist, x: (random() - 0.5) * 6, start: random(), speed: 0.12 + random() * 0.08 });
  }

  return (time, delta) => {
    for (const { texture, speed } of textures) texture.offset.y = (texture.offset.y + delta * speed) % 1;
    for (const item of puffs) {
      const wave = Math.sin(time * item.speed + item.phase);
      item.puff.scale.setScalar(1 + wave * 0.25);
      item.puff.position.y = item.baseY + (wave + 1) * 0.08;
    }
    for (const item of spray) {
      const rise = (item.start + time * item.speed) % 1;
      item.mist.position.set(item.x + Math.sin(time * 0.5 + item.start * 6) * 0.6, rise * 4, LAKE_BACK + 1 + rise * 1.5);
      item.mist.scale.setScalar(0.6 + rise * 0.8);
    }
  };
}

// ---------- Rainforest plants, rocks and reeds ----------

function buildPlants(scene, random) {
  const swaying = [];
  const leafMaterials = COLORS.leaves.map((color) => material(color));
  const brightMaterials = COLORS.brightLeaves.map((color) => material(color));
  const leafSheets = [...COLORS.leaves, ...COLORS.brightLeaves].map((color) => material(color, { side: THREE.DoubleSide }));
  const trunkMaterial = material(COLORS.trunk);

  function tree(x, z, size) {
    const group = new THREE.Group();
    const height = 1.6 * size;
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.13 * size, 0.26 * size, height, 6), trunkMaterial);
    trunk.position.y = height / 2;
    trunk.castShadow = true;
    group.add(trunk);
    const crown = new THREE.Group();
    crown.position.y = height;
    for (const [bx, by, bz, radius] of [[0, 0.45, 0, 0.9], [0.5, 0.15, 0.15, 0.6], [-0.45, 0.2, 0.22, 0.65], [0.05, 0.2, -0.5, 0.6], [0.08, 1, 0.02, 0.55]]) {
      const blob = new THREE.Mesh(lumpyBall(radius * size, random), by > 0.8 ? pick(brightMaterials, random) : pick(leafMaterials, random));
      blob.position.set(bx * size, by * size, bz * size);
      blob.castShadow = true;
      crown.add(blob);
    }
    group.add(crown);
    group.position.set(x, bankHeight(Math.round(x), Math.round(z)), z);
    scene.add(group);
    swaying.push({ group: crown, amount: 0.02, speed: 0.7 + random() * 0.4, phase: random() * 6 });
  }

  function palm(x, z, size) {
    const group = new THREE.Group();
    let height = 0;
    let lean = 0;
    for (let i = 0; i < 5; i += 1) {
      const piece = new THREE.Mesh(new THREE.CylinderGeometry(0.1 * size, 0.13 * size, 0.55 * size, 6), trunkMaterial);
      lean = i * 0.06 * size;
      piece.position.set(lean, height + 0.27 * size, 0);
      piece.rotation.z = -0.1;
      piece.castShadow = true;
      group.add(piece);
      height += 0.52 * size;
    }
    const crown = new THREE.Group();
    crown.position.set(lean + 0.06, height, 0);
    for (let i = 0; i < 8; i += 1) {
      const frond = new THREE.Mesh(leafShape(1.5 * size, 0.5 * size, 0.8 * size), pick(leafSheets, random));
      frond.rotation.order = "YXZ";
      frond.rotation.y = (i / 8) * Math.PI * 2;
      frond.rotation.x = -0.34;
      frond.castShadow = true;
      crown.add(frond);
    }
    group.add(crown);
    group.position.set(x, bankHeight(Math.round(x), Math.round(z)), z);
    group.rotation.y = random() * 6;
    scene.add(group);
    swaying.push({ group: crown, amount: 0.05, speed: 1 + random() * 0.5, phase: random() * 6 });
  }

  function fern(x, z, size) {
    const group = new THREE.Group();
    for (let i = 0; i < 7; i += 1) {
      const holder = new THREE.Group();
      holder.rotation.y = (i / 7) * Math.PI * 2 + random() * 0.4;
      const leaf = new THREE.Mesh(leafShape((0.8 + random() * 0.35) * size, 0.45 * size, 0.45 * size), pick(leafSheets, random));
      leaf.rotation.x = -0.7;
      holder.add(leaf);
      group.add(holder);
    }
    group.position.set(x, bankHeight(Math.round(x), Math.round(z)), z);
    scene.add(group);
    swaying.push({ group, amount: 0.04, speed: 1.2 + random() * 0.6, phase: random() * 6 });
  }

  // Scatter plants over the banks (not right at the water's edge), and along the top of the cliff
  for (let i = 0; i < 260; i += 1) {
    const x = (random() - 0.5) * 112;
    const z = -30 + random() * 72;
    const onCliff = z <= LAKE_BACK - 0.8 && Math.abs(x) > FALL_HALF + 0.8;
    const onBank = z > LAKE_BACK && inLake(x, z) < -1.4;
    if (!onCliff && !onBank) continue;
    const roll = random();
    if (roll < 0.42) tree(x, z, 0.9 + random() * 0.6);
    else if (roll < 0.66) palm(x, z, 0.9 + random() * 0.4);
    else fern(x, z, 0.9 + random() * 0.5);
  }

  // Rocks along the shore and in the shallows, reeds, and lily pads floating on the lake
  for (let i = 0; i < 70; i += 1) {
    const x = (random() - 0.5) * 2 * (LAKE_X + 3);
    const z = LAKE_BACK + random() * (LAKE_FRONT - LAKE_BACK + 3);
    const depth = inLake(x, z);
    if (depth < -0.6 || depth > 1.3) continue;   // only right around the shoreline
    const size = 0.35 + random() * 0.6;
    const rock = new THREE.Mesh(lumpyBall(size, random, 0.22, 0), material(pick(COLORS.rock, random)));
    rock.scale.y = 0.7;
    rock.position.set(x, size * 0.15, z);
    rock.castShadow = true;
    scene.add(rock);
  }
  const reeds = [];
  for (let i = 0; i < 90; i += 1) {
    const x = (random() - 0.5) * 2 * (LAKE_X + 2);
    const z = LAKE_BACK + 2 + random() * (LAKE_FRONT - LAKE_BACK);
    const depth = inLake(x, z);
    if (depth < 0.1 || depth > 1.2) continue;
    for (let r = 0; r < 4; r += 1) {
      reeds.push({ x: x + (random() - 0.5) * 0.3, y: 0.45, z: z + (random() - 0.5) * 0.3, rx: (random() - 0.5) * 0.3, rz: (random() - 0.5) * 0.3, sy: 0.7 + random() * 0.6, color: pick(["#5e9a3a", "#76ad44", "#4d8a34"], random) });
    }
  }
  instanced(scene, new THREE.CylinderGeometry(0.025, 0.04, 1, 4), material("#ffffff"), reeds);
  const padMaterial = material("#5fbf4a");
  for (let i = 0; i < 26; i += 1) {
    const x = (random() - 0.5) * 2 * LAKE_X;
    const z = LAKE_BACK + 3 + random() * (LAKE_FRONT - LAKE_BACK - 2);
    if (inLake(x, z) < 1 || Math.hypot(x - SPLASH.x, z - SPLASH.y) < 4) continue;
    const size = 0.3 + random() * 0.35;
    const pad = new THREE.Mesh(new THREE.CylinderGeometry(size, size, 0.04, 10, 1, false, 0.3, Math.PI * 2 - 0.6), padMaterial);
    pad.position.set(x, 0.03, z);
    pad.rotation.y = random() * 6;
    scene.add(pad);
    if (random() < 0.3) {   // a few have a pink flower
      const flower = new THREE.Mesh(new THREE.IcosahedronGeometry(0.12, 0), material("#ff9ec7"));
      flower.position.set(x, 0.12, z);
      scene.add(flower);
    }
  }

  return (time) => {
    for (const item of swaying) {
      item.group.rotation.x = Math.sin(time * item.speed + item.phase) * item.amount;
      item.group.rotation.z = Math.cos(time * item.speed * 0.8 + item.phase) * item.amount;
    }
  };
}

// ---------- Putting it together ----------

export function createLakeScene(canvas, { still = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#2fa36f");
  scene.fog = new THREE.Fog("#7fc9a5", 50, 95);   // the far forest fades into a green haze
  const camera = new THREE.PerspectiveCamera(35, 1, 0.5, 220);

  scene.add(new THREE.HemisphereLight("#e6fbff", "#47703a", 1.8));
  const sun = new THREE.DirectionalLight("#fff3d6", 2.6);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  for (const side of ["left", "bottom"]) sun.shadow.camera[side] = -40;
  for (const side of ["right", "top"]) sun.shadow.camera[side] = 40;
  sun.shadow.camera.far = 120;
  sun.shadow.bias = -0.0008;
  scene.add(sun);
  scene.add(sun.target);

  const random = makeRandom(20261109);
  const water = buildWater(scene, renderer.getPixelRatio());
  buildBanks(scene, random);
  const updates = [buildWaterfall(scene, random), buildPlants(scene, random)];

  // Where the camera looks. Panning the canvas slides this a little, so the lake feels further away than the cards.
  const START_Z = -5;   // start aimed a little back, so the waterfall is in view
  const aim = { x: 0, z: START_Z, zoom: 1 };
  const shown = { ...aim };
  const UNITS_PER_PIXEL = 0.012;
  function handleCanvasMove(event) {
    const { x = 0, y = 0, zoom = 1 } = event.detail ?? {};
    aim.x = -x * UNITS_PER_PIXEL;
    aim.z = START_Z - y * UNITS_PER_PIXEL;
    aim.zoom = zoom;
  }

  function place() {
    const distance = 50 / Math.pow(shown.zoom, 0.35);
    camera.position.set(shown.x, distance * 0.7, shown.z + distance * 0.72);
    camera.lookAt(shown.x, 0, shown.z);
    sun.position.set(shown.x - 12, 30, shown.z + 20);   // in front, so the waterfall cliff is lit
    sun.target.position.set(shown.x, 0, shown.z);
  }

  function fit() {
    const parent = canvas.parentElement;
    const width = parent.clientWidth;
    const height = parent.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    draw();
  }

  let frame = 0;
  let timer = 0;
  let last = performance.now();
  const startTime = performance.now();
  function draw() {
    const now = performance.now();
    const delta = Math.min(0.1, (now - last) / 1000);
    last = now;
    const time = still ? 7 : (now - startTime) / 1000 + 7;
    water.uTime.value = time;
    for (const update of updates) update(time, still ? 0 : delta);
    const ease = still ? 1 : 0.2;
    shown.x += (aim.x - shown.x) * ease;
    shown.z += (aim.z - shown.z) * ease;
    shown.zoom += (aim.zoom - shown.zoom) * ease;
    place();
    renderer.render(scene, camera);
  }
  // About 30 frames a second: smooth enough for water, lighter than full speed. Pauses in background tabs.
  function loop() {
    draw();
    timer = setTimeout(() => { frame = requestAnimationFrame(loop); }, 1000 / 30 - 4);
  }

  const observer = new ResizeObserver(fit);
  observer.observe(canvas.parentElement);
  fit();
  window.addEventListener("cascade:canvas-move", handleCanvasMove);
  if (still) {
    window.addEventListener("cascade:canvas-move", draw);
  } else {
    frame = requestAnimationFrame(loop);
  }

  return () => {
    cancelAnimationFrame(frame);
    clearTimeout(timer);
    window.removeEventListener("cascade:canvas-move", handleCanvasMove);
    window.removeEventListener("cascade:canvas-move", draw);
    observer.disconnect();
    const seen = new Set();
    const free = (thing) => { if (thing && !seen.has(thing)) { seen.add(thing); thing.dispose?.(); } };
    scene.traverse((object) => {
      free(object.geometry);
      for (const item of [object.material].flat()) {
        if (!item) continue;
        free(item.map);
        free(item);
      }
    });
    renderer.dispose();
    renderer.forceContextLoss();
  };
}
