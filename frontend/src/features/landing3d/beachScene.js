import * as THREE from "three";
import { instanced, lumpyBall, makeRandom, material, pick } from "./islandScene";

// The 3D beach behind the AI Studio canvas: gentle sand dunes with shells, pebbles, starfish, driftwood
// and sea grass, in warm sunlight. The cards, lily pads and vines sit on top (they're the React Flow canvas).
// When you pan or zoom the canvas, the beach slides along a little behind them, which gives it depth.
//
// It's a work page, so it only draws when something changes (panning, zooming, resizing), not every frame.
// createBeachScene(canvas, { still }) starts it and returns a function that stops it and frees its memory.

const SAND = ["#f1e4c4", "#ecdcb6", "#f5ead0", "#e8d6ab"];
const AREA_X = 70;   // how far the beach reaches each way, so panning never runs off the edge
const AREA_Z = 55;

function sandHeight(x, z) {
  return Math.sin(x * 0.18 + 1) * 0.45 + Math.cos(z * 0.22 + x * 0.05) * 0.4 + Math.sin(x * 0.6 + z * 0.45) * 0.12;
}

function buildSand(scene, random) {
  const geometry = new THREE.PlaneGeometry(AREA_X * 2, AREA_Z * 2, 110, 85);
  geometry.rotateX(-Math.PI / 2);
  const position = geometry.attributes.position;
  const colors = [];
  const color = new THREE.Color();
  for (let i = 0; i < position.count; i += 1) {
    const x = position.getX(i);
    const z = position.getZ(i);
    position.setY(i, sandHeight(x, z));
    color.set(pick(SAND, random));
    colors.push(color.r, color.g, color.b);
  }
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  const sand = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, flatShading: true }));
  sand.receiveShadow = true;
  scene.add(sand);
}

function buildBeachThings(scene, random) {
  const spot = () => {
    const x = (random() - 0.5) * AREA_X * 1.9;
    const z = (random() - 0.5) * AREA_Z * 1.9;
    return [x, z, sandHeight(x, z)];
  };

  // Pebbles and sea-grass tufts: lots of small things, drawn in one go each
  const pebbles = [];
  for (let i = 0; i < 160; i += 1) {
    const [x, z, y] = spot();
    const size = 0.6 + random() * 1.4;
    pebbles.push({ x, y: y + 0.04, z, ry: random() * 6, sx: size, sy: size * 0.55, sz: size * (0.7 + random() * 0.5), color: pick(["#b9b2a6", "#a39c92", "#cfc6b6", "#8f8a83"], random) });
  }
  instanced(scene, new THREE.DodecahedronGeometry(0.16, 0), material("#ffffff"), pebbles, true);

  const blades = [];
  for (let i = 0; i < 45; i += 1) {
    const [x, z, y] = spot();
    const shade = pick(["#7fae4a", "#93bf55", "#6a9a3e"], random);
    for (let b = 0; b < 6; b += 1) {
      const angle = (b / 6) * Math.PI * 2 + random();
      blades.push({ x: x + Math.cos(angle) * 0.12, y: y + 0.3, z: z + Math.sin(angle) * 0.12, rx: Math.sin(angle) * 0.4, rz: -Math.cos(angle) * 0.4, sy: 0.8 + random() * 0.7, color: shade });
    }
  }
  instanced(scene, new THREE.ConeGeometry(0.06, 0.7, 4), material("#ffffff"), blades, true);

  // Shells: a fan shape with ridges
  const shellShape = new THREE.SphereGeometry(0.4, 9, 4, 0, Math.PI, 0, Math.PI / 2);
  shellShape.scale(1, 0.45, 1);
  for (let i = 0; i < 40; i += 1) {
    const [x, z, y] = spot();
    const shell = new THREE.Mesh(shellShape, material(pick(["#ffd9c7", "#ffe9b8", "#f7b8c4", "#fff4e6"], random)));
    shell.position.set(x, y + 0.02, z);
    shell.rotation.y = random() * 6;
    shell.scale.setScalar(0.6 + random() * 0.6);
    shell.castShadow = true;
    scene.add(shell);
  }

  // Starfish
  const star = new THREE.Shape();
  for (let i = 0; i < 10; i += 1) {
    const radius = i % 2 ? 0.16 : 0.45;
    const angle = (i / 10) * Math.PI * 2;
    if (i === 0) star.moveTo(Math.cos(angle) * radius, Math.sin(angle) * radius);
    else star.lineTo(Math.cos(angle) * radius, Math.sin(angle) * radius);
  }
  const starShape = new THREE.ExtrudeGeometry(star, { depth: 0.1, bevelEnabled: true, bevelSize: 0.03, bevelThickness: 0.03, bevelSegments: 1 });
  for (let i = 0; i < 14; i += 1) {
    const [x, z, y] = spot();
    const starfish = new THREE.Mesh(starShape, material(pick(["#ff8a3d", "#ff5d73", "#ffcf3d", "#c77dff"], random)));
    starfish.rotation.set(-Math.PI / 2, 0, random() * 6);
    starfish.position.set(x, y + 0.04, z);
    starfish.castShadow = true;
    scene.add(starfish);
  }

  // Driftwood and a few bigger rocks
  for (let i = 0; i < 9; i += 1) {
    const [x, z, y] = spot();
    const log = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.24, 3 + random() * 2.5, 7), material(pick(["#a98563", "#9a7653", "#b89572"], random)));
    log.rotation.set(Math.PI / 2, 0, random() * 6);
    log.position.set(x, y + 0.15, z);
    log.castShadow = true;
    scene.add(log);
  }
  for (let i = 0; i < 14; i += 1) {
    const [x, z, y] = spot();
    const size = 0.5 + random() * 0.8;
    const rock = new THREE.Mesh(lumpyBall(size, random, 0.22, 0), material(pick(["#a39c92", "#8f8a83", "#b9b2a6"], random)));
    rock.scale.y = 0.6;
    rock.position.set(x, y + size * 0.15, z);
    rock.castShadow = true;
    rock.receiveShadow = true;
    scene.add(rock);
  }
}

