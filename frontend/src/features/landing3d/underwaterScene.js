import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { COLORS, clipTexture, lumpyBall, makeRandom, material, pick } from "./islandScene";

// The world behind Projects: under the sea, in 3D like the Landing island, seen from the side as if you're swimming.
// Rock pillars and cave walls fade into blue haze with distance, a beam of light pours down onto a tall pillar,
// and the sea floor has sand, coral, seaweed, a treasure chest and sunken clip cards. Fish swim past.
//
// createUnderwaterScene(canvas, { still }) starts it and returns a function that stops it and frees its memory.
// In the world: +x is right, +y is up, +z comes toward you. The camera is at z = 14, looking into the scene.

const ROCK = ["#4f6584", "#5c7394", "#46597a", "#566c8e"];
const SAND = "#e9cf93";

// ---------- The water behind everything (same chunky-pixel style as the Landing sea) ----------

const WATER_VERTEX = `
  void main() {
    gl_Position = vec4(position.xy, 0.9999, 1.0);
  }
`;

const WATER_FRAGMENT = `
  uniform float uTime;
  uniform float uPixel;
  uniform vec2 uResolution;

  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
  }

  void main() {
    vec2 grid = gl_FragCoord.xy / uPixel;
    vec2 cell = floor(grid);
    vec2 uv = (cell + 0.5) * uPixel / uResolution;
    float aspect = uResolution.x / uResolution.y;
    float across = abs(uv.x - 0.53) * aspect;
    float t = uTime;

    // Deep at the bottom, bright toward the surface and the middle
    vec3 color = mix(vec3(0.05, 0.15, 0.38), vec3(0.11, 0.38, 0.72), smoothstep(0.0, 0.9, uv.y));
    float glow = exp(-across * across * 4.0) * smoothstep(0.1, 1.0, uv.y);
    color = mix(color, vec3(0.45, 0.92, 1.0), glow * 0.8 * uv.y);

    // Faint rays fanning down
    float rays = smoothstep(0.6, 1.0, sin((uv.x - 0.53) * aspect / (1.35 - uv.y) * 20.0 + sin(t * 0.3) * 1.5) * 0.5 + 0.5) * glow;
    color += vec3(0.5, 0.9, 1.0) * rays * 0.1;

    // The surface: bright pixel patches shimmering near the top
    float nearTop = smoothstep(0.82, 1.0, uv.y);
    float shimmer = noise(vec2(uv.x * aspect * 9.0 + t * 0.35, uv.y * 28.0 - t * 0.5)) * noise(vec2(uv.x * aspect * 4.0 - t * 0.2, uv.y * 11.0));
    color = mix(color, vec3(0.88, 1.0, 1.0), step(0.4 - nearTop * 0.14, shimmer) * nearTop * (0.35 + glow * 0.65));

    // Tiny specks drifting up
    vec2 drifting = floor(vec2(cell.x, cell.y - t * (2.0 + hash(vec2(cell.x, 3.0)) * 3.0)));
    color = mix(color, vec3(0.8, 0.96, 1.0), step(0.995, hash(drifting)) * 0.5);

    color = floor(color * 18.0 + 0.5) / 18.0;   // a limited palette, like pixel art
    gl_FragColor = vec4(color, 1.0);             // already screen colors: no color conversion
  }
`;

function buildWater(scene, pixelRatio) {
  const uniforms = { uTime: { value: 0 }, uPixel: { value: 5 * pixelRatio }, uResolution: { value: new THREE.Vector2(1, 1) } };
  const backdrop = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({ uniforms, vertexShader: WATER_VERTEX, fragmentShader: WATER_FRAGMENT, depthTest: false, depthWrite: false }));
  backdrop.frustumCulled = false;
  backdrop.renderOrder = -1;
  scene.add(backdrop);
  return uniforms;
}

