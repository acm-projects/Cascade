import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// Small 3D views of Cassie the seahorse, with a see-through background.
// She is made in Blender: frontend/blender/seahorse.py builds her and exports public/models/seahorse.glb,
// with one "Idle" clip (bobbing, swaying, a fluttering back fin, a curling tail, a blink).
//
// She glows like a deep-sea creature: her emissive parts (fins, crown, spots) breathe gently brighter and dimmer.
// createSeahorseScene(canvas, { still }) - the whole seahorse floating, at about 30 frames a second.
//   Returns a function that stops it and frees its memory.
// seahorseHeadPicture(size) - draws her face once and resolves to a picture (a data URL),
//   for small badges like the AI Studio chat. No 3D keeps running afterwards.
const MODEL_URL = "/models/seahorse.glb";

// Download the model once; every view makes its own copy of it
let modelPromise = null;
function loadModel() {
  modelPromise ??= new GLTFLoader().loadAsync(MODEL_URL).catch((error) => {
    modelPromise = null;   // let a later try download it again
    throw error;
  });
  return modelPromise;
}

function setUp(canvas, width, height) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x000000, 0);
  renderer.setSize(width, height, false);

  // Underwater light: bright from above, a cool sea-blue bounce from below
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight("#fff6e6", "#3a6fb8", 1.8));
  const sun = new THREE.DirectionalLight("#fff3dc", 2.2);
  sun.position.set(2, 5, 4);
  scene.add(sun);
  const rim = new THREE.DirectionalLight("#9ff4ff", 1.6);   // a cool aqua edge light from behind, to go with her glow
  rim.position.set(-3, 2, -3);
  scene.add(rim);
  return { renderer, scene };
}

// Put a copy of the Blender seahorse in the scene, with her idle loop playing
function addSeahorse(scene, gltf) {
  const seahorse = gltf.scene.clone(true);
  seahorse.rotation.y = -0.3;   // turned a little toward us, so she reads as 3D but keeps her profile
  scene.add(seahorse);
  const mixer = new THREE.AnimationMixer(seahorse);
  const idle = gltf.animations.find((item) => item.name === "Idle");
  if (idle) mixer.clipAction(idle).play();
  return mixer;
}

// Her glowing parts (fins, crown, spots, eye shine, tail tip are emissive in Blender), each with its own phase,
// so the glow breathes softly across her body instead of blinking all at once
function glowingParts(scene) {
  const parts = [];
  scene.traverse((object) => {
    const material = object.material;
    if (!material?.emissive || material.emissive.getHex() === 0 || parts.some((p) => p.material === material)) return;
    parts.push({ material, base: material.emissiveIntensity, phase: parts.length * 1.3 });
  });
  return parts;
}

function breathe(parts, time) {
  for (const { material, base, phase } of parts) material.emissiveIntensity = base * (0.8 + 0.3 * Math.sin(time * 1.8 + phase));
}

function freeAll(scene, renderer) {
  const seen = new Set();
  scene.traverse((object) => {
    for (const thing of [object.geometry, object.material]) {
      if (thing && !seen.has(thing)) { seen.add(thing); thing.dispose(); }
    }
  });
  renderer.dispose();
  renderer.forceContextLoss();
}

export function createSeahorseScene(canvas, { still = false } = {}) {
  const width = canvas.clientWidth || 150;
  const height = canvas.clientHeight || 225;
  const { renderer, scene } = setUp(canvas, width, height);
  // Side-on, from straight in front of her profile
  const camera = new THREE.PerspectiveCamera(30, width / height, 0.1, 50);
  camera.position.set(0.15, 0.95, 4.3);
  camera.lookAt(0.12, 0.92, 0);

  let stopped = false;
  let mixer = null;
  let glow = [];
  let frame = 0;
  let timer = 0;
  const clock = new THREE.Clock();
  function loop() {
    mixer.update(clock.getDelta());
    breathe(glow, clock.elapsedTime);
    renderer.render(scene, camera);
    timer = setTimeout(() => { frame = requestAnimationFrame(loop); }, 1000 / 30 - 4);
  }
  loadModel().then((gltf) => {
    if (stopped) return;
    mixer = addSeahorse(scene, gltf);
    glow = glowingParts(scene);
    if (still) {
      mixer.update(0);
      renderer.render(scene, camera);
    } else {
      loop();
    }
  }).catch(() => {});   // no model: the space just stays empty

  return () => {
    stopped = true;
    cancelAnimationFrame(frame);
    clearTimeout(timer);
    freeAll(scene, renderer);
  };
}

export async function seahorseHeadPicture(size) {
  const gltf = await loadModel();
  const canvas = document.createElement("canvas");
  const { renderer, scene } = setUp(canvas, size, size);
  addSeahorse(scene, gltf).update(0);
  // Close on her face, crown and big eye
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
  camera.position.set(0.2, 1.55, 1.8);
  camera.lookAt(0.18, 1.52, 0);
  renderer.render(scene, camera);
  const picture = canvas.toDataURL("image/png");
  freeAll(scene, renderer);
  return picture;
}