export function createBeachScene(canvas, { still = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#f1e4c4");
  const camera = new THREE.PerspectiveCamera(35, 1, 0.5, 200);

  // Warm afternoon sun from the upper left
  scene.add(new THREE.HemisphereLight("#fff6e0", "#c9a36a", 1.6));
  const sun = new THREE.DirectionalLight("#fff1d2", 2.2);
  sun.position.set(-18, 30, -12);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  for (const side of ["left", "bottom"]) sun.shadow.camera[side] = -45;
  for (const side of ["right", "top"]) sun.shadow.camera[side] = 45;
  sun.shadow.camera.far = 120;
  sun.shadow.bias = -0.0008;
  scene.add(sun);
  scene.add(sun.target);

  const random = makeRandom(20261109);
  buildSand(scene, random);
  buildBeachThings(scene, random);

  // Where the camera is aimed. Panning the canvas slides this (a little, so the beach feels further away than the cards).
  const aim = { x: 0, z: 0, zoom: 1 };
  const shown = { x: 0, z: 0, zoom: 1 };
  const UNITS_PER_PIXEL = 0.012;

  function place() {
    const distance = 34 / Math.pow(shown.zoom, 0.35);
    camera.position.set(shown.x, distance * 0.85, shown.z + distance * 0.55);
    camera.lookAt(shown.x, 0, shown.z);
    // Keep the sun's shadows around what's on screen
    sun.position.set(shown.x - 18, 30, shown.z - 12);
    sun.target.position.set(shown.x, 0, shown.z);
  }

  // Draw only when something changed, easing the camera to where it should be
  let frame = 0;
  function draw() {
    frame = 0;
    shown.x += (aim.x - shown.x) * 0.25;
    shown.z += (aim.z - shown.z) * 0.25;
    shown.zoom += (aim.zoom - shown.zoom) * 0.25;
    place();
    renderer.render(scene, camera);
    const settled = Math.abs(aim.x - shown.x) < 0.01 && Math.abs(aim.z - shown.z) < 0.01 && Math.abs(aim.zoom - shown.zoom) < 0.001;
    if (!settled && !still) frame = requestAnimationFrame(draw);
  }
  function redraw() {
    if (!frame) frame = requestAnimationFrame(draw);
  }

  function handleCanvasMove(event) {
    const { x = 0, y = 0, zoom = 1 } = event.detail ?? {};
    aim.x = -x * UNITS_PER_PIXEL;
    aim.z = -y * UNITS_PER_PIXEL;
    aim.zoom = zoom;
    if (still) {   // no easing for people who turned off animations
      Object.assign(shown, aim);
      place();
      renderer.render(scene, camera);
    } else {
      redraw();
    }
  }

  function fit() {
    const parent = canvas.parentElement;
    const width = parent.clientWidth;
    const height = parent.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    place();
    renderer.render(scene, camera);
  }

  const observer = new ResizeObserver(fit);
  observer.observe(canvas.parentElement);
  fit();
  window.addEventListener("cascade:canvas-move", handleCanvasMove);

  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("cascade:canvas-move", handleCanvasMove);
    observer.disconnect();
    const seen = new Set();
    const free = (thing) => { if (thing && !seen.has(thing)) { seen.add(thing); thing.dispose?.(); } };
    scene.traverse((object) => {
      free(object.geometry);
      for (const item of [object.material].flat()) free(item);
    });
    renderer.dispose();
    renderer.forceContextLoss();
  };
}
