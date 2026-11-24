import * as THREE from "three";

// The 3D loading screen (DolphinLoader.jsx): blocky dolphins, built out of boxes like the sea animals in
// seaCreatures.js, leaping out of the water one after another. Each one bursts up through the surface, arcs over
// with its shadow sliding along the water underneath, and dives back in. Where it leaves and where it lands, a ring
// of white pixel ripples spreads out and square droplets splash up and fall back.
// The water itself is the page's own pixel sea behind this see-through canvas: the scene only draws a surface you
// can't see, which hides the parts of a dolphin that are still under water.
//
// With { flips: true }, some of the dolphins do a somersault at the top of their leap (see flipEvery below).
//
// createDolphinLoaderScene(canvas, { still, flips }) starts it (about 30 frames a second) and returns a function that
// stops it. It throws if the device can't draw 3D, so the caller can show something simpler instead.
// In the scene: +x is right, +y is up, the water's surface is y = 0, +z comes toward you.

const LEAP_TIME = 2.4;   // seconds for one dolphin's leap; the three are a third of a leap apart
const DOLPHINS = [
  // where each one jumps from and lands (x), how far back it is (z), and how high it goes
  // flipEvery (only with { flips: true }): 1 = a flip on every leap, 2 = on every other leap, 0 = never
  { from: -3.4, to: 2.6, z: -0.6, height: 2.3, delay: 0, flipEvery: 0 },
  { from: -2.4, to: 3.4, z: 1.4, height: 1.9, delay: 1 / 3, flipEvery: 1 },
  { from: -3.0, to: 3.0, z: -2.4, height: 2.6, delay: 2 / 3, flipEvery: 2 },
];
const FLIP_HEIGHT = 0.6;   // a flipping dolphin jumps this much higher, to make room for the somersault

const C = {
  back: 0x4f86c6,   // deep sea-blue along the top
  side: 0x7fb2e5,   // lighter blue down the sides
  belly: 0xf2f8ff,  // white belly and chin
  fin: 0x3f70ae,    // fins and flukes, darkest
  mouth: 0x2e5486,
  eye: 0x15181d, shine: 0xffffff,
};

