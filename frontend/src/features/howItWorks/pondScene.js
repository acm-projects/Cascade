import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";

// The 3D pond on the "How it works" page: a frog leaps across four lily pads, one per stage of Cascade.
// The pond (banks, cliff, plants, the pads and their lotus flowers) is made in Blender: frontend/blender/pond.py.
// The frog is made in Blender too: frontend/blender/frog.py, with an "Idle" loop and a "Leap" clip.
// Drawn here, because they move: the water, the waterfall, ripples, dragonflies, and the frog's path through the air.
//
// createPondScene(canvas, { still, labels, onStage }) starts it. It returns
//   { goTo(stage), stop() }
//   labels  - four elements (the stage tags); each frame they're moved to sit next to their lily pad
//   onStage - called with the stage number (1 to 4) each time the frog lands on a pad
// In the world: +x is right, +y is up, +z comes toward you. The water's surface is at y = 0.

const POND_URL = "/models/pond.glb";
const FROG_URL = "/models/frog.glb";
const STAGES = 4;
const LEAP_SECONDS = 0.8;   // the length of the frog's "Leap" clip
// The waterfall pours through a notch in the back cliff (the same numbers as pond.py)
const FALL = { x: -0.5, width: 2, top: 2.7, front: -7.45, back: -17 };

let modelsPromise = null;
function loadModels() {
  if (!modelsPromise) {
    const draco = new DRACOLoader().setDecoderPath("/draco/");   // the pond is Draco-compressed
    const loader = new GLTFLoader().setDRACOLoader(draco);
    modelsPromise = Promise.all([loader.loadAsync(POND_URL), loader.loadAsync(FROG_URL)]).finally(() => draco.dispose());
    modelsPromise.catch(() => { modelsPromise = null; });   // let a later visit try again
  }
  return modelsPromise;
}

// ---------- The water: chunky pixels of turquoise, with sparkles and ripple rings ----------

const WATER_VERTEX = `
  varying vec2 vWorld;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vWorld = world.xz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

const WATER_FRAGMENT = `
  uniform float uTime;
  uniform vec4 uRipples[4];   // x, z, the time it started, strength
  uniform vec3 uPads[4];      // x, z, size
  varying vec2 vWorld;

  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
  }

  void main() {
    vec2 cell = floor(vWorld / 0.16) * 0.16 + 0.08;   // chunky pixels, like the Landing sea
    float t = uTime;

    // Deeper in the middle and under the cliff, lighter in the shallows by the banks
    float oval = length(cell / vec2(10.4, 7.54));   // the pond's size in pond.py
    vec3 deep = vec3(0.07, 0.47, 0.58);
    vec3 shallow = vec3(0.34, 0.8, 0.8);
    vec3 color = mix(deep, shallow, smoothstep(0.55, 1.0, oval));
    color = mix(color, vec3(0.05, 0.36, 0.48), smoothstep(-4.0, -7.5, cell.y) * 0.6);

    // Slow, wobbling light bands
    float bands = noise(vec2(cell.x * 0.6 + t * 0.25, cell.y * 1.4 - t * 0.15)) * noise(vec2(cell.x * 1.3 - t * 0.2, cell.y * 0.7));
    color += vec3(0.25, 0.35, 0.3) * smoothstep(0.32, 0.6, bands) * 0.5;

    // Sparkles that flick on and off
    float sparkle = step(0.985, hash(floor(cell * 6.25) + floor(t * 1.5)));
    color = mix(color, vec3(0.95, 1.0, 1.0), sparkle * 0.7);

    // A soft lighter ring of still water around each pad
    for (int i = 0; i < 4; i++) {
      float d = length(cell - uPads[i].xy) - uPads[i].z;
      color = mix(color, vec3(0.55, 0.9, 0.88), smoothstep(0.35, 0.0, d) * step(0.0, d) * 0.35);
    }

    // Ripples: rings spreading out from where the frog lands (and where the waterfall hits)
    for (int i = 0; i < 4; i++) {
      float age = t - uRipples[i].z;
      if (age < 0.0 || age > 2.2) continue;
      float d = length(cell - uRipples[i].xy);
      for (int ring = 0; ring < 2; ring++) {
        float radius = age * 1.6 - float(ring) * 0.45;
        float line = smoothstep(0.14, 0.0, abs(d - radius));
        color = mix(color, vec3(0.92, 1.0, 1.0), line * (1.0 - age / 2.2) * uRipples[i].w * step(0.0, radius));
      }
    }

    color = floor(color * 20.0 + 0.5) / 20.0;   // a limited palette, like pixel art
    gl_FragColor = vec4(color, 1.0);   // already screen colors: no color conversion
  }
