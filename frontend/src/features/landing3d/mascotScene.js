import * as THREE from "three";
import { buildCapybara } from "./capybaraModel";

// Small 3D views of the capybara mascot (capybaraModel.js), with a see-through background.
//
// createMascotScene(canvas, { still }) - the whole capybara, idling (breathing, blinking, ear flicks)
//   at about 30 frames a second. Returns a function that stops it and frees its memory.
// capybaraHeadPicture(size) - draws the capybara's head once and returns it as a picture (a data URL),
//   for small badges. No 3D keeps running afterwards.

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

  const capybara = buildCapybara();
  scene.add(capybara.group);
  return { renderer, scene, capybara };
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
  const { renderer, scene, capybara } = setUp(canvas, width, height);
  // A three-quarter view from the front-right, a little above, like the island's camera
  const camera = new THREE.PerspectiveCamera(28, width / height, 0.1, 50);
  camera.position.set(3.4, 2.5, 5.2);
  camera.lookAt(0.25, 0.85, 0);

  const start = performance.now();
  let frame = 0;
  let timer = 0;
  function draw() {
    capybara.update(still ? 0 : (performance.now() - start) / 1000);
    renderer.render(scene, camera);
  }
  function loop() {
    draw();
    timer = setTimeout(() => { frame = requestAnimationFrame(loop); }, 1000 / 30 - 4);
  }
  if (still) draw();
  else loop();

  return () => {
    cancelAnimationFrame(frame);
    clearTimeout(timer);
    freeAll(scene, renderer);
  };
}

export function capybaraHeadPicture(size) {
  const canvas = document.createElement("canvas");
  const { renderer, scene } = setUp(canvas, size, size);
  const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 50);
  camera.position.set(3.6, 2.2, 2.6);
  camera.lookAt(1.25, 1.45, 0);
  renderer.render(scene, camera);
  const picture = canvas.toDataURL("image/png");
  freeAll(scene, renderer);
  return picture;
}
