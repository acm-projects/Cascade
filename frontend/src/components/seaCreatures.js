import * as THREE from "three";

// The animals in the WaterFlow background, built like Minecraft's sea mobs out of boxes and lit from the surface:
// clownfish (orange, white bands), yellow-and-blue tropical fish, cod schools, turtles paddling with four flippers,
// dolphins beating their tails, squid pulsing their tentacles upward, and a glow squid. Fog fades the distant ones
// into dark shapes against the light, like the reference footage.
//
// createCreatures(canvas) draws on a transparent WebGL canvas laid over the water. It returns
// { resize(width, height), frame(seconds, dt, depth), dispose() } and throws if WebGL isn't available.

const FOV = 50;
const CAM_Z = 18;
const LOOK_Y = 1.5;
const TAN = Math.tan((FOV / 2) * (Math.PI / 180));

const C = {
  orange: 0xe8742a, white: 0xf4f1ea, black: 0x15181d,
  yellow: 0xe6c23c, blue: 0x2f5fb8,
  cod: 0xa3916f, codDark: 0x7a6a4f, codLight: 0xcbbf9f,
  shell: 0x2d5a2a, shellLight: 0x3f7a36, skin: 0x7d9f4a, belly: 0xc2b27a,
  dolphin: 0x6f879c, dolphinDark: 0x56697b, dolphinBelly: 0xb5c3cf,
  squid: 0x1d3150, squidLight: 0x2b4670, squidEye: 0xd9e2ec,
  glow: 0x168a83, glowLight: 0x4ff0d6, glowEye: 0xeafffb,
};

// Who swims. z = distance range (more negative = farther), band = where on screen, speed in units per second,
// rest = seconds to wait off-screen before coming back, school = how many swim together.
const CAST = [
  { kind: "cod", school: 12, z: [-38, -30], band: "high", speed: 2.4, spread: [5, 2, 3] },
  { kind: "cod", school: 9, z: [-28, -20], band: "any", speed: 2.8, spread: [4, 1.6, 2.5] },
  { kind: "squid", z: [-30, -22], band: "high", speed: 0.7, swim: "up" },
  { kind: "squid", z: [-24, -16], band: "high", speed: 0.6, swim: "up" },
  { kind: "squid", z: [-20, -12], band: "any", speed: 0.55, swim: "up" },
  { kind: "dolphin", school: 2, z: [-24, -16], band: "high", speed: 3.6, spread: [4, 1.2, 2], rest: [10, 30], scale: 1.2 },
  { kind: "turtle", z: [-22, -16], band: "high", speed: 0.8, rest: [8, 20], scale: 1.1 },
  { kind: "turtle", z: [-12, -6], band: "any", speed: 0.9, rest: [4, 12], scale: 1.1 },
  { kind: "tropical", z: [-14, -8], band: "any", speed: 1.8 },
  { kind: "tropical", school: 2, z: [-8, -2], band: "any", speed: 1.6, spread: [2, 1, 1] },
  { kind: "clown", school: 2, z: [-12, -6], band: "low", speed: 1.4, spread: [2, 1, 1] },
  { kind: "clown", school: 4, z: [-4, 2], band: "low", speed: 1.5, spread: [3, 1.4, 1.5] },
  { kind: "glow", z: [-10, -4], band: "low", speed: 0.5, swim: "up" },
];

const between = ([low, high]) => low + Math.random() * (high - low);

