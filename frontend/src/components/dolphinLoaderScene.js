import * as THREE from "three";

// The 3D loading screen (DolphinLoader.jsx): blocky dolphins, built out of boxes like the sea animals in
// seaCreatures.js, leaping out of the water one after another. Each one bursts up through the surface, arcs over
// with its shadow sliding along the water underneath, and dives back in. Where it leaves and where it lands, a ring
// of white pixel ripples spreads out and square droplets splash up and fall back.
// The water itself is the page's own pixel sea behind this see-through canvas: the scene only draws a surface you
// can't see, which hides the parts of a dolphin that are still under water.
//
// createDolphinLoaderScene(canvas, { still }) starts it (about 30 frames a second) and returns a function that
// stops it. It throws if the device can't draw 3D, so the caller can show something simpler instead.
// In the scene: +x is right, +y is up, the water's surface is y = 0, +z comes toward you.

const LEAP_TIME = 2.4;   // seconds for one dolphin's leap; the three are a third of a leap apart
const DOLPHINS = [
  // where each one jumps from and lands (x), how far back it is (z), and how high it goes
  { from: -3.4, to: 2.6, z: -0.6, height: 2.3, delay: 0 },
  { from: -2.4, to: 3.4, z: 1.4, height: 1.9, delay: 1 / 3 },
  { from: -3.0, to: 3.0, z: -2.4, height: 2.6, delay: 2 / 3 },
];

const C = {
  back: 0x8fc8f0, side: 0xa9d8f7, dark: 0x5f9ed6, belly: 0xffffff, eye: 0x15181d, shine: 0xffffff,
};

