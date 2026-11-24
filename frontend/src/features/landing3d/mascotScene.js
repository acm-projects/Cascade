import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// Small 3D views of the frog mascot, with a see-through background.
// The frog is Cassie: the cute original frog with a little kit (CASSIE_KIT below), made in Blender by
// frontend/blender/frog_director.py, with an "Idle" clip (breathing, blinks, and the kit's own motion: the
// clapperboard snapping, or the camera's red light blinking) and a "Leap" clip (a hop, not used).
// The "How it works" pond keeps its own frog (blender/frog.py, public/models/frog.glb).
// (The earlier capybara mascot is still in frontend/blender/capybara.py and public/models/capybara.glb.)
//
// createMascotScene(canvas, { still }) - the whole frog idling at about 30 frames a second (no hopping: Sai's call;
//   the "Leap" clip is still in the model if it's ever wanted). Returns a function that stops it and frees its memory.
// mascotHeadPicture(size) - draws the frog's face once and resolves to a picture (a data URL),
//   for small badges. No 3D keeps running afterwards.
//
// Which kit Cassie has (both are built by blender/frog_director.py, and both stay ready):
//   "director" - a little clapperboard and megaphone at her feet (public/models/frog_director.glb)
//   "camera"   - a little camera on a tripod beside her (public/models/frog_camera.glb)
const CASSIE_KIT = "camera";
const MODEL_URL = `/models/frog_${CASSIE_KIT}.glb`;
// The camera kit is wider (the tripod stands beside her), so its view is pulled back and moved over a little
const FULL_VIEW = CASSIE_KIT === "camera"
  ? { from: [0.6, 1.45, 3.4], at: [0.32, 0.45, 0] }
  : { from: [0.35, 1.4, 3.0], at: [0, 0.4, 0] };

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
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight("#fff8e8", "#8a6a48", 1.7));
  const sun = new THREE.DirectionalLight("#fff3dc", 2.4);
  sun.position.set(3, 6, 4);
  sun.castShadow = true;
  sun.shadow.mapSize.set(512, 512);
  for (const side of ["left", "bottom"]) sun.shadow.camera[side] = -3;
  for (const side of ["right", "top"]) sun.shadow.camera[side] = 3;
  scene.add(sun);

  // A soft shadow on the "floor" so it looks like it's sitting on the panel
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(8, 8), new THREE.ShadowMaterial({ opacity: 0.18 }));
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  return { renderer, scene };
}

// Put a copy of the Blender frog in the scene, with its idle loop playing
function addMascot(scene, gltf) {
  const frog = gltf.scene.clone(true);
  frog.traverse((object) => {
    if (object.isMesh) {
      object.castShadow = true;
      object.receiveShadow = true;
    }
  });
  frog.rotation.y = 0.45;   // turned a little toward the side, so it reads as 3D
  scene.add(frog);
  const mixer = new THREE.AnimationMixer(frog);
  const clip = (name) => gltf.animations.find((item) => item.name === name);
  mixer.clipAction(clip("Idle")).play();
  return { mixer };
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

export function createMascotScene(canvas, { still = false } = {}) {
  const width = canvas.clientWidth || 160;
  const height = canvas.clientHeight || 130;
  const { renderer, scene } = setUp(canvas, width, height);
  // From the front, a little above
  const camera = new THREE.PerspectiveCamera(28, width / height, 0.1, 50);
  camera.position.set(...FULL_VIEW.from);
  camera.lookAt(...FULL_VIEW.at);

  let stopped = false;
  let mixer = null;
  let frame = 0;
  let timer = 0;
  const clock = new THREE.Clock();
  function loop() {
    mixer.update(clock.getDelta());
    renderer.render(scene, camera);
    timer = setTimeout(() => { frame = requestAnimationFrame(loop); }, 1000 / 30 - 4);
  }
  loadModel().then((gltf) => {
    if (stopped) return;
    ({ mixer } = addMascot(scene, gltf));
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

export async function mascotHeadPicture(size) {
  const gltf = await loadModel();
  const canvas = document.createElement("canvas");
  const { renderer, scene } = setUp(canvas, size, size);
  addMascot(scene, gltf).mixer.update(0);
  // Close on the frog's face and big eyes
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
  camera.position.set(0.55, 1.15, 2.3);
  camera.lookAt(0.05, 0.6, 0);
  renderer.render(scene, camera);
  const picture = canvas.toDataURL("image/png");
  freeAll(scene, renderer);
  return picture;
}