export function createDolphinLoaderScene(canvas, { still = false, flips = false } = {}) {
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

  // One blocky dolphin, facing +x, about 2.8 long, its middle at the origin. Built to read as a dolphin, not a fish:
  // a thick middle, a rounded forehead (the "melon") with a short beak set low under it, a smile, a tall dorsal fin
  // swept back, a tail that narrows to a thin stalk, and wide flukes. Deep blue on top, white underneath.
  function makeDolphin() {
    const dolphin = new THREE.Group();
    const body = new THREE.Group();
    dolphin.add(body);
    // body: chest and middle are the thickest part
    box(body, 0.95, 0.74, 0.68, C.side, 0.1, 0);                 // middle
    box(body, 0.55, 0.68, 0.64, C.side, 0.82, 0.01);             // chest
    box(body, 0.92, 0.16, 0.56, C.back, 0.12, 0.36);             // dark back
    box(body, 0.5, 0.14, 0.52, C.back, 0.8, 0.34);
    box(body, 0.92, 0.22, 0.7, C.belly, 0.12, -0.27);            // white belly
    box(body, 0.52, 0.2, 0.66, C.belly, 0.82, -0.25);
    // head: a rounded forehead, then a short beak set low, with a white chin
    box(body, 0.42, 0.62, 0.58, C.side, 1.27, 0.0);
    box(body, 0.34, 0.14, 0.48, C.back, 1.25, 0.33);             // top of the forehead
    box(body, 0.18, 0.4, 0.5, C.side, 1.55, -0.01);              // the rounded front of the melon
    box(body, 0.42, 0.18, 0.56, C.belly, 1.29, -0.22);           // chin
    box(body, 0.38, 0.17, 0.26, C.side, 1.8, -0.15);             // beak
    box(body, 0.38, 0.08, 0.27, C.belly, 1.8, -0.24);
    for (const s of [-1, 1]) {
      box(body, 0.42, 0.035, 0.02, C.mouth, 1.55, -0.14, s * 0.27);   // the smile
      box(body, 0.13, 0.13, 0.04, C.eye, 1.3, 0.05, s * 0.29);        // eyes
      box(body, 0.05, 0.05, 0.02, C.shine, 1.33, 0.09, s * 0.31);
      const flipper = box(body, 0.42, 0.06, 0.3, C.fin, 0.62, -0.32, s * 0.44);   // flippers, angled back and down
      flipper.rotation.set(s * 0.35, s * 0.6, -0.35);
    }
    // a tall dorsal fin, stepped so it sweeps back in a curve
    box(body, 0.42, 0.16, 0.12, C.fin, 0.05, 0.5);
    box(body, 0.32, 0.16, 0.1, C.fin, -0.06, 0.65);
    box(body, 0.2, 0.14, 0.08, C.fin, -0.18, 0.79);
    // tail: narrows to a thin stalk, then wide flukes (it beats up and down from here)
    const tail = new THREE.Group();
    tail.position.x = -0.38;
    body.add(tail);
    box(tail, 0.5, 0.56, 0.52, C.side, -0.25, 0.02);
    box(tail, 0.5, 0.12, 0.44, C.back, -0.25, 0.3);
    box(tail, 0.5, 0.16, 0.5, C.belly, -0.25, -0.2);
    box(tail, 0.45, 0.4, 0.36, C.side, -0.7, 0.04);
    box(tail, 0.45, 0.1, 0.3, C.back, -0.7, 0.24);
    box(tail, 0.38, 0.24, 0.22, C.side, -1.1, 0.05);
    const flukes = new THREE.Group();
    flukes.position.x = -1.3;
    tail.add(flukes);
    box(flukes, 0.26, 0.08, 0.5, C.fin, -0.05, 0.05);
    for (const s of [-1, 1]) {
      box(flukes, 0.3, 0.08, 0.42, C.fin, -0.18, 0.05, s * 0.4).rotation.y = s * -0.45;   // swept-back fluke tips
    }
    dolphin.scale.setScalar(0.95);
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
  const DEPTH = 1.7;   // deep enough to hide the whole (2.8 long) dolphin at the start and end of a leap
  function place(leaper, now) {
    const { spec, dolphin, tail, flukes, shadow } = leaper;
    const progress = now / LEAP_TIME + spec.delay;
    const p = ((progress % 1) + 1) % 1;                         // 0 to 1 through this leap
    const leap = Math.floor(progress);                          // which leap this is (counts up forever)
    const flipping = flips && spec.flipEvery > 0 && leap % spec.flipEvery === 0;
    const height = spec.height + (flipping ? FLIP_HEIGHT : 0);
    const x = spec.from + (spec.to - spec.from) * p;
    const arc = 4 * p * (1 - p);                                // 0 at the ends, 1 at the top
    const y = -DEPTH + (height + DEPTH) * arc;
    // nose along the direction it's moving: up out of the water, level at the top, down into it
    const slope = ((height + DEPTH) * 4 * (1 - 2 * p)) / (spec.to - spec.from);
    const surface = DEPTH / (height + DEPTH);                   // arc value where its middle crosses y = 0
    const crossOut = (1 - Math.sqrt(1 - surface)) / 2;          // the p values where 4p(1-p) = surface
    const crossIn = 1 - crossOut;
    // a flip: one full forward somersault while it's out of the water, slow at the start and end, fast in the middle
    let spin = 0;
    if (flipping) {
      const air = Math.min(1, Math.max(0, (p - crossOut) / (crossIn - crossOut)));
      spin = -Math.PI * 2 * (air * air * (3 - 2 * air));
    }
    dolphin.position.set(x, y, spec.z);
    dolphin.rotation.z = Math.atan(slope) + spin;
    tail.rotation.z = Math.sin(now * 14 + spec.delay * 9) * 0.28;   // tail beats as it swims
    flukes.rotation.x = Math.sin(now * 14 + spec.delay * 9) * 0.15;
    // shadow on the water right under it, smaller and fainter the higher it is
    const lift = Math.max(0, y);
    shadow.visible = y > -0.3;
    shadow.position.set(x, 0.005, spec.z);
    shadow.scale.set(1.2 - lift * 0.18, 0.32 - lift * 0.05, 1);
    shadow.material.opacity = 0.3 - lift * 0.05;
    // splashes: where it breaks out of the water, and where it dives back in
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
