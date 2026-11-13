import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// Small 3D views of the capybara mascot, with a see-through background.
// The capybara itself is made in Blender: frontend/blender/capybara.py builds it and exports
// public/models/capybara.glb, with its "Idle" animation (breathing, a lazy nod, blinks and an ear flick).
//
// createMascotScene(canvas, { still }) - the whole capybara, playing its idle animation at about
//   30 frames a second. Returns a function that stops it and frees its memory.
// capybaraHeadPicture(size) - draws the capybara's head once and resolves to a picture (a data URL),
//   for small badges. No 3D keeps running afterwards.
const MODEL_URL = "/models/capybara.glb";

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

// Put a copy of the Blender capybara in the scene, with its idle animation ready to play
function addCapybara(scene, gltf) {
  const capybara = gltf.scene.clone(true);
  capybara.traverse((object) => {
    if (object.isMesh) {
      object.castShadow = true;
      object.receiveShadow = true;
    }
  });
  scene.add(capybara);
  // Blender exports the idle loop as one clip per moving part (body, head, eyes, ears).
  // They are all the same length, so playing them together keeps them in step.
  const mixer = new THREE.AnimationMixer(capybara);
  for (const clip of gltf.animations) mixer.clipAction(clip).play();
  return mixer;
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
  // A three-quarter view from the front-right, a little above, like the island's camera
  const camera = new THREE.PerspectiveCamera(28, width / height, 0.1, 50);
  camera.position.set(3.6, 2.4, 5.4);
  camera.lookAt(0.4, 0.8, 0);

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
    mixer = addCapybara(scene, gltf);
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

export async function capybaraHeadPicture(size) {
  const gltf = await loadModel();
  const canvas = document.createElement("canvas");
  const { renderer, scene } = setUp(canvas, size, size);
  addCapybara(scene, gltf).update(0);
  const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 50);
  camera.position.set(4.1, 1.95, 2.7);
  camera.lookAt(1.45, 1.25, 0);
  renderer.render(scene, camera);
  const picture = canvas.toDataURL("image/png");
  freeAll(scene, renderer);
  return picture;
}