export function createDolphinLoaderScene(canvas, { still = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.localClippingEnabled = true;

  const scene = new THREE.Scene();
  // a little above the water, looking down across it, like the reference
  const camera = new THREE.PerspectiveCamera(32, 2, 0.1, 60);
  camera.position.set(0, 3.6, 10);
  camera.lookAt(0, 1.0, 0);
  scene.add(new THREE.HemisphereLight(0xeaf8ff, 0x2a6fb0, 2.0));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(-3, 8, 5);
  scene.add(sun);

  // Anything under the surface isn't drawn, so dolphins rise out of the water and sink back into it
  const aboveWater = [new THREE.Plane(new THREE.Vector3(0, 1, 0), 0.02)];
  const geometries = new Map();
  const materials = new Map();
  const geo = (w, h, d) => {
    const key = `${w}|${h}|${d}`;
    if (!geometries.has(key)) geometries.set(key, new THREE.BoxGeometry(w, h, d));
    return geometries.get(key);
  };
  const mat = (color) => {
    if (!materials.has(color)) {
      materials.set(color, new THREE.MeshLambertMaterial({ color, clippingPlanes: aboveWater }));
    }
    return materials.get(color);
  };
  const box = (parent, w, h, d, color, x = 0, y = 0, z = 0) => {
    const mesh = new THREE.Mesh(geo(w, h, d), mat(color));
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  };

  // One blocky dolphin, facing +x, about 2.4 long, its middle at the origin
  function makeDolphin() {
    const dolphin = new THREE.Group();
    const body = new THREE.Group();
    dolphin.add(body);
    box(body, 1.3, 0.62, 0.62, C.side, 0.1, 0);                 // chest
    box(body, 1.24, 0.2, 0.64, C.belly, 0.12, -0.24);           // white belly
    box(body, 0.6, 0.54, 0.56, C.side, 0.9, 0.02);              // head
    box(body, 0.56, 0.16, 0.58, C.belly, 0.9, -0.2);            // chin
    box(body, 0.32, 0.18, 0.26, C.side, 1.32, -0.06);           // beak
    box(body, 0.3, 0.1, 0.28, C.belly, 1.32, -0.17);
    box(body, 1.1, 0.14, 0.5, C.back, 0.15, 0.36);              // darker back
    for (const s of [-1, 1]) {
      box(body, 0.12, 0.12, 0.04, C.eye, 1.0, 0.1, s * 0.29);   // eyes
      box(body, 0.05, 0.05, 0.02, C.shine, 1.02, 0.13, s * 0.31);
      box(body, 0.32, 0.06, 0.26, C.dark, 0.35, -0.3, s * 0.4).rotation.y = s * 0.5;   // flippers
    }
    const fin = box(body, 0.36, 0.34, 0.08, C.dark, -0.05, 0.5);   // dorsal fin, swept back
    fin.rotation.z = 0.5;
    const tail = new THREE.Group();
    tail.position.x = -0.55;
    body.add(tail);
    box(tail, 0.55, 0.46, 0.46, C.side, -0.27, 0);
    box(tail, 0.5, 0.12, 0.42, C.belly, -0.24, -0.18);
    box(tail, 0.4, 0.32, 0.32, C.side, -0.68, 0.02);
    const flukes = box(tail, 0.24, 0.08, 0.9, C.dark, -0.98, 0.02);
    scene.add(dolphin);
    return { dolphin, tail, flukes };
  }

  // Its shadow on the water: a soft dark ellipse that shrinks and fades the higher the dolphin is
  const shadowMaterial = new THREE.MeshBasicMaterial({ color: 0x0a3a6e, transparent: true, opacity: 0.3, depthWrite: false });
  const shadowGeometry = new THREE.CircleGeometry(1, 24);

  // Pixel ripples (small white squares in a ring on the surface) and square droplets
  const whiteMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true });
  const pixel = new THREE.BoxGeometry(0.1, 0.02, 0.1);
  const drop = new THREE.BoxGeometry(0.11, 0.11, 0.11);
  function makeSplash() {
    const group = new THREE.Group();
    const ripple = [];
    for (let i = 0; i < 22; i += 1) {
      const angle = (i / 22) * Math.PI * 2;
      const square = new THREE.Mesh(pixel, whiteMaterial.clone());
      square.userData = { angle };
      group.add(square);
      ripple.push(square);
    }
    const drops = [];
    for (let i = 0; i < 9; i += 1) {
      const square = new THREE.Mesh(drop, whiteMaterial.clone());
      const angle = (i / 9) * Math.PI * 2 + 0.3;
      square.userData = { vx: Math.cos(angle) * (0.6 + (i % 3) * 0.35), vz: Math.sin(angle) * 0.5, vy: 2.6 + (i % 4) * 0.55 };
      group.add(square);
      drops.push(square);
    }
    scene.add(group);
    return { group, ripple, drops };
  }
  // age: seconds since the dolphin broke the surface here (or < 0 / too old: nothing shows)
  function showSplash(splash, age) {
    const alive = age >= 0 && age < 1.1;
    splash.group.visible = alive;
    if (!alive) return;
    const spread = 0.25 + age * 1.6;
    for (const square of splash.ripple) {
      const { angle } = square.userData;
      // snapped to a coarse grid, so the ring looks like the sea's pixel dashes
      square.position.set(Math.round(Math.cos(angle) * spread * 1.6 * 10) / 10, 0.01, Math.round(Math.sin(angle) * spread * 0.6 * 10) / 10);
      square.material.opacity = Math.max(0, 0.9 - age * 0.85);
    }
    for (const square of splash.drops) {
      const { vx, vy, vz } = square.userData;
      const t = Math.min(age, 0.8);
      square.position.set(vx * t, Math.max(0, vy * t - 6 * t * t), vz * t);
      square.material.opacity = age < 0.8 ? 1 : 0;
    }
  }

  const leapers = DOLPHINS.map((spec) => {
    const parts = makeDolphin();
    const shadow = new THREE.Mesh(shadowGeometry, shadowMaterial.clone());
    shadow.rotation.x = -Math.PI / 2;
    scene.add(shadow);
    return { spec, ...parts, shadow, out: makeSplash(), in: makeSplash() };
  });

  // The leap: the dolphin's middle follows a parabola from a little under the water at `from`, up to `height`,
  // and back under at `to`. It starts and ends deep enough that its whole body is under the surface.
  const DEPTH = 1.3;
  function place(leaper, now) {
    const { spec, dolphin, tail, flukes, shadow } = leaper;
    const p = (((now / LEAP_TIME + spec.delay) % 1) + 1) % 1;   // 0 to 1 through this leap
    const x = spec.from + (spec.to - spec.from) * p;
    const arc = 4 * p * (1 - p);                                // 0 at the ends, 1 at the top
    const y = -DEPTH + (spec.height + DEPTH) * arc;
    // nose along the direction it's moving: up out of the water, level at the top, down into it
    const slope = ((spec.height + DEPTH) * 4 * (1 - 2 * p)) / (spec.to - spec.from);
    dolphin.position.set(x, y, spec.z);
    dolphin.rotation.z = Math.atan(slope);
    tail.rotation.z = Math.sin(now * 14 + spec.delay * 9) * 0.28;   // tail beats as it swims
    flukes.rotation.x = Math.sin(now * 14 + spec.delay * 9) * 0.15;
    // shadow on the water right under it, smaller and fainter the higher it is
    const lift = Math.max(0, y);
    shadow.visible = y > -0.3;
    shadow.position.set(x, 0.005, spec.z);
    shadow.scale.set(1.2 - lift * 0.18, 0.32 - lift * 0.05, 1);
    shadow.material.opacity = 0.3 - lift * 0.05;
    // splashes: where it breaks out of the water, and where it dives back in
    const surface = DEPTH / (spec.height + DEPTH);              // arc value where its middle crosses y = 0
    const crossOut = (1 - Math.sqrt(1 - surface)) / 2;          // the p values where 4p(1-p) = surface
    const crossIn = 1 - crossOut;
    leaper.out.group.position.set(spec.from + (spec.to - spec.from) * crossOut, 0, spec.z);
    leaper.in.group.position.set(spec.from + (spec.to - spec.from) * crossIn, 0, spec.z);
    showSplash(leaper.out, (p - crossOut) * LEAP_TIME);
    showSplash(leaper.in, (p - crossIn) * LEAP_TIME);
  }

  function fit() {
    const width = canvas.clientWidth || 480;
    const height = canvas.clientHeight || 260;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  let frame = 0;
  let timer = 0;
  const start = performance.now();
  function draw(now) {
    for (const leaper of leapers) place(leaper, now);
    renderer.render(scene, camera);
  }
  function loop() {
    draw((performance.now() - start) / 1000);
    timer = setTimeout(() => { frame = requestAnimationFrame(loop); }, 1000 / 30 - 4);
  }

  fit();
  const observer = new ResizeObserver(() => { fit(); if (still) draw(LEAP_TIME * 0.5); });
  observer.observe(canvas);
  if (still) draw(LEAP_TIME * 0.5);   // reduced motion: one still moment, the first dolphin at the top of its leap
  else loop();

  return () => {
    cancelAnimationFrame(frame);
    clearTimeout(timer);
    observer.disconnect();
    const seen = new Set();
    scene.traverse((object) => {
      for (const thing of [object.geometry, object.material]) {
        if (thing && !seen.has(thing)) { seen.add(thing); thing.dispose(); }
      }
    });
    renderer.dispose();
    renderer.forceContextLoss();
  };
}