export function createCreatures(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "low-power" });
  renderer.setPixelRatio(1);   // WaterFlow sizes the canvas itself (lower than the screen, for blocky edges)
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const fogNear = new THREE.Color(0x0a2c50);
  const fogDeep = new THREE.Color(0x03111f);
  scene.fog = new THREE.Fog(fogNear.clone(), 12, 62);
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.5, 140);
  camera.position.set(0, 0, CAM_Z);
  camera.lookAt(0, LOOK_Y, 0);
  const sky = new THREE.HemisphereLight(0xa8dcff, 0x0a1a2e, 1.7);
  const sun = new THREE.DirectionalLight(0xd8f3ff, 1.3);
  sun.position.set(2, 10, 4);
  const fill = new THREE.AmbientLight(0x9fd0ff, 0.9);   // light bounced around in the water, so colors read up close
  scene.add(sky, sun, fill);

  // shared boxes and colors, so many animals cost little
  const geometries = new Map();
  const materials = new Map();
  const glowing = [];
  const geo = (w, h, d) => {
    const key = `${w}|${h}|${d}`;
    if (!geometries.has(key)) geometries.set(key, new THREE.BoxGeometry(w, h, d));
    return geometries.get(key);
  };
  const mat = (color, glow = false) => {
    const key = `${color}|${glow}`;
    if (!materials.has(key)) {
      const material = new THREE.MeshLambertMaterial({ color, emissive: glow ? color : 0x000000, emissiveIntensity: 0 });
      if (glow) glowing.push(material);
      materials.set(key, material);
    }
    return materials.get(key);
  };
  const box = (parent, w, h, d, color, x = 0, y = 0, z = 0, glow = false) => {
    const mesh = new THREE.Mesh(geo(w, h, d), mat(color, glow));
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  };

  // ---------- The animals (each faces +x) ----------

  function fish(kind) {
    const group = new THREE.Group();
    const { L, H, W } = { clown: { L: 0.9, H: 0.55, W: 0.32 }, tropical: { L: 0.75, H: 0.7, W: 0.28 }, cod: { L: 1.0, H: 0.42, W: 0.3 } }[kind];
    let tailColor;
    if (kind === "clown") {
      box(group, L, H, W, C.orange);
      for (const x of [L * 0.2, -L * 0.17]) {
        box(group, 0.13, H + 0.02, W + 0.02, C.white, x);
        box(group, 0.03, H + 0.03, W + 0.03, C.black, x + 0.08);
        box(group, 0.03, H + 0.03, W + 0.03, C.black, x - 0.08);
      }
      box(group, L * 0.45, 0.16, 0.05, C.orange, -0.05, H / 2 + 0.08);
      tailColor = C.orange;
    } else if (kind === "tropical") {
      box(group, L, H, W, C.yellow);
      box(group, L * 0.75, H * 0.42, W + 0.02, C.blue, 0.02, H * 0.2);
      box(group, L * 0.55, 0.26, 0.05, C.yellow, -0.05, H / 2 + 0.13);
      box(group, L * 0.4, 0.18, 0.05, C.yellow, -0.05, -H / 2 - 0.09);
      tailColor = C.yellow;
    } else {
      box(group, L, H, W, C.cod);
      box(group, L * 0.9, H * 0.3, W + 0.02, C.codDark, 0, H * 0.3);
      box(group, L * 0.8, H * 0.24, W + 0.02, C.codLight, 0.05, -H * 0.32);
      box(group, L * 0.35, 0.14, 0.05, C.codDark, 0, H / 2 + 0.07);
      tailColor = C.codDark;
    }
    box(group, 0.08, 0.08, W + 0.04, C.black, L * 0.36, H * 0.12);   // eyes, one each side
    const tail = new THREE.Group();
    tail.position.x = -L / 2;
    group.add(tail);
    box(tail, 0.32, H * 0.9, 0.05, tailColor, -0.16);
    if (kind === "clown") box(tail, 0.05, H * 0.9 + 0.01, 0.06, C.black, -0.3);
    return { group, animate: (t, phase) => { tail.rotation.y = Math.sin(t * 9 + phase) * 0.5; } };
  }

  function squid(glow) {
    const group = new THREE.Group();
    const body = glow ? C.glow : C.squid;
    const light = glow ? C.glowLight : C.squidLight;
    box(group, 0.9, 1.3, 0.9, body, 0, 0.65, 0, glow);
    box(group, 0.94, 0.3, 0.94, light, 0, 1.15, 0, glow);
    box(group, 0.2, 0.14, 0.94, glow ? C.glowEye : C.squidEye, 0.18, 0.4, 0, glow);   // eyes, both sides
    if (glow) {
      box(group, 0.92, 0.1, 0.12, C.glowLight, -0.1, 0.8, 0, true);
      box(group, 0.12, 0.1, 0.92, C.glowLight, -0.25, 0.6, 0, true);
    }
    const tentacles = [];
    for (let i = 0; i < 8; i += 1) {
      const angle = (i / 8) * Math.PI * 2;
      const pivot = new THREE.Group();
      pivot.position.set(Math.cos(angle) * 0.33, 0, Math.sin(angle) * 0.33);
      group.add(pivot);
      box(pivot, 0.14, 1.15, 0.14, i % 2 ? body : light, 0, -0.57, 0, glow);
      tentacles.push({ pivot, angle });
    }
    return {
      group,
      animate: (t, phase) => {
        // squeeze in, then spread out: the swimming pulse
        const lean = 0.12 + 0.38 * (0.5 + 0.5 * Math.sin(t * 2.2 + phase));
        for (const { pivot, angle } of tentacles) {
          pivot.rotation.z = -Math.cos(angle) * lean;
          pivot.rotation.x = Math.sin(angle) * lean;
        }
      },
      pulse: (t, phase) => 0.5 + 0.5 * Math.sin(t * 2.2 + phase - 1.2),
    };
  }

  function turtle() {
    const group = new THREE.Group();
    const inner = new THREE.Group();
    inner.rotation.x = 0.45;   // tipped a little toward the camera, so the flippers show as it paddles
    group.add(inner);
    box(inner, 2.0, 0.45, 1.6, C.shell);
    box(inner, 1.6, 0.25, 1.3, C.shellLight, 0, 0.33);
    box(inner, 1.0, 0.16, 0.8, C.shell, -0.05, 0.5);
    box(inner, 1.8, 0.12, 1.4, C.belly, 0, -0.27);
    box(inner, 0.62, 0.45, 0.52, C.skin, 1.25, 0.05);
    box(inner, 0.1, 0.1, 0.54, C.black, 1.42, 0.13);
    box(inner, 0.3, 0.14, 0.2, C.skin, -1.1, -0.05);
    const flippers = [];
    for (const side of [1, -1]) {
      const front = new THREE.Group();
      front.position.set(0.55, -0.05, side * 0.8);
      box(front, 0.55, 0.08, 1.05, C.skin, 0, 0, side * 0.52);
      const back = new THREE.Group();
      back.position.set(-0.75, -0.05, side * 0.7);
      box(back, 0.42, 0.08, 0.6, C.skin, 0, 0, side * 0.3);
      inner.add(front, back);
      flippers.push({ front, back, side });
    }
    return {
      group,
      animate: (t, phase) => {
        const stroke = Math.sin(t * 1.8 + phase);
        for (const { front, back, side } of flippers) {
          front.rotation.x = side * stroke * 0.6;
          front.rotation.y = side * stroke * 0.3;
          back.rotation.x = -side * stroke * 0.35;
        }
      },
    };
  }

  function dolphin() {
    const group = new THREE.Group();
    box(group, 2.2, 0.8, 0.8, C.dolphin);
    box(group, 1.8, 0.24, 0.82, C.dolphinBelly, 0.1, -0.3);
    box(group, 0.7, 0.7, 0.7, C.dolphin, 1.42, 0.02);
    box(group, 0.55, 0.22, 0.3, C.dolphinBelly, 1.98, -0.15);
    box(group, 0.08, 0.08, 0.72, C.black, 1.58, 0.16);
    box(group, 0.5, 0.45, 0.1, C.dolphinDark, -0.15, 0.55).rotation.z = -0.45;
    box(group, 0.5, 0.08, 0.4, C.dolphinDark, 0.55, -0.32, 0.55).rotation.y = 0.5;
    box(group, 0.5, 0.08, 0.4, C.dolphinDark, 0.55, -0.32, -0.55).rotation.y = -0.5;
    const tail = new THREE.Group();
    tail.position.x = -1.1;
    group.add(tail);
    box(tail, 0.9, 0.45, 0.45, C.dolphin, -0.45);
    box(tail, 0.35, 0.08, 1.3, C.dolphinDark, -1.0);
    return { group, animate: (t, phase) => { tail.rotation.z = Math.sin(t * 4 + phase) * 0.35; } };
  }

  const MAKERS = {
    clown: () => fish("clown"), tropical: () => fish("tropical"), cod: () => fish("cod"),
    squid: () => squid(false), glow: () => squid(true), turtle, dolphin,
  };

  // ---------- Swimming ----------

  let aspect = 1;
  const view = (z) => {
    const halfH = (CAM_Z - z) * TAN;
    return { halfW: halfH * aspect, halfH, centerY: (LOOK_Y * (CAM_Z - z)) / CAM_Z };
  };

  const actors = CAST.map((spec) => {
    const root = new THREE.Group();
    root.scale.setScalar(spec.scale ?? 1);
    scene.add(root);
    const members = Array.from({ length: spec.school ?? 1 }, (_, i) => {
      const made = MAKERS[spec.kind]();
      const [sx, sy, sz] = spec.spread ?? [0, 0, 0];
      const offset = i === 0 ? new THREE.Vector3() : new THREE.Vector3(between([-sx, sx]), between([-sy, sy]), between([-sz, sz]));
      made.group.position.copy(offset);
      root.add(made.group);
      return { ...made, offset, phase: Math.random() * 10 };
    });
    return { spec, root, members, phase: Math.random() * 10, rest: 0, dir: 1, speed: 1 };
  });

  const place = (actor, anywhere) => {
    const { spec, root } = actor;
    const z = between(spec.z);
    const { halfW, halfH, centerY } = view(z);
    const band = { high: [0.2, 0.85], low: [-0.75, 0], any: [-0.65, 0.8] }[spec.band];
    actor.dir = Math.random() < 0.5 ? 1 : -1;
    actor.speed = spec.speed * between([0.8, 1.2]);
    actor.rest = anywhere || !spec.rest ? 0 : between(spec.rest);
    const margin = 4 * (spec.scale ?? 1);
    let x = anywhere ? between([-halfW, halfW]) : -actor.dir * (halfW + margin);
    let y = centerY + halfH * between(band);
    if (spec.swim === "up" && !anywhere) {   // squid rise in from below
      x = between([-halfW * 0.9, halfW * 0.9]);
      y = centerY - halfH - 3;
    }
    root.position.set(x, y, z);
    root.visible = actor.rest <= 0;
  };

  let started = false;
  const resize = (width, height) => {
    renderer.setSize(width, height, false);
    aspect = width / height;
    camera.aspect = aspect;
    camera.updateProjectionMatrix();
    if (!started) {
      actors.forEach((actor) => place(actor, true));
      started = true;
    }
  };

  const frame = (t, dt, depth) => {
    scene.fog.color.copy(fogNear).lerp(fogDeep, depth);
    sky.intensity = 1.7 - depth * 1.1;
    sun.intensity = 1.3 - depth * 1.0;
    fill.intensity = 0.9 - depth * 0.6;
    for (const material of glowing) material.emissiveIntensity = 0.35 + depth * 1.4;

    for (const actor of actors) {
      const { spec, root, members } = actor;
      if (actor.rest > 0) {
        actor.rest -= dt;
        root.visible = actor.rest <= 0;
        continue;
      }
      const { halfW, halfH, centerY } = view(root.position.z);
      const margin = 4 * (spec.scale ?? 1);
      if (spec.swim === "up") {
        const push = members[0].pulse(t, actor.phase);
        root.position.x += actor.dir * actor.speed * 0.45 * push * dt;
        root.position.y += actor.speed * (0.3 + push) * dt;
        root.rotation.z = -actor.dir * 0.35;   // leaning into the direction it's swimming
        if (root.position.y > centerY + halfH + 3 || Math.abs(root.position.x) > halfW + margin) place(actor, false);
      } else {
        root.position.x += actor.dir * actor.speed * dt;
        root.rotation.y = actor.dir > 0 ? 0 : Math.PI;
        // dolphins rise and dive in long curves, nose first; everyone else just drifts a little
        const dive = spec.kind === "dolphin" ? Math.sin(t * 0.7 + actor.phase) : 0;
        root.rotation.z = dive * 0.18;
        root.position.y += (Math.sin(t * 0.8 + actor.phase) * 0.15 + dive * 0.5) * dt;
        if (Math.abs(root.position.x) > halfW + margin) place(actor, false);
      }
      for (const member of members) {
        member.animate(t, member.phase);
        member.group.position.y = member.offset.y + Math.sin(t * 1.3 + member.phase) * 0.12;
        if (spec.swim !== "up") member.group.rotation.y = Math.sin(t * 2 + member.phase) * 0.08;
      }
    }
    renderer.render(scene, camera);
  };

  const dispose = () => {
    geometries.forEach((g) => g.dispose());
    materials.forEach((m) => m.dispose());
    renderer.dispose();
    renderer.forceContextLoss();
  };

  return { resize, frame, dispose };
}