`;

function buildWater(scene) {
  const uniforms = {
    uTime: { value: 0 },
    uRipples: { value: Array.from({ length: 4 }, () => new THREE.Vector4(0, 0, -10, 0)) },
    uPads: { value: Array.from({ length: 4 }, () => new THREE.Vector3(0, 0, 0)) },
  };
  const water = new THREE.Mesh(new THREE.PlaneGeometry(52, 40), new THREE.ShaderMaterial({ uniforms, vertexShader: WATER_VERTEX, fragmentShader: WATER_FRAGMENT }));
  water.rotation.x = -Math.PI / 2;
  water.position.y = -0.02;
  scene.add(water);
  let next = 0;
  return {
    uniforms,
    ripple(x, z, time, strength = 1) {
      uniforms.uRipples.value[next].set(x, z, time, strength);
      next = (next + 1) % 4;
    },
  };
}

// ---------- The waterfall: a flowing strip on top of the notch, then a sheet down the cliff ----------

function flowTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 32;
  canvas.height = 64;
  const context = canvas.getContext("2d");
  context.fillStyle = "#57c9dd";
  context.fillRect(0, 0, 32, 64);
  const streaks = ["#8fe3ee", "#c9f5fa", "#3fb3cc", "#ffffff"];
  for (let i = 0; i < 46; i += 1) {
    context.fillStyle = streaks[i % streaks.length];
    context.fillRect(Math.floor(Math.random() * 8) * 4, Math.floor(Math.random() * 16) * 4, 4, 4 + Math.floor(Math.random() * 3) * 4);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function buildWaterfall(scene) {
  const sheetTexture = flowTexture();
  sheetTexture.repeat.set(2, 2.2);
  const sheet = new THREE.Mesh(new THREE.PlaneGeometry(FALL.width, FALL.top + 0.1), new THREE.MeshBasicMaterial({ map: sheetTexture, transparent: true, opacity: 0.94 }));
  sheet.position.set(FALL.x, (FALL.top + 0.1) / 2 - 0.05, FALL.front);
  scene.add(sheet);

  const streamTexture = flowTexture();
  streamTexture.repeat.set(2, 6);
  const streamLength = FALL.front - FALL.back;
  const stream = new THREE.Mesh(new THREE.PlaneGeometry(FALL.width, streamLength), new THREE.MeshBasicMaterial({ map: streamTexture }));
  stream.rotation.x = -Math.PI / 2;
  stream.position.set(FALL.x, FALL.top + 0.02, (FALL.front + FALL.back) / 2);
  scene.add(stream);

  // Foam where it lands: white lumps that bob and swell
  const foamMaterial = new THREE.MeshStandardMaterial({ color: "#f3fffd", roughness: 0.9, flatShading: true });
  const foam = Array.from({ length: 7 }, (_, i) => {
    const lump = new THREE.Mesh(new THREE.IcosahedronGeometry(0.22 + (i % 3) * 0.06, 0), foamMaterial);
    lump.position.set(FALL.x - FALL.width / 2 + 0.15 + i * 0.28, 0.05, FALL.front + 0.25 + (i % 2) * 0.2);
    scene.add(lump);
    return { lump, phase: i * 1.7 };
  });

  return (time) => {
    sheetTexture.offset.y = (time * 1.6) % 1;
    streamTexture.offset.y = (time * 0.9) % 1;
    for (const { lump, phase } of foam) {
      const swell = 0.85 + Math.sin(time * 4 + phase) * 0.2;
      lump.scale.set(swell, swell * 0.7, swell);
      lump.position.y = 0.03 + Math.sin(time * 3 + phase) * 0.04;
    }
  };
}

// ---------- Dragonflies zipping over the water ----------

function buildDragonflies(scene) {
  const wing = new THREE.PlaneGeometry(0.28, 0.07);
  const flies = [["#4fd1e8", 0], ["#ff9e5e", 2.4]].map(([color, phase]) => {
    const group = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 0.36), new THREE.MeshStandardMaterial({ color, flatShading: true }));
    group.add(body);
    const wingMaterial = new THREE.MeshBasicMaterial({ color: "#e9fbff", transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false });
    const wings = [-1, 1].map((side) => {
      const piece = new THREE.Mesh(wing, wingMaterial);
      piece.rotation.x = -Math.PI / 2;
      piece.position.set(side * 0.15, 0.03, -0.04);
      group.add(piece);
      return piece;
    });
    scene.add(group);
    return { group, wings, phase };
  });
  return (time) => {
    for (const fly of flies) {
      const t = time * 0.35 + fly.phase;
      // Darting: mostly still, then a quick hop to a new spot
      const hop = t + Math.sin(t * 3) * 0.25;
      const x = Math.sin(hop * 1.1) * 7.2;
      const z = Math.sin(hop * 0.8 + 1) * 4.2;
      const previous = fly.group.position.clone();
      fly.group.position.set(x, 1.1 + Math.sin(t * 4) * 0.15, z);
      const dx = x - previous.x;
      const dz = z - previous.z;
      if (Math.abs(dx) + Math.abs(dz) > 0.0005) fly.group.rotation.y = Math.atan2(dx, dz);
      const flap = Math.sin(time * 60) * 0.5;
      fly.wings[0].rotation.z = flap;
      fly.wings[1].rotation.z = -flap;
    }
  };
}

// ---------- The scene ----------

export function createPondScene(canvas, { still = false, labels = [], onStage = () => {} } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#7cc6d8");
  scene.fog = new THREE.Fog("#7cc6d8", 30, 52);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  const lookAt = new THREE.Vector3(0, 0, -0.6);   // the same camera as pond.py's preview
  const CAMERA_HOME = new THREE.Vector3(0, 15, 14);
  let distance = 1;   // how far back the camera steps (narrow screens step back further)

  scene.add(new THREE.HemisphereLight("#fff8e6", "#4f7a4a", 1.6));
  const sun = new THREE.DirectionalLight("#fff1d6", 2.3);
  sun.position.set(-7, 16, 9);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  for (const side of ["left", "bottom"]) sun.shadow.camera[side] = -16;
  for (const side of ["right", "top"]) sun.shadow.camera[side] = 16;
  sun.shadow.camera.far = 50;
  sun.shadow.bias = -0.0008;
  scene.add(sun);

  const water = buildWater(scene);
  const updates = [buildWaterfall(scene), buildDragonflies(scene)];

  // Filled in once the Blender models arrive
  const pads = [];       // { object, flower, x, z, size, dip, open }
  const swaying = [];
  let frog = null;       // { object, mixer, idle, leap }
  let current = 0;       // the pad the frog is on (0 to 3)
  let leap = null;       // the leap in progress: { from, to, start }
  const queue = [];      // pads still to leap to, one hop at a time
  let now = 0;

  function padTop(index) {
    const pad = pads[index];
    return new THREE.Vector3(pad.x, pad.object.position.y + 0.06, pad.z);
  }

  // Where the frog sits on a pad: a little off the middle, away from the lotus
  function seat(index) {
    const top = padTop(index);
    const pad = pads[index];
    top.x -= pad.flowerOffset.x * 0.55;
    top.z -= pad.flowerOffset.z * 0.55;
    return top;
  }

  function land(index) {
    const pad = pads[index];
    pad.dip = 1;
    pad.open = 1;
    water.ripple(pad.x, pad.z, now, 1);
    current = index;
    onStage(index + 1);
  }

  function startLeap(to) {
    leap = { from: seat(current), to, start: now, turnFrom: frog.object.rotation.y };
    const action = frog.leap;
    action.reset();
    action.play();
    water.ripple(pads[current].x, pads[current].z, now + 0.25, 0.6);
  }

  function goTo(stage) {
    const target = Math.max(0, Math.min(STAGES - 1, stage - 1));
    if (!frog || still) {
      current = target;
      if (pads.length) {
        pads.forEach((pad, i) => { pad.open = i === target ? 1 : pad.open; });
        if (frog) frog.object.position.copy(seat(target));
      }
      onStage(target + 1);
      draw();
      return;
    }
    // Hop pad by pad toward the target (forwards or backwards)
    queue.length = 0;
    const from = leap ? leap.to : current;
    const step = target > from ? 1 : -1;
    for (let i = from + step; step > 0 ? i <= target : i >= target; i += step) queue.push(i);
    if (!leap && queue.length) startLeap(queue.shift());
  }

  loadModels().then(([pondModel, frogModel]) => {
    if (stopped) return;
    const pond = pondModel.scene.clone(true);
    pond.traverse((object) => {
      if (object.isMesh) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
      if (object.userData.sway) {
        swaying.push({ object, amount: object.userData.sway, speed: object.userData.speed ?? 1,
          phase: Math.random() * 6.28, baseX: object.rotation.x, baseZ: object.rotation.z });
      }
    });
    scene.add(pond);
    pond.updateMatrixWorld(true);   // so attach() below knows where each pad really is
    for (let i = 1; i <= STAGES; i += 1) {
      const object = pond.getObjectByName(`Pad_${i}`);
      const flower = pond.getObjectByName(`Flower_${i}`);
      if (!object || !flower) continue;
      object.attach(flower);   // the lotus rides its pad up and down
      object.rotation.reorder("YXZ");   // turn first, so the little tilt added below doesn't flip the pad over
      const box = new THREE.Box3().setFromObject(object);
      const size = (box.max.x - box.min.x) / 2;
      pads.push({ object, flower, x: object.position.x, z: object.position.z, size, dip: 0, open: i === 1 ? 1 : 0,
        flowerOffset: new THREE.Vector3(flower.position.x, 0, flower.position.z).applyQuaternion(object.quaternion), baseY: object.position.y,
        baseZ: object.rotation.z });
      water.uniforms.uPads.value[i - 1].set(object.position.x, object.position.z, size);
    }

    const frogObject = frogModel.scene.clone(true);
    frogObject.traverse((object) => {
      if (object.isMesh) object.castShadow = true;
    });
    frogObject.scale.setScalar(1.1);
    const mixer = new THREE.AnimationMixer(frogObject);
    const clip = (name) => frogModel.animations.find((item) => item.name === name);
    const idle = mixer.clipAction(clip("Idle"));
    const leapAction = mixer.clipAction(clip("Leap"));
    leapAction.setLoop(THREE.LoopOnce, 1);
    idle.play();
    scene.add(frogObject);
    frog = { object: frogObject, mixer, idle, leap: leapAction };
    frogObject.position.copy(seat(current));
    faceToward(current + 1, 1);
    onStage(current + 1);
    draw();
  }).catch(() => {});   // no models: the water and waterfall still show

  // Turn the frog toward a pad (or toward the camera, after the last one)
  function faceToward(index, amount) {
    const from = frog.object.position;
    const target = index < STAGES ? seat(index) : new THREE.Vector3(from.x, 0, from.z + 5);
    const want = Math.atan2(target.x - from.x, target.z - from.z);
    let turn = want - frog.object.rotation.y;
    turn = Math.atan2(Math.sin(turn), Math.cos(turn));
    frog.object.rotation.y += turn * amount;
  }

  function updateFrog(delta) {
    if (!frog) return;
    frog.mixer.update(delta);
    if (leap) {
      const elapsed = now - leap.start;
      // The clip crouches for the first 0.2s, flies from 0.2s to 0.65s, and squashes down on landing
      const fly = THREE.MathUtils.clamp((elapsed - 0.2) / 0.45, 0, 1);
      const eased = fly * fly * (3 - 2 * fly);
      const to = seat(leap.to);
      const position = leap.from.clone().lerp(to, eased);
      position.y += Math.sin(fly * Math.PI) * (1.4 + leap.from.distanceTo(to) * 0.12);
      frog.object.position.copy(position);
      // Turn to face where it's going during the crouch
      const want = Math.atan2(to.x - leap.from.x, to.z - leap.from.z);
      let turn = want - leap.turnFrom;
      turn = Math.atan2(Math.sin(turn), Math.cos(turn));
      frog.object.rotation.y = leap.turnFrom + turn * THREE.MathUtils.clamp(elapsed / 0.2, 0, 1);
      if (fly >= 1 && !leap.landed) {
        leap.landed = true;
        land(leap.to);
      }
      if (elapsed >= LEAP_SECONDS) {
        leap = null;
        if (queue.length) startLeap(queue.shift());
      }
    } else {
      frog.object.position.copy(seat(current));
      faceToward(current + 1, 1 - Math.pow(0.02, delta));   // slowly turn to look at the next pad
    }
  }

  function updatePads(time, delta) {
    pads.forEach((pad, i) => {
      pad.dip = Math.max(0, pad.dip - delta * 2.2);
      const dip = Math.sin(pad.dip * Math.PI) * pad.dip * 0.12;
      pad.object.position.y = pad.baseY + Math.sin(time * 1.3 + i * 1.7) * 0.025 - dip;
      pad.object.rotation.z = pad.baseZ + Math.sin(time * 0.9 + i) * 0.015;
      // The lotus: a closed bud until the frog has visited, then it opens out
      const target = pad.open ? 1 : 0;
      pad.bloom = pad.bloom === undefined ? target : pad.bloom + (target - pad.bloom) * Math.min(1, delta * 3);
      const spread = 0.65 + pad.bloom * 0.6;
      pad.flower.scale.set(spread, 1.2 - pad.bloom * 0.45, spread);
    });
  }

  // Put each stage tag next to its pad, on the screen
  const projected = new THREE.Vector3();
  function placeLabels() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    pads.forEach((pad, i) => {
      const label = labels[i];
      if (!label) return;
      projected.set(pad.x + pad.size * 1.05, pad.object.position.y, pad.z);
      projected.project(camera);
      const x = (projected.x * 0.5 + 0.5) * width;
      const y = (-projected.y * 0.5 + 0.5) * height;
      label.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(0, -50%)`;
      label.style.opacity = "1";
    });
  }

  // Click a lily pad to send the frog there
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  function handleClick(event) {
    if (!pads.length) return;
    const rect = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(pads.map((pad) => pad.object), true)[0];
    if (!hit) return;
    const index = pads.findIndex((pad) => pad.object === hit.object || pad.object.getObjectById(hit.object.id));
    if (index >= 0) goTo(index + 1);
  }
  function handleHover(event) {
    if (!pads.length) return;
    const rect = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    canvas.style.cursor = raycaster.intersectObjects(pads.map((pad) => pad.object), true).length ? "pointer" : "";
  }

  // The view drifts a little and leans toward the mouse
  const mouse = { x: 0, y: 0, smoothX: 0, smoothY: 0 };
  function handleMouse(event) {
    mouse.x = (event.clientX / window.innerWidth - 0.5) * 2;
    mouse.y = (event.clientY / window.innerHeight - 0.5) * 2;
    handleHover(event);
  }

  function fit() {
    const parent = canvas.parentElement;
    const width = parent.clientWidth;
    const height = parent.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.fov = camera.aspect < 1 ? 50 : 42;
    camera.updateProjectionMatrix();
    // Narrow screens: step back until the pond (about 9 either side of the middle) fits across
    const halfAcross = Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect);
    distance = Math.max(1, 10.8 / Math.tan(halfAcross) / CAMERA_HOME.length());
    scene.fog.near = 30 * distance;   // the haze steps back with the camera
    scene.fog.far = 52 * distance;
    draw();
  }

  // Arriving from Projects ("rise"): the camera starts high above the pond and settles down onto it
  const arrivedAt = window.cascadePondArrive;
  const arrive = !still && arrivedAt && performance.now() - arrivedAt < 2500 ? { start: performance.now(), duration: 1600 } : null;

  let stopped = false;
  let frame = 0;
  let last = performance.now();
  const startTime = last;
  function draw() {
    const clock = performance.now();
    const delta = still ? 0 : Math.min(0.05, (clock - last) / 1000);
    last = clock;
    now = still ? 3 : (clock - startTime) / 1000;
    water.uniforms.uTime.value = now;
    for (const update of updates) update(now);
    for (const item of swaying) {
      item.object.rotation.x = item.baseX + Math.sin(now * item.speed + item.phase) * item.amount;
      item.object.rotation.z = item.baseZ + Math.cos(now * item.speed * 0.8 + item.phase) * item.amount;
    }
    updatePads(now, still ? 1 : delta);
    updateFrog(delta);
    mouse.smoothX += (mouse.x - mouse.smoothX) * 0.04;
    mouse.smoothY += (mouse.y - mouse.smoothY) * 0.04;
    camera.position.copy(CAMERA_HOME).multiplyScalar(distance);
    camera.position.x += mouse.smoothX * 0.9 + Math.sin(now * 0.12) * 0.3;
    camera.position.y -= mouse.smoothY * 0.5;
    camera.position.z += Math.sin(now * 0.1) * 0.2;
    if (arrive) {
      const p = Math.min(1, (clock - arrive.start) / arrive.duration);
      const settled = 1 - Math.pow(1 - p, 3);   // fast at first, settling gently
      camera.position.y += 14 * distance * (1 - settled);
      camera.position.z -= 6 * distance * (1 - settled);
    }
    camera.lookAt(lookAt);
    renderer.render(scene, camera);
    placeLabels();
  }
  function loop() {
    draw();
    frame = requestAnimationFrame(loop);
  }

  const observer = new ResizeObserver(fit);
  observer.observe(canvas.parentElement);
  fit();
  canvas.addEventListener("click", handleClick);
  if (!still) {
    window.addEventListener("pointermove", handleMouse);
    frame = requestAnimationFrame(loop);
  }

  function stop() {
    stopped = true;
    cancelAnimationFrame(frame);
    canvas.removeEventListener("click", handleClick);
    window.removeEventListener("pointermove", handleMouse);
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
  }

  return { goTo, stop };
}