// The beam of light pouring down onto the middle pillar: a soft glowing cone
function buildBeam(scene) {
  const beamMaterial = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
    uniforms: { uTime: { value: 0 } },
    vertexShader: `
      varying vec2 vUv;
      varying vec3 vNormalView;
      void main() {
        vUv = uv;
        vNormalView = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform float uTime;
      varying vec2 vUv;
      varying vec3 vNormalView;
      void main() {
        float facing = abs(vNormalView.z);                       // brightest through the middle of the cone
        float strength = pow(facing, 2.0) * smoothstep(0.0, 0.85, vUv.y);
        strength *= 0.75 + 0.25 * sin(vUv.x * 40.0 + uTime * 0.6);
        gl_FragColor = vec4(vec3(0.5, 0.9, 1.0) * strength * 0.22, 1.0);
      }`,
  });
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(2.6, 6.5, 34, 24, 1, true), beamMaterial);
  beam.position.set(0.6, 12, -14);
  scene.add(beam);
  return beamMaterial.uniforms.uTime;
}

// ---------- The sea floor ----------

function floorY(x, z) {
  return -0.6 + Math.sin(x * 0.35) * 0.6 + Math.cos(z * 0.4 + x * 0.2) * 0.5 + Math.sin(x * 0.9 + z * 0.7) * 0.25;
}

// Light patterns rippling across the top of the sand
function addCaustics(baseMaterial, time) {
  baseMaterial.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = time;
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vPlace;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvPlace = (modelMatrix * vec4(transformed, 1.0)).xyz;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform float uTime;\nvarying vec3 vPlace;")
      .replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
        vec2 spot = floor(vPlace.xz / 0.16) * 0.16;
        float ripple = sin(spot.x * 1.5 + uTime * 0.8 + sin(spot.y * 1.2 + uTime * 0.6) * 1.6) + sin(spot.y * 1.7 - uTime * 0.7 + sin(spot.x * 0.9 - uTime * 0.5) * 1.6);
        float light = smoothstep(0.22, 0.0, abs(ripple - 1.1)) + smoothstep(0.16, 0.0, abs(ripple + 0.6)) * 0.6;
        totalEmissiveRadiance += vec3(0.55, 0.85, 1.0) * light * 0.3;`);
  };
  return baseMaterial;
}

function buildFloor(scene, time) {
  // A bumpy sheet of sand reaching from in front of you to far away (z from +20 to -60)
  const geometry = new THREE.PlaneGeometry(110, 80, 70, 50);
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, 0, -20);
  const position = geometry.attributes.position;
  for (let i = 0; i < position.count; i += 1) {
    position.setY(i, floorY(position.getX(i), position.getZ(i)));
  }
  geometry.computeVertexNormals();
  scene.add(new THREE.Mesh(geometry, addCaustics(new THREE.MeshStandardMaterial({ color: SAND, roughness: 0.95, flatShading: true }), time)));
}

// ---------- Rock: pillars made of stacked lumpy chunks ----------

function buildRocks(scene, random) {
  const materials = ROCK.map((color) => material(color));
  function pillar(x, z, height, radius) {
    const group = new THREE.Group();
    let y = floorY(x, z) - radius * 0.3;
    while (y < floorY(x, z) + height) {
      const size = radius * (0.8 + random() * 0.4);
      const chunk = new THREE.Mesh(lumpyBall(size, random, 0.24, 1), pick(materials, random));
      chunk.scale.set(1 + random() * 0.2, 1.25 + random() * 0.3, 1 + random() * 0.2);
      chunk.position.set(x + (random() - 0.5) * radius * 0.5, y, z + (random() - 0.5) * radius * 0.4);
      group.add(chunk);
      if (random() < 0.4) {   // a side lump now and then
        const side = new THREE.Mesh(lumpyBall(size * 0.55, random, 0.22, 0), pick(materials, random));
        side.position.set(chunk.position.x + (random() < 0.5 ? -1 : 1) * size * 0.8, y + size * 0.3, chunk.position.z + size * 0.3);
        group.add(side);
      }
      y += size * 1.35;
    }
    scene.add(group);
  }
  // Cave walls framing the sides, close to you
  for (const [x, z, r] of [[-14, 5, 3.2], [-11.5, 1, 2.6], [-13, -3, 3], [14.5, 5, 3.2], [12, 0.5, 2.6], [13.5, -4, 3]]) pillar(x, z, 26, r);
  // Pillars in the middle distance
  pillar(-6.5, -7, 9, 1.8);
  pillar(7.5, -9, 12, 2);
  pillar(-10, -15, 17, 2.6);
  pillar(10.5, -19, 19, 2.6);
  // The tall one in the beam of light
  pillar(0.6, -16, 30, 2.2);
  // Far away, fading into the blue
  for (const [x, z, h, r] of [[-5, -32, 22, 3], [7, -36, 26, 3.6], [-18, -30, 26, 4], [19, -34, 24, 4], [-28, -40, 30, 5], [30, -42, 30, 5]]) pillar(x, z, h, r);
}

// ---------- Things on the sea floor ----------

function buildDecorations(scene, random, time) {
  const swaying = [];
  const placeOnFloor = (object, x, z, lift = 0) => {
    object.position.set(x, floorY(x, z) + lift, z);
    scene.add(object);
  };

  function seaweed(x, z, height, color) {
    const base = new THREE.Group();
    let parent = base;
    const segments = Math.round(height / 0.45);
    const skin = material(color, { side: THREE.DoubleSide });
    for (let i = 0; i < segments; i += 1) {
      const joint = new THREE.Group();
      joint.position.y = i === 0 ? 0 : 0.45;
      const blade = new THREE.Mesh(new THREE.BoxGeometry(0.22 * (1 - i / (segments + 2)), 0.48, 0.05), skin);
      blade.position.y = 0.22;
      joint.add(blade);
      parent.add(joint);
      swaying.push({ group: joint, amount: 0.1 + i * 0.02, speed: 0.8 + random() * 0.4, phase: random() * 6 + i * 0.4 });
      parent = joint;
    }
    placeOnFloor(base, x, z);
  }

  function coral(x, z, color, size = 1) {
    const group = new THREE.Group();
    const skin = material(color);
    const branches = 6 + Math.floor(random() * 3);
    for (let i = 0; i < branches; i += 1) {
      const height = (0.6 + random() * 0.7) * size;
      const holder = new THREE.Group();
      holder.rotation.set((random() - 0.5) * 0.9, (i / branches) * Math.PI * 2, (random() - 0.5) * 0.9);
      const branch = new THREE.Mesh(new THREE.CylinderGeometry(0.07 * size, 0.11 * size, height, 5), skin);
      branch.position.y = height / 2;
      const tip = new THREE.Mesh(new THREE.IcosahedronGeometry(0.11 * size, 0), skin);
      tip.position.y = height;
      holder.add(branch, tip);
      group.add(holder);
    }
    placeOnFloor(group, x, z);
  }

  function brainCoral(x, z, color, size) {
    const mesh = new THREE.Mesh(lumpyBall(size, random, 0.18, 1), material(color));
    mesh.scale.y = 0.7;
    placeOnFloor(mesh, x, z, size * 0.25);
  }

  function rock(x, z, size) {
    const mesh = new THREE.Mesh(lumpyBall(size, random, 0.22, 0), material(pick(ROCK, random)));
    mesh.scale.y = 0.7;
    placeOnFloor(mesh, x, z, size * 0.2);
  }

  function starfish(x, z, color) {
    const shape = new THREE.Shape();
    for (let i = 0; i < 10; i += 1) {
      const radius = i % 2 ? 0.1 : 0.28;
      const angle = (i / 10) * Math.PI * 2;
      if (i === 0) shape.moveTo(Math.cos(angle) * radius, Math.sin(angle) * radius);
      else shape.lineTo(Math.cos(angle) * radius, Math.sin(angle) * radius);
    }
    const mesh = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: 0.06, bevelEnabled: false }), material(color));
    mesh.rotation.set(-Math.PI / 2, 0, random() * 6);
    placeOnFloor(mesh, x, z, 0.05);
  }

  // Clip cards that sank to the bottom
  function sunkenClip(x, z, palette, tilt) {
    const card = new THREE.Group();
    card.add(new THREE.Mesh(new RoundedBoxGeometry(1.2, 0.12, 0.72, 2, 0.04), material(COLORS.cream, { flatShading: false })));
    const texture = clipTexture(...palette);
    const face = new THREE.Mesh(new THREE.PlaneGeometry(1.04, 0.58), new THREE.MeshStandardMaterial({ map: texture, emissiveMap: texture, emissive: "#ffffff", emissiveIntensity: 0.2, roughness: 0.6 }));
    face.rotation.x = -Math.PI / 2;
    face.position.y = 0.07;
    card.add(face);
    card.rotation.set(tilt, random() * 6, tilt * 0.6);
    placeOnFloor(card, x, z, 0.1);
  }

  // A treasure chest full of glowing gold
  const chest = new THREE.Group();
  const wood = material("#8a5328");
  const band = material("#d9a42e");
  const box = new THREE.Mesh(new RoundedBoxGeometry(1.3, 0.7, 0.85, 2, 0.06), wood);
  box.position.y = 0.35;
  chest.add(box);
  for (const x of [-0.42, 0.42]) {
    const strap = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.72, 0.87), band);
    strap.position.set(x, 0.36, 0);
    chest.add(strap);
  }
  const hinge = new THREE.Group();
  hinge.position.set(0, 0.7, -0.42);
  const lid = new THREE.Mesh(new RoundedBoxGeometry(1.3, 0.22, 0.85, 2, 0.07), wood);
  lid.position.set(0, 0.11, 0.42);
  hinge.add(lid);
  hinge.rotation.x = -0.8;
  chest.add(hinge);
  const gold = new THREE.Mesh(new THREE.IcosahedronGeometry(0.42, 0), new THREE.MeshStandardMaterial({ color: "#ffd34d", emissive: "#ffb800", emissiveIntensity: 0.7, roughness: 0.3, metalness: 0.4, flatShading: true }));
  gold.scale.set(1.3, 0.45, 0.85);
  gold.position.y = 0.72;
  chest.add(gold);
  const glow = new THREE.PointLight("#ffcf5a", 6, 6, 1.6);
  glow.position.y = 1.2;
  chest.add(glow);
  chest.rotation.y = 0.45;
  placeOnFloor(chest, -3.4, 3);

  for (const [x, z, h, c] of [[-8, 4, 3.2, "#2f9a5a"], [-7.2, 5.2, 2.4, "#3fae66"], [-2, 6.5, 2.2, "#58c172"], [5.5, 3.5, 3, "#3fae66"], [6.4, 4.8, 2.2, "#2f9a5a"], [8.6, 1, 3.6, "#58c172"], [-5, -2, 2.8, "#2f9a5a"], [3, -4, 3.2, "#3fae66"], [-1, -8, 3.6, "#58c172"], [9.5, -5, 3, "#2f9a5a"], [-9, -6, 3.4, "#3fae66"]]) {
    seaweed(x, z, h, c);
  }
  coral(-5.6, 5, "#ff7f8a", 1.3);
  coral(4, 5.5, "#ff9a3c", 1.4);
  coral(1.4, 2, "#c77dff", 1.1);
  coral(-7.5, -1.5, "#ff7f8a", 1.2);
  coral(6.8, -2.5, "#ffb43c", 1.3);
  coral(-2.5, -5, "#c77dff", 1);
  brainCoral(-0.6, 6.4, "#ff9fb0", 0.55);
  brainCoral(7.4, 6, "#c77dff", 0.5);
  brainCoral(2.8, -1.5, "#ffb86b", 0.45);
  rock(-4.6, 7.2, 0.7);
  rock(2.4, 7.6, 0.55);
  rock(5.6, 0.5, 0.6);
  rock(-8.6, 2, 0.6);
  starfish(-1.6, 5.4, "#ff8a3d");
  starfish(3.2, 4.2, "#ff5d73");
  starfish(-6.4, 7.4, "#ffcf3d");
  sunkenClip(0.4, 4.6, ["#2d6cdf", "#4fd1e0"], 0.3);
  sunkenClip(-1.6, 1.4, ["#f06a4a", "#f7b267"], -0.25);
  sunkenClip(5.2, -0.6, ["#7b4ddb", "#e36bb0"], 0.22);

  return (now) => {
    for (const item of swaying) item.group.rotation.z = Math.sin(now * item.speed + item.phase) * item.amount;
    glow.intensity = 5.4 + Math.sin(now * 2.2) * 0.8;
    time.value = now;
  };
}

// ---------- Fish, jellyfish and bubbles ----------

// One low-poly fish, facing +x: body, tail, a fin on top and two eyes
function makeFish(color, size, random) {
  const fish = new THREE.Group();
  // A little glow of their own, so their colors stay bright in the blue water
  const skin = material(color, { emissive: color, emissiveIntensity: 0.3 });
  const finColor = new THREE.Color(color).offsetHSL(0, 0, -0.12);
  const fin = material(finColor, { emissive: finColor, emissiveIntensity: 0.25 });
  const body = new THREE.Mesh(new THREE.IcosahedronGeometry(0.5, 1), skin);
  body.scale.set(1, 0.56, 0.32);
  fish.add(body);
  const tail = new THREE.Group();
  tail.position.x = -0.45;
  const tailFin = new THREE.Mesh(new THREE.ConeGeometry(0.26, 0.36, 4), fin);
  tailFin.rotation.z = Math.PI / 2;
  tailFin.scale.z = 0.25;
  tailFin.position.x = -0.14;
  tail.add(tailFin);
  fish.add(tail);
  const dorsal = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.26, 3), fin);
  dorsal.position.set(0.02, 0.3, 0);
  dorsal.rotation.z = -0.4;
  dorsal.scale.z = 0.3;
  fish.add(dorsal);
  if (random() < 0.5) {   // some fish have a stripe
    const stripe = new THREE.Mesh(new THREE.TorusGeometry(0.25, 0.05, 4, 10), material("#ffffff"));
    stripe.rotation.y = Math.PI / 2;
    stripe.scale.set(1, 1.05, 0.62);
    stripe.position.x = 0.08;
    fish.add(stripe);
  }
  for (const side of [-1, 1]) {
    const eye = new THREE.Mesh(new THREE.IcosahedronGeometry(0.07, 0), material("#ffffff"));
    eye.position.set(0.3, 0.06, side * 0.13);
    const pupil = new THREE.Mesh(new THREE.IcosahedronGeometry(0.04, 0), material("#14213d"));
    pupil.position.set(0.33, 0.06, side * 0.17);
    fish.add(eye, pupil);
  }
  fish.scale.setScalar(size);
  return { fish, tail };
}

function buildFish(scene, random) {
  // Schools swim across the view at different depths and speeds, then loop back around
  const schools = [
    { color: "#ff8a3d", count: 7, y: 4.4, z: 0, speed: 1.4, direction: 1, size: 1 },
    { color: "#ffd34d", count: 6, y: 7, z: -5, speed: 1, direction: -1, size: 0.95 },
    { color: "#4fd1e0", count: 9, y: 2.6, z: 3, speed: 1.8, direction: 1, size: 0.7 },
    { color: "#ff5d73", count: 5, y: 9, z: -9, speed: 0.8, direction: 1, size: 1 },
    { color: "#2d6cdf", count: 1, y: 5.6, z: 5, speed: 0.9, direction: -1, size: 2.2 },   // one big fish
    { color: "#9be15d", count: 4, y: 3.4, z: -3, speed: 1.2, direction: -1, size: 0.85 },
  ];
  const swimmers = [];
  schools.forEach((school, index) => {
    for (let i = 0; i < school.count; i += 1) {
      const { fish, tail } = makeFish(school.color, school.size, random);
      scene.add(fish);
      swimmers.push({
        fish, tail, school,
        start: (index / schools.length) * 36,   // spread out, so some fish are always in view
        dx: (random() - 0.5) * 3 * Math.min(1, school.count / 3),
        dy: (random() - 0.5) * 1.2,
        dz: (random() - 0.5) * 1.6,
        phase: random() * 6,
      });
    }
  });
  const SPAN = 36;   // how far a school swims before looping back (the view is about 28 wide)
  return (now) => {
    for (const item of swimmers) {
      const { school } = item;
      const travel = ((now * school.speed + item.start) % SPAN) - SPAN / 2;   // -18 to 18
      item.fish.position.set(travel * school.direction + item.dx, school.y + item.dy + Math.sin(now * 1.1 + item.phase) * 0.25, school.z + item.dz + Math.sin(now * 0.6 + item.phase) * 0.3);
      item.fish.rotation.y = (school.direction > 0 ? 0 : Math.PI) + Math.sin(now * 1.3 + item.phase) * 0.12;
      item.tail.rotation.y = Math.sin(now * 10 + item.phase) * 0.45;
    }
  };
}

function buildJellyfish(scene, random) {
  const jellies = [["#ff9fd0", 6, 8, -6], ["#c9a7ff", -6.5, 9, -10], ["#9fe8ff", 3, 11, -20]].map(([color, x, height, z]) => {
    const group = new THREE.Group();
    const skin = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.4, transparent: true, opacity: 0.82, roughness: 0.4, flatShading: true });
    group.add(new THREE.Mesh(new THREE.SphereGeometry(0.55, 9, 5, 0, Math.PI * 2, 0, Math.PI / 2), skin));
    const tentacles = [];
    for (let i = 0; i < 7; i += 1) {
      const angle = (i / 7) * Math.PI * 2;
      const holder = new THREE.Group();
      holder.position.set(Math.cos(angle) * 0.32, 0, Math.sin(angle) * 0.32);
      const strand = new THREE.Mesh(new THREE.BoxGeometry(0.05, 1 + random() * 0.5, 0.05), skin);
      strand.position.y = -0.6;
      holder.add(strand);
      group.add(holder);
      tentacles.push(holder);
    }
    group.position.set(x, height, z);
    scene.add(group);
    return { group, tentacles, height, phase: random() * 6 };
  });
  return (now) => {
    for (const jelly of jellies) {
      const pulse = Math.sin(now * 1.6 + jelly.phase);
      jelly.group.position.y = jelly.height + Math.sin(now * 0.5 + jelly.phase) * 0.7;
      jelly.group.scale.set(1 + pulse * 0.08, 1 - pulse * 0.08, 1 + pulse * 0.08);
      jelly.tentacles.forEach((tentacle, i) => { tentacle.rotation.z = Math.sin(now * 2 + i + jelly.phase) * 0.25; });
    }
  };
}

function buildBubbles(scene, random) {
  const sources = [[-3.4, 3], [-8, 4], [8.6, 1], [-1, -8], [5.5, 3.5], [-5, -2]];
  const COUNT = 50;
  const bubbles = [];
  for (let i = 0; i < COUNT; i += 1) {
    const [x, z] = sources[i % sources.length];
    bubbles.push({ x: x + (random() - 0.5) * 0.6, z: z + (random() - 0.5) * 0.6, start: random(), speed: 0.05 + random() * 0.05, size: 0.06 + random() * 0.08, phase: random() * 6 });
  }
  const mesh = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 1), new THREE.MeshStandardMaterial({ color: "#e8fbff", emissive: "#bfefff", emissiveIntensity: 0.45, transparent: true, opacity: 0.75, roughness: 0.1 }), COUNT);
  scene.add(mesh);
  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3();
  const rotation = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  return (now) => {
    bubbles.forEach((bubble, i) => {
      const rise = (bubble.start + now * bubble.speed) % 1;
      position.set(bubble.x + Math.sin(now * 2 + bubble.phase) * 0.15, floorY(bubble.x, bubble.z) + rise * 20, bubble.z);
      scale.setScalar(bubble.size * (0.6 + rise * 0.9));
      matrix.compose(position, rotation, scale);
      mesh.setMatrixAt(i, matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  };
}

// ---------- Putting it together ----------

export function createUnderwaterScene(canvas, { still = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog("#1f63ad", 10, 52);   // far rock fades into the blue, like layers in the distance
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 120);
  const lookAt = new THREE.Vector3(0, 5, -6);

  scene.add(new THREE.HemisphereLight("#bfefff", "#1b4f7a", 1.9));
  const sun = new THREE.DirectionalLight("#dff6ff", 1.8);
  sun.position.set(2, 20, 4);
  scene.add(sun);

  const random = makeRandom(20261108);
  const water = buildWater(scene, renderer.getPixelRatio());
  const beamTime = buildBeam(scene);
  const causticsTime = { value: 0 };
  buildFloor(scene, causticsTime);
  buildRocks(scene, random);
  const updates = [
    buildDecorations(scene, random, causticsTime),
    buildFish(scene, random),
    buildJellyfish(scene, random),
    buildBubbles(scene, random),
  ];

  function fit() {
    const parent = canvas.parentElement;
    const width = parent.clientWidth;
    const height = parent.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    water.uResolution.value.set(width * renderer.getPixelRatio(), height * renderer.getPixelRatio());
    camera.aspect = width / height;
    camera.fov = camera.aspect < 1 ? 70 : 50;   // phones: see a bit more
    camera.updateProjectionMatrix();
    draw();
  }

  // The view drifts gently, and leans a little toward the mouse
  const mouse = { x: 0, y: 0, smoothX: 0, smoothY: 0 };
  function handleMouse(event) {
    mouse.x = (event.clientX / window.innerWidth - 0.5) * 2;
    mouse.y = (event.clientY / window.innerHeight - 0.5) * 2;
  }

  // Camera moves: "arrive" sinks down from just under the surface (right after the dive from Landing),
  // "forward" pushes into the beam of light (when you open a project). See components/LeafTransition.jsx.
  const ease = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
  const arrivedAt = window.cascadeCameraArrive;
  let arrive = !still && arrivedAt && performance.now() - arrivedAt < 2500 ? { start: performance.now(), duration: 1800 } : null;
  let forward = null;
  function handleCamera(event) {
    if (event.detail?.move === "forward" && !still) forward = { start: performance.now(), duration: event.detail.duration ?? 800 };
  }

  let frame = 0;
  const startTime = performance.now();
  function draw() {
    const now = still ? 7 : (performance.now() - startTime) / 1000 + 7;
    water.uTime.value = now;
    beamTime.value = now;
    for (const update of updates) update(now);
    mouse.smoothX += (mouse.x - mouse.smoothX) * 0.04;
    mouse.smoothY += (mouse.y - mouse.smoothY) * 0.04;
    camera.position.set(mouse.smoothX * 1.2 + Math.sin(now * 0.15) * 0.4, 3 - mouse.smoothY * 0.5 + Math.sin(now * 0.2) * 0.2, 14);
    const target = lookAt.clone();
    if (arrive) {
      const p = Math.min(1, (performance.now() - arrive.start) / arrive.duration);
      const settled = 1 - Math.pow(1 - p, 3);   // fast at first, settling gently
      camera.position.y += (22 - camera.position.y) * (1 - settled);
      camera.position.z += (9 - camera.position.z) * (1 - settled);
      target.y += (13 - target.y) * (1 - settled);
      if (p >= 1) arrive = null;
    }
    if (forward) {
      const pushed = ease(Math.min(1, (performance.now() - forward.start) / forward.duration));
      camera.position.z += (0 - camera.position.z) * pushed;
      camera.position.y += (6 - camera.position.y) * pushed;
      target.y += (8 - target.y) * pushed;
    }
    camera.lookAt(target);
    renderer.render(scene, camera);
  }
  function loop() {
    draw();
    frame = requestAnimationFrame(loop);
  }

  const observer = new ResizeObserver(fit);
  observer.observe(canvas.parentElement);
  fit();
  if (!still) {
    window.addEventListener("pointermove", handleMouse);
    window.addEventListener("cascade:camera", handleCamera);
    frame = requestAnimationFrame(loop);
  }

  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("pointermove", handleMouse);
    window.removeEventListener("cascade:camera", handleCamera);
    observer.disconnect();
    const seen = new Set();
    const free = (thing) => { if (thing && !seen.has(thing)) { seen.add(thing); thing.dispose?.(); } };
    scene.traverse((object) => {
      free(object.geometry);
      for (const item of [object.material].flat()) {
        if (!item) continue;
        free(item.map);
        free(item.emissiveMap);
        free(item);
      }
    });
    renderer.dispose();
    renderer.forceContextLoss();
  };
}
