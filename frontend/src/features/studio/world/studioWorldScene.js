import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";
import {
  COLORS, SEA_FRAGMENT, SEA_VERTEX, clipTexture, leafShape, lumpyBall, makeRandom, material, pick, waterTexture,
} from "../../landing3d/islandScene";

// AI Studio as a little isometric world, built the same way as the Landing island: a jungle island of voxel
// columns (grass, a band of dirt, dark rock) sitting in the chunky pixel sea. The land steps down in terraces
// from left to right. Your video is a tall cliff with a waterfall pouring down three ledges; rivers carry the
// water to a lily pad for each prompt and on to a platform for each clip, dropping in waterfalls wherever the
// land steps down. Picking a clip raises a green flag on its platform. Little clip cards float down the rivers.
// The cards you click (preview, title, Pick clip) are normal HTML drawn on top by StudioWorld.jsx; this file
// tells it where each card belongs on screen.
//
// Controls: drag to turn the island around (it glides a little after you let go, like a 3D splat viewer),
// right-drag / Shift + drag / two-finger scroll to move, pinch or Ctrl + scroll to zoom.
//
// createStudioWorld(canvas, { still, onFrame }) returns
//   setGraph({ nodes, edges }) - nodes: [{ id, type: "source" | "generation" | "clip", x, z, picked, busy }]
//                                edges: [{ id, source, target, busy }]   (x / z in world units on the ground)
//   zoomBy(factor), fit() (also resets the angle), stop()
//   onFrame(spots, scale) - every frame: spots = { [id]: { x, y } } in canvas pixels, scale = pixels per world unit
// In the world: +y is up, the flow runs along +x (it steps down that way), clips of a prompt line up along +z.

const SEA = -0.6;          // the sea's surface
const LOW = 0.6;           // the top of the lowest terrace
const STEP = 1.2;          // how much each terrace steps down
const VIEW_HEIGHT = 18;    // world units shown top to bottom at zoom 1
const START_AZIMUTH = Math.PI / 4;                    // around the island (0 = from +z)
const START_ELEVATION = Math.atan2(1.2, Math.SQRT2);  // up from the ground (about 40°)
const MIN_ELEVATION = 0.22;
const MAX_ELEVATION = 1.4;
const LIFT = { source: 6.6, generation: 0.7, clip: 1.4 };   // how high above the ground each card sits
const UP = new THREE.Vector3(0, 1, 0);
const CLIFF = [[-2.2, 4.6], [-0.9, 3.2], [0.4, 1.8]];         // the video cliff's steps: [front edge x, height]
const RIVER_WIDTH = 1.15;
const RISE_DEPTH = 4.5;      // new land starts this far under the sea...
const RISE_SECONDS = 1.9;    // ...and rises up over this long

// The island's pieces (trees, palms, ferns, rocks, the waterfall cliff, pond rims, the clip platform, the dock)
// are made in Blender: frontend/blender/studio_kit.py builds them into public/models/studio_kit.glb. They're
// downloaded once, then copied wherever they're needed. If the kit can't load, the code draws simpler versions.
const KIT_URL = "/models/studio_kit.glb";
let kitPromise = null;
function loadKit() {
  if (!kitPromise) {
    const draco = new DRACOLoader().setDecoderPath("/draco/");
    kitPromise = new GLTFLoader().setDRACOLoader(draco).loadAsync(KIT_URL).finally(() => draco.dispose());
    kitPromise.catch(() => { kitPromise = null; });
  }
  return kitPromise;
}

// The water's waves move with this clock (set every frame in draw)
const waveTime = { value: 0 };

// waves: how tall the rolling waves are (0 = still). Wavy water is faceted, like low-poly water,
// so each little wave catches the light.
function waterMaterial(map, waves = 0) {
  const water = new THREE.MeshStandardMaterial({
    map, roughness: 0.22, metalness: 0.08, emissive: "#0b6f86", emissiveIntensity: 0.26,
    side: THREE.DoubleSide, flatShading: waves > 0,
  });
  if (waves > 0) {
    water.onBeforeCompile = (shader) => {
      shader.uniforms.uWaveTime = waveTime;
      shader.vertexShader = "uniform float uWaveTime;\n" + shader.vertexShader.replace("#include <begin_vertex>", `#include <begin_vertex>
        vec4 placeInWorld = modelMatrix * vec4(position, 1.0);
        float wave = (sin(placeInWorld.x * 2.3 + uWaveTime * 2.1) * 0.5
          + sin(placeInWorld.z * 3.1 - uWaveTime * 1.7) * 0.35
          + sin((placeInWorld.x + placeInWorld.z) * 5.0 + uWaveTime * 3.0) * 0.15) * ${waves.toFixed(3)};
        transformed += (vec4(0.0, wave, 0.0, 0.0) * modelMatrix).xyz;   // straight up in the world, however the water is turned`);
    };
  }
  return water;
}

// A flat-topped disc of water with rings of points inside, so it can ripple
function waterDisc(radius) {
  return new THREE.RingGeometry(0.001, radius, 28, 6).rotateX(-Math.PI / 2);
}

// A sheet of falling water that isn't flat: it shoots out from the lip and curves down, and bulges in the
// middle. Its top is at y = 0 and it hangs down to -drop; +z is out from the cliff.
function fallGeometry(width, drop, reach = 0.32) {
  const geometry = new THREE.PlaneGeometry(width, drop, 8, Math.max(4, Math.round(drop * 5)));
  geometry.translate(0, -drop / 2, 0);
  const position = geometry.attributes.position;
  for (let i = 0; i < position.count; i += 1) {
    const across = position.getX(i) / (width / 2);
    const down = -position.getY(i) / drop;   // 0 at the lip, 1 at the bottom
    const bulge = (1 - across * across) * 0.12;
    position.setZ(i, reach * Math.sqrt(down) + bulge + Math.sin(across * 5 + down * 3) * 0.025);
  }
  geometry.computeVertexNormals();
  return geometry;
}

// Many copies of one small shape in one draw: items [{ x, y, z, ry, s, sy, color }]
function instances(group, geometry, items, shadows = false) {
  if (!items.length) return;
  const mesh = new THREE.InstancedMesh(geometry, material("#ffffff"), items.length);
  const matrix = new THREE.Matrix4();
  const quaternion = new THREE.Quaternion();
  const position = new THREE.Vector3();
  const scale = new THREE.Vector3();
  const color = new THREE.Color();
  items.forEach((item, i) => {
    quaternion.setFromAxisAngle(UP, item.ry ?? 0);
    matrix.compose(position.set(item.x, item.y, item.z), quaternion, scale.set(item.s ?? 1, item.sy ?? item.s ?? 1, item.s ?? 1));
    mesh.setMatrixAt(i, matrix);
    mesh.setColorAt(i, color.set(item.color));
  });
  mesh.castShadow = shadows;
  mesh.receiveShadow = true;
  group.add(mesh);
}

export function createStudioWorld(canvas, { still = false, onFrame = () => {} } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -200, 400);

  scene.add(new THREE.HemisphereLight("#fff6e0", "#3e6b45", 1.7));
  const sun = new THREE.DirectionalLight("#fff1d6", 2.3);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0006;
  scene.add(sun, sun.target);

  const flowing = [];   // water textures and how fast they scroll
  const flow = (texture, speed) => { flowing.push({ texture, speed }); return texture; };

  let world = null;          // everything built for the current graph
  let spots = [];            // [{ id, point }] where each card sits, in the world
  const movers = [];         // per-frame updates for the current graph
  let bounds = new THREE.Box3(new THREE.Vector3(-5, 0, -5), new THREE.Vector3(5, 0, 5));
  let lastKey = "";
  let kit = null;            // the Blender pieces, by name ("TreeRound", "Cliff", ...), once downloaded
  let kitDone = false;       // the download finished (or failed)
  let waiting = null;        // a graph that arrived before the kit; it's built once the kit is ready
  // What's already on the island, so only new land (and new pads, clips and rivers) rises out of the sea
  let knownTiles = new Set();
  let knownNodes = new Set();
  let knownEdges = new Set();
  let rising = null;     // { group, start } while new land is rising
  let splash = null;     // { group, start, rings, puffs } the foam where it breaks the surface

  function clear() {
    if (!world) return;
    scene.remove(world);
    world.traverse((object) => {
      if (object.userData.fromKit) return;   // shared with the Blender kit, which is reused
      object.geometry?.dispose();
      const list = [object.material].flat().filter(Boolean);
      for (const item of list) {
        item.map?.dispose();
        item.uniforms?.uShore?.value?.dispose();
        item.dispose?.();
      }
    });
    world = null;
    movers.length = 0;
    flowing.length = 0;
  }

  // A copy of a Blender piece, standing at `at`, turned and sized. Parts marked "sway" in Blender sway here.
  function place(name, group, at, turn = 0, size = 1) {
    const source = kit?.get(name);
    if (!source) return null;
    const copy = source.clone(true);
    copy.position.copy(at);
    copy.rotation.y = turn;
    copy.scale.setScalar(size);
    copy.traverse((object) => {
      if (object.isMesh) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
      if (object.userData.sway) {
        const baseX = object.rotation.x;
        const baseZ = object.rotation.z;
        const amount = object.userData.sway;
        const speed = object.userData.speed ?? 1;
        const phase = at.x * 1.7 + at.z * 0.9;
        movers.push((time) => {
          object.rotation.x = baseX + Math.sin(time * speed + phase) * amount;
          object.rotation.z = baseZ + Math.cos(time * speed * 0.8 + phase) * amount;
        });
      }
    });
    group.add(copy);
    return copy;
  }

  // ---------- The land: terraces of voxel columns, and the sea around them ----------

  // groupFor(x, z): where a tile (and everything on it) goes - the rising group if it's new land, else the world.
  // Every tile gets its own random numbers (from its position), so a tile's plants stay the same each time
  // the island is rebuilt: old land never reshuffles when new land arrives.
  function buildLand(box, heightAt, keepClear, groupFor) {
    const center = box.getCenter(new THREE.Vector3());
    const half = box.getSize(new THREE.Vector3()).multiplyScalar(0.5).addScalar(1.5);
    const wobble = (x, z) => Math.sin(x * 1.3 + z * 0.7) * 0.45 + Math.cos(z * 1.7 - x * 0.5) * 0.4;
    const isLand = (x, z) => {
      const outX = Math.max(Math.abs(x - center.x) - half.x, 0);
      const outZ = Math.max(Math.abs(z - center.z) - half.z, 0);
      return Math.hypot(outX, outZ) <= 1.6 + wobble(x, z) * 0.7;
    };
    const tiles = [];
    for (let x = Math.floor(center.x - half.x - 3); x <= Math.ceil(center.x + half.x + 3); x += 1) {
      for (let z = Math.floor(center.z - half.z - 3); z <= Math.ceil(center.z + half.z + 3); z += 1) {
        if (!isLand(x, z)) continue;
        const edge = !isLand(x + 1, z) || !isLand(x - 1, z) || !isLand(x, z + 1) || !isLand(x, z - 1);
        tiles.push({ x, z, h: heightAt(x), edge, group: groupFor(x, z) });
      }
    }

    // Each column: a grass cap, a band of dirt, and dark rock down into the sea. Plus tufts, flowers and pebbles.
    const layers = new Map();   // group -> { grass, dirt, rock, tufts, flowers, pebbles }
    const layersFor = (group) => {
      if (!layers.has(group)) layers.set(group, { grass: [], dirt: [], rock: [], tufts: [], flowers: [], pebbles: [] });
      return layers.get(group);
    };
    for (const tile of tiles) {
      const random = makeRandom((tile.x * 73856093) ^ (tile.z * 19349663) ^ 0x5bd1e995);
      tile.random = random;
      const list = layersFor(tile.group);
      list.grass.push({ x: tile.x, y: tile.h - 0.12, z: tile.z, color: pick(COLORS.grass, random) });
      list.dirt.push({ x: tile.x, y: tile.h - 0.49, z: tile.z, color: pick(COLORS.dirt, random) });
      const bottom = SEA - 1.0;
      const top = tile.h - 0.74;
      list.rock.push({ x: tile.x, y: (top + bottom) / 2, z: tile.z, s: 1, sy: top - bottom, color: random() < 0.85 ? pick(COLORS.deepRock, random) : "#3f6b3a" });
      if (!keepClear(tile.x, tile.z, 0.9)) continue;
      for (let i = 0; i < 2; i += 1) {
        if (random() < 0.55) list.tufts.push({ x: tile.x + (random() - 0.5) * 0.8, y: tile.h + 0.08, z: tile.z + (random() - 0.5) * 0.8, ry: random() * 6, s: 0.7 + random() * 0.6, color: pick(["#4fae3b", "#5fc24a", "#3f9a36"], random) });
      }
      if (random() < 0.16) list.flowers.push({ x: tile.x + (random() - 0.5) * 0.7, y: tile.h + 0.08, z: tile.z + (random() - 0.5) * 0.7, s: 1, color: pick(["#ffd34d", "#ff9ec7", "#ffffff", "#c993f0", "#ff8a3d"], random) });
      if (random() < 0.06) list.pebbles.push({ x: tile.x + (random() - 0.5) * 0.7, y: tile.h + 0.04, z: tile.z + (random() - 0.5) * 0.7, ry: random() * 6, s: 0.8 + random() * 0.6, color: pick(COLORS.rock, random) });
    }
    for (const [group, list] of layers) {
      instances(group, new THREE.BoxGeometry(1, 0.24, 1), list.grass);
      instances(group, new THREE.BoxGeometry(1, 0.5, 1), list.dirt);
      instances(group, new THREE.BoxGeometry(1, 1, 1), list.rock);
      instances(group, new THREE.ConeGeometry(0.06, 0.2, 4), list.tufts);
      instances(group, new THREE.IcosahedronGeometry(0.06, 0), list.flowers);
      instances(group, new THREE.DodecahedronGeometry(0.09, 0), list.pebbles);
    }

    // Trees, palms, ferns, bushes, mushrooms and rocks on the free tiles
    for (const tile of tiles) {
      const random = tile.random;
      if (tile.edge || !keepClear(tile.x, tile.z, 1.5) || random() > 0.24) continue;
      const kind = random();
      const at = new THREE.Vector3(tile.x + (random() - 0.5) * 0.4, tile.h, tile.z + (random() - 0.5) * 0.4);
      const turn = random() * Math.PI * 2;
      const size = 0.8 + random() * 0.45;
      if (kit) {
        const name = kind < 0.3 ? pick(["TreeRound", "TreeRound", "TreeFruit", "TreeTall"], random)
          : kind < 0.55 ? pick(["PalmA", "PalmB"], random)
            : kind < 0.72 ? pick(["Fern", "FernBright"], random)
              : kind < 0.84 ? "Bush" : kind < 0.92 ? "Mushrooms" : pick(["RockA", "RockB", "RockC"], random);
        place(name, tile.group, at, turn, size);
      } else if (kind < 0.3) addTree(tile.group, random, at, 0.8 + random() * 0.5, random() < 0.3);
      else if (kind < 0.55) addPalm(tile.group, random, at, 0.8 + random() * 0.35);
      else if (kind < 0.72) addFern(tile.group, random, at, 0.8 + random() * 0.4);
      else if (kind < 0.84) addBush(tile.group, random, at);
      else if (kind < 0.92) addMushrooms(tile.group, random, at);
      else addRock(tile.group, random, at, 0.25 + random() * 0.2);
    }

    // A dock with a little boat on the front edge
    const shore = tiles.filter((tile) => tile.edge).sort((a, b) => (b.x + b.z) - (a.x + a.z));
    if (shore.length) {
      const tile = shore[Math.min(shore.length - 1, 3)];
      addDock(tile.group, tile);
    }
    return tiles;
  }

  function addTree(group, random, at, size, fruit) {
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.1 * size, 0.16 * size, 1.1 * size, 6), material(COLORS.trunk));
    trunk.position.copy(at).add(new THREE.Vector3(0, 0.55 * size, 0));
    trunk.castShadow = true;
    const crown = new THREE.Group();
    crown.position.copy(at).add(new THREE.Vector3(0, 1.1 * size, 0));
    for (const [bx, by, bz, r] of [[0, 0.35, 0, 0.62], [0.36, 0.12, 0.1, 0.42], [-0.32, 0.16, 0.16, 0.45], [0.04, 0.15, -0.36, 0.42], [0.05, 0.78, 0, 0.36]]) {
      const blob = new THREE.Mesh(lumpyBall(r * size, random), material(by > 0.7 ? pick(COLORS.brightLeaves, random) : pick(COLORS.leaves, random)));
      blob.position.set(bx * size, by * size, bz * size);
      blob.castShadow = true;
      crown.add(blob);
    }
    if (fruit) {
      for (let i = 0; i < 6; i += 1) {
        const ball = new THREE.Mesh(new THREE.IcosahedronGeometry(0.07 * size, 1), material("#f0912e"));
        const angle = random() * Math.PI * 2;
        ball.position.set(Math.cos(angle) * 0.55 * size, (0.15 + random() * 0.5) * size, Math.sin(angle) * 0.55 * size);
        crown.add(ball);
      }
    }
    group.add(trunk, crown);
    const phase = random() * 6;
    movers.push((time) => { crown.rotation.z = Math.sin(time * 0.9 + phase) * 0.025; crown.rotation.x = Math.cos(time * 0.7 + phase) * 0.025; });
  }

  function addPalm(group, random, at, size) {
    let lean = 0;
    let height = 0;
    for (let i = 0; i < 5; i += 1) {
      lean = i * 0.06 * size;
      const piece = new THREE.Mesh(new THREE.CylinderGeometry(0.09 * size * (1 - i * 0.08), 0.12 * size * (1 - i * 0.08), 0.5 * size, 6), material(COLORS.trunk));
      piece.position.copy(at).add(new THREE.Vector3(lean, height + 0.25 * size, 0));
      piece.rotation.z = -0.1;
      piece.castShadow = true;
      group.add(piece);
      height += 0.47 * size;
    }
    const crown = new THREE.Group();
    crown.position.copy(at).add(new THREE.Vector3(lean + 0.06, height, 0));
    const colors = [...COLORS.leaves, ...COLORS.brightLeaves];
    for (let i = 0; i < 8; i += 1) {
      const leaf = new THREE.Mesh(leafShape(1.3 * size, 0.44 * size, 0.7 * size), material(pick(colors, random), { side: THREE.DoubleSide }));
      leaf.rotation.set(-0.34, (i / 8) * Math.PI * 2, 0, "YXZ");
      leaf.castShadow = true;
      crown.add(leaf);
    }
    group.add(crown);
    const phase = random() * 6;
    movers.push((time) => { crown.rotation.z = Math.sin(time * 1.2 + phase) * 0.05; crown.rotation.x = Math.cos(time * 1.0 + phase) * 0.04; });
  }

  function addFern(group, random, at, size) {
    const plant = new THREE.Group();
    plant.position.copy(at);
    const count = 6 + Math.floor(random() * 3);
    for (let i = 0; i < count; i += 1) {
      const leaf = new THREE.Mesh(leafShape((0.7 + random() * 0.3) * size, 0.4 * size, 0.4 * size), material(pick(random() < 0.4 ? COLORS.brightLeaves : COLORS.leaves, random), { side: THREE.DoubleSide }));
      leaf.rotation.set(-0.72, (i / count) * Math.PI * 2 + random() * 0.4, 0, "YXZ");
      plant.add(leaf);
    }
    group.add(plant);
    const phase = random() * 6;
    movers.push((time) => { plant.rotation.z = Math.sin(time * 1.5 + phase) * 0.05; });
  }

  function addBush(group, random, at) {
    const bush = new THREE.Mesh(lumpyBall(0.35 + random() * 0.15, random), material(pick(COLORS.leaves, random)));
    bush.position.copy(at).add(new THREE.Vector3(0, 0.22, 0));
    bush.scale.y = 0.75;
    bush.castShadow = true;
    group.add(bush);
    for (let i = 0; i < 4; i += 1) {
      const berry = new THREE.Mesh(new THREE.IcosahedronGeometry(0.06, 0), material(pick(["#ff9ec7", "#c993f0", "#ffd34d"], random)));
      berry.position.copy(at).add(new THREE.Vector3((random() - 0.5) * 0.6, 0.3 + random() * 0.2, (random() - 0.5) * 0.6));
      group.add(berry);
    }
  }

  function addMushrooms(group, random, at) {
    for (let i = 0; i < 2 + Math.floor(random() * 2); i += 1) {
      const spot = at.clone().add(new THREE.Vector3((random() - 0.5) * 0.5, 0, (random() - 0.5) * 0.5));
      const size = 0.7 + random() * 0.6;
      const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.04 * size, 0.06 * size, 0.18 * size, 6), material(COLORS.cream));
      stem.position.copy(spot).add(new THREE.Vector3(0, 0.09 * size, 0));
      const cap = new THREE.Mesh(new THREE.SphereGeometry(0.13 * size, 8, 4, 0, Math.PI * 2, 0, Math.PI / 2), material("#ef5b4a"));
      cap.position.copy(spot).add(new THREE.Vector3(0, 0.16 * size, 0));
      group.add(stem, cap);
    }
  }

  function addRock(group, random, at, size) {
    const rockMesh = new THREE.Mesh(lumpyBall(size, random, 0.2, 0), material(pick(COLORS.rock, random)));
    rockMesh.position.copy(at).add(new THREE.Vector3(0, size * 0.3, 0));
    rockMesh.scale.y = 0.7;
    rockMesh.castShadow = true;
    group.add(rockMesh);
  }

  function addDock(group, tile) {
    if (kit) {
      const turn = Math.PI / 4 + Math.PI;   // pointing out to sea, toward the front
      place("Dock", group, new THREE.Vector3(tile.x, SEA - 0.6, tile.z), turn);
      const boat = place("Boat", group, new THREE.Vector3(tile.x, SEA, tile.z).add(new THREE.Vector3(0.8, 0, -2.1).applyAxisAngle(UP, turn)), turn);
      movers.push((time) => {
        boat.position.y = SEA + Math.sin(time * 1.3) * 0.04;
        boat.rotation.z = Math.sin(time * 1.1) * 0.05;
      });
      return;
    }
    const dock = new THREE.Group();
    dock.position.set(tile.x, 0, tile.z);
    dock.rotation.y = Math.PI / 4 + Math.PI;   // pointing out to sea, toward the front
    for (let i = 0; i < 7; i += 1) {
      const plank = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.06, 0.24), material(i % 2 ? COLORS.wood : COLORS.woodDark));
      plank.position.set(0, SEA + 0.35, -0.6 - i * 0.26);
      plank.castShadow = true;
      dock.add(plank);
    }
    for (const [x, z] of [[-0.36, -1.0], [0.36, -1.0], [-0.36, -2.3], [0.36, -2.3]]) {
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.9, 6), material(COLORS.woodDark));
      post.position.set(x, SEA + 0.1, z);
      dock.add(post);
    }
    const boat = new THREE.Group();
    const hull = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.18, 1.0), material(COLORS.wood));
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.05, 0.14), material(COLORS.woodDark));
    seat.position.y = 0.1;
    boat.add(hull, seat);
    boat.position.set(0.8, SEA + 0.1, -2.1);
    dock.add(boat);
    group.add(dock);
    movers.push((time) => {
      boat.position.y = SEA + 0.1 + Math.sin(time * 1.3) * 0.04;
      boat.rotation.z = Math.sin(time * 1.1) * 0.05;
    });
  }

  function buildSea(group, random, tiles, box) {
    // How far every spot of sea is from the island, worked out once and stored as a small picture (like Landing)
    const SIZE = 128;
    const center = box.getCenter(new THREE.Vector3());
    const range = Math.max(box.max.x - box.min.x, box.max.z - box.min.z) / 2 + 14;
    const MAX_DISTANCE = 8;
    const shoreTiles = tiles.filter((tile) => tile.edge);
    const distances = new Uint8Array(SIZE * SIZE);
    for (let row = 0; row < SIZE; row += 1) {
      for (let column = 0; column < SIZE; column += 1) {
        const x = ((column + 0.5) / SIZE) * range * 2 - range + center.x;
        const z = ((row + 0.5) / SIZE) * range * 2 - range + center.z;
        let nearest = Infinity;
        for (const tile of shoreTiles) {
          const across = Math.max(Math.abs(x - tile.x) - 0.5, 0);
          const down = Math.max(Math.abs(z - tile.z) - 0.5, 0);
          nearest = Math.min(nearest, across * across + down * down);
        }
        distances[row * SIZE + column] = Math.min(1, Math.sqrt(nearest) / MAX_DISTANCE) * 255;
      }
    }
    const shore = new THREE.DataTexture(distances, SIZE, SIZE, THREE.RedFormat);
    shore.magFilter = THREE.LinearFilter;
    shore.minFilter = THREE.LinearFilter;
    shore.needsUpdate = true;
    const uniforms = {
      uTime: { value: 0 },
      uShore: { value: shore },
      uRange: { value: range },
      uMaxDistance: { value: MAX_DISTANCE },
      uFall: { value: new THREE.Vector2(1e4, 1e4) },   // no waterfall into the sea here
      uDeep: { value: new THREE.Color("#1f9fd6") },
      uShallow: { value: new THREE.Color("#63e6df") },
      uFoam: { value: new THREE.Color("#f3fffd") },
      uPixel: { value: 5 * renderer.getPixelRatio() },
    };
    const geometry = new THREE.PlaneGeometry(range * 2, range * 2);
    geometry.rotateX(-Math.PI / 2);
    const surface = new THREE.Mesh(geometry, new THREE.ShaderMaterial({ uniforms, vertexShader: SEA_VERTEX, fragmentShader: SEA_FRAGMENT, toneMapped: false }));
    surface.position.set(center.x, SEA, center.z);
    group.add(surface);

    // Rocks and lily pads out in the water
    const padMaterial = material("#58b84a");
    for (let i = 0; i < 14 && shoreTiles.length; i += 1) {
      const tile = pick(shoreTiles, random);
      const out = new THREE.Vector3(tile.x - center.x, 0, tile.z - center.z).normalize().multiplyScalar(1.4 + random() * 2.6);
      const x = tile.x + out.x;
      const z = tile.z + out.z;
      if (i % 2) {
        const size = 0.3 + random() * 0.35;
        const rockMesh = new THREE.Mesh(lumpyBall(size, random, 0.2, 0), material(pick(COLORS.rock, random)));
        rockMesh.position.set(x, SEA + size * 0.2, z);
        rockMesh.scale.y = 0.8;
        rockMesh.castShadow = true;
        group.add(rockMesh);
      } else {
        const size = 0.2 + random() * 0.18;
        const pad = new THREE.Mesh(new THREE.CylinderGeometry(size, size, 0.04, 9), padMaterial);
        pad.position.set(x, SEA + 0.03, z);
        group.add(pad);
      }
    }
    movers.push((time) => { uniforms.uTime.value = time; });
  }

  // ---------- Your video: the waterfall cliff ----------

  function buildCliff(group, random, point) {
    const cliff = new THREE.Group();
    cliff.position.copy(point);
    const depth = 3.8;
    const fallWidth = 1.9;
    const foamMaterial = material(COLORS.foam);
    const foam = [];
    const spray = [];
    CLIFF.forEach(([front, height], i) => {
      const back = i === 0 ? front - 2.4 : CLIFF[i - 1][0];
      const width = front - back;
      const middle = back + width / 2;
      // rock body, a band of dirt, grass on top either side of the water (the same layers as the island)
      // (the Blender cliff has all of this already; these are only the fallback)
      if (!kit) {
      const body = new THREE.Mesh(new THREE.BoxGeometry(width, height - 0.7, depth), material(pick(COLORS.deepRock, random)));
      body.position.set(middle, (height - 0.7) / 2, 0);
      const dirtBand = new THREE.Mesh(new THREE.BoxGeometry(width, 0.48, depth), material(pick(COLORS.dirt, random)));
      dirtBand.position.set(middle, height - 0.46, 0);
      for (const mesh of [body, dirtBand]) { mesh.castShadow = true; mesh.receiveShadow = true; cliff.add(mesh); }
      for (const side of [-1, 1]) {
        const cap = new THREE.Mesh(new THREE.BoxGeometry(width, 0.24, (depth - fallWidth) / 2), material(pick(COLORS.grass, random)));
        cap.position.set(middle, height - 0.1, side * (fallWidth / 2 + (depth - fallWidth) / 4));
        cap.castShadow = true;
        cap.receiveShadow = true;
        cliff.add(cap);
      }
      // Moss hanging down the rock
      for (let k = 0; k < 4; k += 1) {
        const moss = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.4 + random() * 0.8, 0.3), material("#3f8f3a"));
        const z = (random() < 0.5 ? -1 : 1) * (fallWidth / 2 + 0.25 + random() * 0.6);
        moss.position.set(front + 0.02, height - 0.9 - random() * 0.6, z);
        cliff.add(moss);
      }
      }
      // The water: running across the top, then pouring down the front
      const runTexture = flow(waterTexture(random, 1, width / 2.4, false), 0.3);
      const run = new THREE.Mesh(new THREE.PlaneGeometry(fallWidth, width, 6, Math.max(4, Math.round(width * 5))), waterMaterial(runTexture, 0.03));
      run.rotation.set(-Math.PI / 2, 0, -Math.PI / 2);
      run.position.set(middle, height - 0.04, 0);
      cliff.add(run);
      const below = i + 1 < CLIFF.length ? CLIFF[i + 1][1] : 0;
      const drop = height - below;
      const fallTexture = flow(waterTexture(random, 1, drop / 2.4, false), 0.95);
      const sheet = new THREE.Mesh(fallGeometry(fallWidth, drop + 0.05, 0.42), waterMaterial(fallTexture));
      sheet.rotation.y = Math.PI / 2;
      sheet.position.set(front + 0.02, height - 0.02, 0);
      const inner = new THREE.Mesh(fallGeometry(fallWidth * 0.92, drop, 0.16), waterMaterial(flow(waterTexture(random, 1, drop / 2.4, false), 0.7)));
      inner.material.color.set("#7ccfe6");
      inner.rotation.y = Math.PI / 2;
      inner.position.set(front + 0.01, height - 0.05, 0);
      // the water curling over the lip
      const lip = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, fallWidth, 10, 1, true, 0, Math.PI / 2), waterMaterial(runTexture));
      lip.rotation.x = Math.PI / 2;
      lip.position.set(front - 0.12, height - 0.18, 0);
      cliff.add(sheet, inner, lip);
      // Foam where it lands, and white drops falling with it
      const puffs = i === CLIFF.length - 1 ? 14 : 8;
      for (let k = 0; k < puffs; k += 1) {
        const size = 0.12 + random() * 0.16;
        const puff = new THREE.Mesh(lumpyBall(size, random, 0.1, 0), foamMaterial);
        puff.position.set(front + 0.2 + random() * 0.5, below + 0.05, (random() - 0.5) * fallWidth);
        cliff.add(puff);
        foam.push({ mesh: puff, phase: random() * 6, speed: 2.2 + random() * 2, baseY: below + 0.05 });
      }
      for (let k = 0; k < 5; k += 1) {
        const drop3 = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.16, 0.08), new THREE.MeshBasicMaterial({ color: "#ffffff" }));
        cliff.add(drop3);
        spray.push({ mesh: drop3, x: front + 0.18, top: height, bottom: below, z: (random() - 0.5) * (fallWidth - 0.3), phase: random() });
      }
    });
    // The splash pool at the bottom
    const pool = new THREE.Mesh(waterDisc(1.55), waterMaterial(flow(waterTexture(random, 1.2, 1.2, true), 0.05), 0.07));
    pool.position.set(1.75, 0.1, 0);
    cliff.add(pool);
    if (kit) {
      place("Cliff", cliff, new THREE.Vector3(0, 0, 0));
      place("PoolRim", cliff, new THREE.Vector3(1.75, 0, 0));
    } else {
      const rim = new THREE.Mesh(new THREE.TorusGeometry(1.57, 0.1, 6, 28), material(pick(COLORS.rock, random)));
      rim.rotation.x = Math.PI / 2;
      rim.position.set(1.75, 0.03, 0);
      cliff.add(rim);
    }
    const mist = [];
    for (let k = 0; k < 7; k += 1) {
      const puff = new THREE.Mesh(new THREE.IcosahedronGeometry(0.35 + random() * 0.2, 1),
        new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.35, depthWrite: false }));
      cliff.add(puff);
      mist.push({ mesh: puff, z: -1 + random() * 2, phase: random() });
    }
    // Jungle on top of the cliff
    if (kit) {
      place("PalmA", cliff, new THREE.Vector3(-3.7, CLIFF[0][1], -1.2), 0.4);
      place("PalmB", cliff, new THREE.Vector3(-3.1, CLIFF[0][1], 1.3), 2.1);
      place("TreeFruit", cliff, new THREE.Vector3(-1.6, CLIFF[1][1], -1.5), 1, 0.75);
      place("FernBright", cliff, new THREE.Vector3(-0.3, CLIFF[2][1], 1.5), 0.6, 0.85);
    } else {
      for (const [x, z] of [[-3.7, -1.2], [-3.1, 1.3]]) addPalm(cliff, random, new THREE.Vector3(x, CLIFF[0][1], z), 1.0);
      addTree(cliff, random, new THREE.Vector3(-1.6, CLIFF[1][1], -1.5), 0.75, true);
      addFern(cliff, random, new THREE.Vector3(-0.3, CLIFF[2][1], 1.5), 0.8);
    }
    group.add(cliff);
    movers.push((time) => {
      for (const puff of foam) {
        const wave = Math.sin(time * puff.speed + puff.phase);
        puff.mesh.scale.setScalar(1 + wave * 0.28);
        puff.mesh.position.y = puff.baseY + (wave + 1) * 0.045;
      }
      for (const s of spray) {
        const p = (time * 0.9 + s.phase) % 1;
        s.mesh.position.set(s.x + p * 0.25, s.top - p * (s.top - s.bottom), s.z);
      }
      for (const m of mist) {
        const p = (time * 0.18 + m.phase) % 1;
        m.mesh.position.set(1.0 + p * 0.8, 0.2 + p * 1.6, m.z);
        m.mesh.material.opacity = 0.35 * (1 - p);
        m.mesh.scale.setScalar(0.7 + p * 0.9);
      }
    });
    return new THREE.Vector3(point.x + 3.3, point.y, point.z);   // where its river leaves the pool
  }

  // ---------- Prompts (lily pads) and clips (platforms with flags) ----------

  function buildPad(group, random, point, busy) {
    const pond = new THREE.Mesh(waterDisc(1.05), waterMaterial(flow(waterTexture(random, 0.8, 0.8, true), 0.04), 0.05));
    pond.position.copy(point).add(new THREE.Vector3(0, 0.08, 0));
    let rim = null;
    if (kit) place("PondRim", group, point, point.x + point.z);
    else {
      rim = new THREE.Mesh(new THREE.TorusGeometry(1.07, 0.09, 6, 28), material(pick(COLORS.rock, random)));
      rim.rotation.x = Math.PI / 2;
      rim.position.copy(point).add(new THREE.Vector3(0, 0.03, 0));
    }
    const pad = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.62, 0.06, 24, 1, false, 0.35, Math.PI * 2 - 0.7), material("#5fc24a"));
    pad.castShadow = true;
    const lotus = new THREE.Mesh(new THREE.IcosahedronGeometry(0.14, 0), material("#ff8fb4"));
    group.add(pond, pad, lotus);
    if (rim) group.add(rim);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.7, 0.03, 4, 32), new THREE.MeshBasicMaterial({ color: "#e8fbff", transparent: true }));
    ring.rotation.x = Math.PI / 2;
    ring.position.copy(point).add(new THREE.Vector3(0, 0.09, 0));
    ring.visible = busy;
    group.add(ring);
    movers.push((time) => {
      pad.position.copy(point).add(new THREE.Vector3(0, 0.1 + Math.sin(time * 1.4 + point.x) * 0.02, 0));
      pad.rotation.y = Math.sin(time * 0.5 + point.z) * 0.08;
      lotus.position.copy(pad.position).add(new THREE.Vector3(-0.25, 0.1, 0.2));
      if (busy) {
        const age = (time * 0.7) % 1;
        ring.scale.setScalar(0.8 + age * 0.6);
        ring.material.opacity = 1 - age;
      }
    });
    return point;
  }

  function buildClipSpot(group, random, point, picked) {
    const spot = new THREE.Group();
    spot.position.copy(point);
    if (kit) place("Platform", spot, new THREE.Vector3(0, 0, 0));   // stone base, planks and the flag pole
    else {
      const base = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.85, 0.3, 8), material(pick(COLORS.rock, random)));
      base.position.y = 0.15;
      const deck = new THREE.Mesh(new THREE.CylinderGeometry(0.72, 0.72, 0.08, 8), material(COLORS.wood));
      deck.position.y = 0.34;
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1.3, 6), material(COLORS.woodDark));
      pole.position.set(0.5, 1.0, -0.3);
      for (const mesh of [base, deck, pole]) { mesh.castShadow = true; mesh.receiveShadow = true; spot.add(mesh); }
    }
    // The flag: down and grey until the clip is picked, then up and green
    const flag = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.32), new THREE.MeshStandardMaterial({ color: picked ? "#3fae4a" : "#cfd8d4", side: THREE.DoubleSide, flatShading: true }));
    flag.position.set(0.76, picked ? 1.45 : 0.75, -0.3);
    spot.add(flag);
    if (picked) {
      const glow = new THREE.Mesh(new THREE.TorusGeometry(0.88, 0.05, 6, 24), new THREE.MeshBasicMaterial({ color: "#7cf06a" }));
      glow.rotation.x = Math.PI / 2;
      glow.position.y = 0.32;
      spot.add(glow);
      movers.push((time) => { glow.material.color.setHSL(0.31, 0.8, 0.55 + Math.sin(time * 3) * 0.1); });
    }
    group.add(spot);
    movers.push((time) => { flag.rotation.y = Math.sin(time * 3 + point.x) * 0.25; });
  }

  // ---------- Rivers: they follow the ground, and drop in a waterfall wherever the land steps down ----------

  // The river's centerline. It does all its sideways bending up on the higher ground, then runs straight across
  // each step (square to the cliff) and drops down the cliff face, so every waterfall falls cleanly.
  // Heights come from the tile under each point, so the water sits exactly on the ground.
  function riverPath(from, to, heightAt) {
    const groundAt = (x) => heightAt(Math.round(x)) + 0.06;
    const edges = [];   // where the land steps down: halfway between two tiles
    for (let x = Math.round(from.x); x < Math.round(to.x); x += 1) {
      if (heightAt(x) !== heightAt(x + 1)) edges.push(x + 0.5);
    }
    const path = [];
    const drops = [];
    const curve = (a, b) => {
      // the handles are never longer than half the way across, so the river can't double back on itself
      const dx = Math.max(0.05, Math.abs(b.x - a.x) * 0.5);
      const bend = new THREE.CubicBezierCurve3(
        new THREE.Vector3(a.x, 0, a.z), new THREE.Vector3(a.x + dx, 0, a.z),
        new THREE.Vector3(b.x - dx, 0, b.z), new THREE.Vector3(b.x, 0, b.z));
      for (const point of bend.getSpacedPoints(Math.max(8, Math.ceil(bend.getLength() * 5)))) {
        path.push(new THREE.Vector3(point.x, groundAt(Math.min(point.x, b.x)), point.z));
      }
    };
    const straight = (fromX, toX, z) => {
      for (let x = fromX; x < toX - 0.01; x += 0.25) path.push(new THREE.Vector3(x, groundAt(x), z));
    };
    if (!edges.length) {
      curve(from, to);
      return { path, drops };
    }
    // bend over to the target's row before the first step
    const bendEnd = Math.max(from.x + 0.6, edges[0] - 0.8);
    curve(from, new THREE.Vector3(bendEnd, 0, to.z));
    let x = bendEnd;
    for (const edge of edges) {
      straight(x + 0.25, edge, to.z);
      const high = groundAt(edge - 0.2);
      const low = groundAt(edge + 0.2);
      path.push(new THREE.Vector3(edge + 0.03, high, to.z), new THREE.Vector3(edge + 0.07, low, to.z));
      drops.push(new THREE.Vector3(edge + 0.35, low, to.z));
      x = edge + 0.07;
    }
    straight(x + 0.25, to.x, to.z);
    path.push(new THREE.Vector3(to.x, groundAt(to.x), to.z));
    return { path, drops };
  }

  const ACROSS = 4;   // points across a river
  function ribbonAlong(path, width) {
    const positions = [];
    const uvs = [];
    const indices = [];
    let along = 0;
    path.forEach((point, i) => {
      const before = path[Math.max(0, i - 1)];
      const after = path[Math.min(path.length - 1, i + 1)];
      const flat = new THREE.Vector3(after.x - before.x, 0, after.z - before.z);
      if (flat.lengthSq() < 0.01) flat.set(1, 0, 0);   // straight down a waterfall: keep facing along the river
      flat.normalize();
      const side = new THREE.Vector3(-flat.z, 0, flat.x).multiplyScalar(width / 2);
      if (i > 0) along += point.distanceTo(path[i - 1]);
      for (let k = 0; k <= ACROSS; k += 1) {   // several points across the river, so its surface can ripple
        const t = (k / ACROSS) * 2 - 1;
        positions.push(point.x + side.x * t, point.y, point.z + side.z * t);
        uvs.push(k / ACROSS, along / 2.4);
      }
      if (i < path.length - 1) {
        const row = i * (ACROSS + 1);
        const next = row + ACROSS + 1;
        for (let k = 0; k < ACROSS; k += 1) indices.push(row + k, row + k + 1, next + k, row + k + 1, next + k + 1, next + k);
      }
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    return { geometry, length: along };
  }

  function buildRiver(group, random, from, to, heightAt, busy) {
    const { path, drops } = riverPath(from, to, heightAt);
    const { geometry, length } = ribbonAlong(path, RIVER_WIDTH);
    const texture = flow(waterTexture(random, 1, 1, false), 0.5);
    const water = new THREE.Mesh(geometry, waterMaterial(texture, 0.045));
    water.receiveShadow = true;
    group.add(water);
    // At each drop, a curved sheet of water arcing out over the edge (in front of the river's own drop)
    for (const spot of drops) {
      const edge = spot.x - 0.35;   // where the land steps down
      const top = heightAt(Math.round(edge - 0.2)) + 0.06;
      const sheet = new THREE.Mesh(fallGeometry(RIVER_WIDTH * 0.96, top - spot.y + 0.04, 0.3), waterMaterial(flow(waterTexture(random, 1, 0.6, false), 0.95)));
      sheet.rotation.y = Math.PI / 2;
      sheet.position.set(edge + 0.02, top - 0.01, spot.z);
      group.add(sheet);
    }
    // Foam where each waterfall lands
    for (const spot of drops) {
      for (let k = 0; k < 7; k += 1) {
        const size = 0.1 + random() * 0.12;
        const puff = new THREE.Mesh(lumpyBall(size, random, 0.1, 0), material(COLORS.foam));
        puff.position.set(spot.x + (random() - 0.5) * 0.4, spot.y, spot.z + (random() - 0.5) * RIVER_WIDTH * 0.8);
        group.add(puff);
        const phase = random() * 6;
        movers.push((time) => { puff.scale.setScalar(1 + Math.sin(time * 3 + phase) * 0.25); });
      }
    }
    // A little clip card floating down the river (two while a prompt is working)
    const lengths = [0];
    for (let i = 1; i < path.length; i += 1) lengths.push(lengths[i - 1] + path[i].distanceTo(path[i - 1]));
    const colors = [["#ff7a3d", "#ffb347"], ["#3d8bff", "#7fd0ff"], ["#b25dff", "#ff7ad9"], ["#2fbf71", "#9be15d"]];
    for (let c = 0; c < (busy ? 2 : 1); c += 1) {
      const [a, b] = pick(colors, random);
      const white = material("#ffffff");
      const card = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.04, 0.32),
        [white, white, new THREE.MeshStandardMaterial({ map: clipTexture(a, b), roughness: 0.5 }), white, white, white]);
      card.castShadow = true;
      group.add(card);
      const offset = c * 0.5 + random() * 0.3;
      movers.push((time) => {
        const distance = ((time * 0.45 / Math.max(length, 1) + offset) % 1) * length;
        let i = lengths.findIndex((value) => value >= distance);
        if (i <= 0) i = 1;
        const span = lengths[i] - lengths[i - 1] || 1;
        const a = path[i - 1];
        const b = path[i];
        const point = a.clone().lerp(b, (distance - lengths[i - 1]) / span);
        const across = Math.hypot(b.x - a.x, b.z - a.z);
        if (Math.abs(b.y - a.y) > across * 2) {
          // Going over a waterfall: the card falls in front of the water (not into the cliff), tumbling as it goes
          const fallen = (a.y - point.y) / Math.max(0.01, a.y - b.y);
          card.position.set(point.x + 0.5, point.y + 0.15, point.z);
          card.rotation.set(0, 0, -fallen * Math.PI * 2);   // one full flip, landing the right way up
        } else {
          // just below a waterfall, keep the card clear of the cliff face behind it
          let x = point.x;
          for (const drop of drops) {
            if (Math.abs(point.y - drop.y) < 0.05 && Math.abs(point.z - drop.z) < 0.6 && x > drop.x - 0.6 && x < drop.x + 0.12) x = drop.x + 0.12;
          }
          card.position.set(x, point.y + 0.04 + Math.sin(time * 2 + c) * 0.02, point.z);
          card.rotation.set(0, Math.atan2(b.x - a.x, b.z - a.z) + Math.PI / 2, 0);
        }
      });
    }
    return path;
  }

  // ---------- Building the world from the graph ----------

  function setGraph(graph) {
    if (!kitDone) {   // build once the Blender pieces are here (or failed to load), so nothing pops in later
      waiting = graph;
      return;
    }
    const { nodes, edges } = graph;
    const key = JSON.stringify([nodes, edges]);
    if (key === lastKey) return;
    const firstTime = !lastKey;
    lastKey = key;
    clear();
    world = new THREE.Group();
    const random = makeRandom(1234);
    const byId = new Map(nodes.map((node) => [node.id, node]));
    // New things go in a group that starts under the sea and rises (not on the first build: then it's all just there)
    const risingGroup = new THREE.Group();
    world.add(risingGroup);
    const isNewNode = (id) => !firstTime && !knownNodes.has(id);
    const isNewEdge = (id) => !firstTime && !knownEdges.has(id);
    const groupFor = (x, z) => (!firstTime && !knownTiles.has(`${x},${z}`) ? risingGroup : world);

    // The terraces: the land steps down just before each prompt's lily pad (and before clips that grow
    // straight out of other clips), so every river that heads right drops in a waterfall
    const cuts = [];
    for (const node of nodes) {
      if (node.type === "generation") cuts.push(Math.round(node.x - 1.4));   // right before the pond
      if (node.type === "clip") {
        const fromClip = edges.some((edge) => edge.target === node.id && byId.get(edge.source)?.type === "clip");
        if (fromClip) cuts.push(Math.round(node.x - 2.2));
      }
    }
    const steps = [...new Set(cuts)].sort((a, b) => a - b).filter((cut, i, list) => i === 0 || cut - list[i - 1] >= 2);
    const heightAt = (x) => LOW + STEP * steps.filter((cut) => cut > x).length;

    const points = new Map(nodes.map((node) => [node.id, new THREE.Vector3(node.x, heightAt(node.x), node.z)]));
    const box = new THREE.Box3();
    for (const point of points.values()) box.expandByPoint(point.clone().setY(0));
    if (box.isEmpty()) box.set(new THREE.Vector3(-3, 0, -3), new THREE.Vector3(3, 0, 3));
    for (const node of nodes) if (node.type === "source") box.expandByPoint(points.get(node.id).clone().setY(0).add(new THREE.Vector3(-4.8, 0, 0)));
    box.expandByScalar(1.2);
    const changedSize = !bounds.equals(box);
    bounds = box.clone();

    const outlets = new Map();
    for (const node of nodes) {
      const point = points.get(node.id);
      const group = isNewNode(node.id) ? risingGroup : world;
      if (node.type === "source") outlets.set(node.id, buildCliff(group, random, point));
      else if (node.type === "generation") outlets.set(node.id, buildPad(group, random, point, node.busy));
      else {
        buildClipSpot(group, random, point, node.picked);
        outlets.set(node.id, new THREE.Vector3(point.x + 0.8, point.y, point.z));
      }
    }
    const paths = [];
    for (const edge of edges) {
      const from = outlets.get(edge.source);
      const end = points.get(edge.target);
      if (!from || !end) continue;
      const to = new THREE.Vector3(end.x - (byId.get(edge.target)?.type === "generation" ? 1.05 : 0.85), end.y, end.z);
      paths.push(buildRiver(isNewEdge(edge.id) ? risingGroup : world, random, from, to, heightAt, edge.busy));
    }

    // Keep plants off the cards' spots, the cliff and the rivers
    const riverPoints = paths.flat();
    const keepClear = (x, z, room) => {
      for (const [id, point] of points) {
        if (byId.get(id).type === "source") {
          if (x > point.x - 5.2 && x < point.x + 3.6 && Math.abs(z - point.z) < 2.6) return false;
        } else if (Math.hypot(point.x - x, point.z - z) < 1.4 + room * 0.5) return false;
      }
      for (const point of riverPoints) if (Math.hypot(point.x - x, point.z - z) < 0.5 + room * 0.5) return false;
      return true;
    };
    const tiles = buildLand(box, heightAt, keepClear, groupFor);
    buildSea(world, random, tiles, box);
    scene.add(world);

    // Start the rise (and a splash of foam where the new land breaks the surface)
    const newTiles = tiles.filter((tile) => tile.group === risingGroup);
    if (risingGroup.children.length) {
      risingGroup.position.y = -RISE_DEPTH;
      rising = { group: risingGroup, start: performance.now() };
      makeSplash(newTiles.length ? newTiles : nodes.filter((node) => isNewNode(node.id)).map((node) => ({ x: node.x, z: node.z })));
    } else {
      rising = null;
    }
    knownTiles = new Set(tiles.map((tile) => `${tile.x},${tile.z}`));
    knownNodes = new Set(nodes.map((node) => node.id));
    knownEdges = new Set(edges.map((edge) => edge.id));

    spots = nodes.map((node) => {
      const point = points.get(node.id).clone();
      point.y += LIFT[node.type] ?? 1;
      if (node.type === "source") point.x -= 1.6;   // above the cliff's top step
      return { id: node.id, point, rises: isNewNode(node.id) };
    });

    const center = box.getCenter(new THREE.Vector3());
    pivotGoal.set(center.x, LOW + STEP, center.z);
    if (firstTime) pivot.copy(pivotGoal);
    const size = box.getSize(new THREE.Vector3()).length() / 2 + 6;
    sun.position.copy(center).add(new THREE.Vector3(12, 18, 5));   // from the front-right, so the waterfalls are lit
    sun.target.position.copy(center);
    Object.assign(sun.shadow.camera, { left: -size, right: size, top: size, bottom: -size, near: 0.5, far: 80 });
    sun.shadow.camera.updateProjectionMatrix();

    if (firstTime) fit(false);
    else if (changedSize) fit(true);   // glide out to show the new land
  }

  // White rings and foam bursting out of the sea around the new land
  function makeSplash(places) {
    if (splash) scene.remove(splash.group);
    const group = new THREE.Group();
    const rings = [];
    const puffs = [];
    const xs = places.map((p) => p.x);
    const zs = places.map((p) => p.z);
    const middle = new THREE.Vector3((Math.min(...xs) + Math.max(...xs)) / 2, SEA + 0.05, (Math.min(...zs) + Math.max(...zs)) / 2);
    const reach = Math.max(2, (Math.max(...xs) - Math.min(...xs) + Math.max(...zs) - Math.min(...zs)) / 4);
    for (let i = 0; i < 3; i += 1) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(1, 0.08, 4, 48), new THREE.MeshBasicMaterial({ color: "#f3fffd", transparent: true }));
      ring.rotation.x = Math.PI / 2;
      ring.position.copy(middle);
      group.add(ring);
      rings.push({ mesh: ring, delay: i * 0.25 });
    }
    const random = makeRandom(places.length * 31 + 7);
    for (const place of places.filter((_, i) => i % 3 === 0).slice(0, 40)) {
      const puff = new THREE.Mesh(lumpyBall(0.18 + random() * 0.18, random, 0.1, 0), material(COLORS.foam, { transparent: true }));
      puff.position.set(place.x + (random() - 0.5), SEA + 0.1, place.z + (random() - 0.5));
      group.add(puff);
      puffs.push({ mesh: puff, phase: random() });
    }
    scene.add(group);
    splash = { group, start: performance.now(), rings, puffs, reach };
  }

  // ---------- Camera: orthographic, turn by dragging, move with right-drag / scroll, zoom with pinch ----------

  let width = 1;
  let height = 1;
  let azimuth = START_AZIMUTH;
  let elevation = START_ELEVATION;
  let spin = 0;                       // keeps turning a little after you let go
  // The camera always looks at one fixed point in the middle of the island and turns around it, so the island
  // stays put on screen while you turn. Moving and fitting slide the view sideways instead (offset, in world
  // units across and up the screen), which never changes what the camera turns around.
  const pivot = new THREE.Vector3();
  const pivotGoal = new THREE.Vector3();   // where the pivot should be (the island's middle); glides there
  const offset = { x: 0, y: 0 };
  let glide = null;                        // { pivot, x, y, zoom } the view is easing toward

  function placeCamera() {
    const aspect = width / height;
    camera.left = (-VIEW_HEIGHT * aspect) / 2 + offset.x;
    camera.right = (VIEW_HEIGHT * aspect) / 2 + offset.x;
    camera.top = VIEW_HEIGHT / 2 + offset.y;
    camera.bottom = -VIEW_HEIGHT / 2 + offset.y;
    const look = new THREE.Vector3(Math.cos(elevation) * Math.sin(azimuth), Math.sin(elevation), Math.cos(elevation) * Math.cos(azimuth));
    camera.position.copy(pivot).addScaledVector(look, 60);
    camera.lookAt(pivot);
    camera.updateProjectionMatrix();
  }
  const pixelsPerUnit = () => (height / VIEW_HEIGHT) * camera.zoom;

  // Frame the island. smooth: glide there over about a second instead of jumping.
  function fit(smooth = false) {
    const before = { pivot: pivot.clone(), x: offset.x, y: offset.y, zoom: camera.zoom };
    pivot.copy(pivotGoal);
    offset.x = 0;
    offset.y = 0;
    placeCamera();
    camera.updateMatrixWorld();
    // Frame what matters: the land with the cliff, pads and clips, with room for the cards above their spots
    const corners = [];
    for (const x of [bounds.min.x - 1.5, bounds.max.x + 1.5]) for (const z of [bounds.min.z - 1.5, bounds.max.z + 1.5]) for (const y of [SEA - 1, LOW]) corners.push(new THREE.Vector3(x, y, z));
    for (const { point } of spots) corners.push(point.clone().setY(point.y + 5.8));
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
    // where each corner lands on screen, measured from the pivot
    const xs = corners.map((c) => c.clone().sub(pivot).dot(right));
    const ys = corners.map((c) => c.clone().sub(pivot).dot(up));
    const spanX = Math.max(...xs) - Math.min(...xs);
    const spanY = Math.max(...ys) - Math.min(...ys);
    offset.x = (Math.max(...xs) + Math.min(...xs)) / 2;
    offset.y = (Math.max(...ys) + Math.min(...ys)) / 2;
    const aspect = width / height;
    camera.zoom = THREE.MathUtils.clamp(0.92 * Math.min((VIEW_HEIGHT * aspect) / spanX, VIEW_HEIGHT / spanY), 0.12, 3);
    if (smooth && !still) {
      glide = { pivot: pivot.clone(), x: offset.x, y: offset.y, zoom: camera.zoom };
      pivot.copy(before.pivot);
      offset.x = before.x;
      offset.y = before.y;
      camera.zoom = before.zoom;
    } else {
      glide = null;
    }
    placeCamera();
  }

  // Turn around the island's middle
  function turnBy(angle) {
    azimuth += angle;
    placeCamera();
  }

  function resetView() {
    azimuth = START_AZIMUTH;
    elevation = START_ELEVATION;
    spin = 0;
    fit(true);
  }

  function zoomBy(factor) {
    camera.zoom = THREE.MathUtils.clamp(camera.zoom * factor, 0.12, 3);
    camera.updateProjectionMatrix();
  }

  // Slide the view across the screen (the offset is where the screen's middle is, in world units)
  function panBy(dx, dy) {
    const scale = pixelsPerUnit();
    offset.x -= dx / scale;
    offset.y += dy / scale;
    placeCamera();
  }

  let drag = null;
  function handleDown(event) {
    // left-drag turns; right-drag, middle-drag or Shift + drag moves
    const mode = event.button === 0 && !event.shiftKey ? "turn" : "move";
    drag = { x: event.clientX, y: event.clientY, mode };
    spin = 0;
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add(mode === "turn" ? "is-turning" : "is-panning");
  }
  function handleMove(event) {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (drag.mode === "move") panBy(dx, dy);
    else {
      spin = -dx * 0.008;
      turnBy(spin);
      elevation = THREE.MathUtils.clamp(elevation + dy * 0.006, MIN_ELEVATION, MAX_ELEVATION);
      placeCamera();
    }
    drag = { ...drag, x: event.clientX, y: event.clientY };
  }
  function handleUp() {
    drag = null;
    canvas.classList.remove("is-panning", "is-turning");
  }
  const noMenu = (event) => event.preventDefault();   // right-drag moves, so no right-click menu
  function handleWheel(event) {
    event.preventDefault();
    if (event.ctrlKey || event.metaKey) zoomBy(Math.exp(-event.deltaY * 0.01));
    else panBy(-event.deltaX, -event.deltaY);
  }

  function resize() {
    const parent = canvas.parentElement;
    width = parent.clientWidth || 1;
    height = parent.clientHeight || 1;
    renderer.setSize(width, height, false);
    placeCamera();
  }

  // ---------- Every frame ----------
  const projected = new THREE.Vector3();
  let frame = 0;
  let stopped = false;
  const start = performance.now();
  let last = start;
  function draw() {
    const now = performance.now();
    const time = still ? 2 : (now - start) / 1000;
    const delta = still ? 0 : Math.min(0.05, (now - last) / 1000);
    last = now;
    if (!drag && Math.abs(spin) > 0.0002) {   // glide to a stop after a turn
      turnBy(spin);
      spin *= 0.92;
    }
    for (const { texture, speed } of flowing) texture.offset.y = (texture.offset.y + delta * speed) % 1;
    waveTime.value = time;
    for (const move of movers) move(time);

    // New land rising out of the sea: fast at first, a tiny overshoot, then it settles
    let rise = 1;
    if (rising) {
      rise = Math.min(1, (now - rising.start) / 1000 / RISE_SECONDS);
      const back = 1.4;
      const eased = 1 + (back + 1) * Math.pow(rise - 1, 3) + back * Math.pow(rise - 1, 2);
      rising.group.position.y = -RISE_DEPTH * (1 - eased);
      if (rise >= 1) { rising.group.position.y = 0; rising = null; }
    }
    if (splash) {
      const age = (now - splash.start) / 1000;
      for (const { mesh, delay } of splash.rings) {
        const p = THREE.MathUtils.clamp((age - delay) / 1.8, 0, 1);
        mesh.scale.setScalar(0.3 + p * splash.reach * 1.6);
        mesh.material.opacity = (1 - p) * 0.9;
        mesh.visible = p > 0 && p < 1;
      }
      for (const { mesh, phase } of splash.puffs) {
        const p = THREE.MathUtils.clamp(age / 1.6 - phase * 0.2, 0, 1);
        mesh.position.y = SEA + 0.1 + Math.sin(p * Math.PI) * 0.6;
        mesh.scale.setScalar(Math.sin(p * Math.PI) * 1.3 + 0.01);
      }
      if (age > 2.6) {
        scene.remove(splash.group);
        splash.group.traverse((object) => { object.geometry?.dispose(); object.material?.dispose?.(); });
        splash = null;
      }
    }
    // The view easing toward a new framing
    if (glide) {
      const k = 1 - Math.pow(0.02, delta);
      pivot.lerp(glide.pivot, k);
      offset.x += (glide.x - offset.x) * k;
      offset.y += (glide.y - offset.y) * k;
      camera.zoom += (glide.zoom - camera.zoom) * k;
      placeCamera();
      if (Math.abs(glide.zoom - camera.zoom) < 0.001 && pivot.distanceTo(glide.pivot) < 0.01) glide = null;
    }

    renderer.render(scene, camera);
    const places = {};
    const lift = rising ? rising.group.position.y : 0;
    for (const { id, point, rises } of spots) {
      projected.copy(point);
      if (rises) projected.y += lift;
      projected.project(camera);
      // new cards ride up with their land, and fade in near the end
      places[id] = { x: (projected.x * 0.5 + 0.5) * width, y: (-projected.y * 0.5 + 0.5) * height, fade: rises && rising ? Math.max(0, (rise - 0.55) / 0.45) : 1 };
    }
    onFrame(places, pixelsPerUnit());
  }
  function loop() {
    if (stopped) return;
    draw();
    frame = requestAnimationFrame(loop);
  }

  const observer = new ResizeObserver(() => { resize(); draw(); });
  observer.observe(canvas.parentElement);
  resize();
  canvas.addEventListener("pointerdown", handleDown);
  canvas.addEventListener("pointermove", handleMove);
  canvas.addEventListener("pointerup", handleUp);
  canvas.addEventListener("pointercancel", handleUp);
  canvas.addEventListener("wheel", handleWheel, { passive: false });
  canvas.addEventListener("contextmenu", noMenu);
  frame = requestAnimationFrame(loop);

  loadKit()
    .then((gltf) => {
      kit = new Map();
      gltf.scene.children.forEach((piece) => {
        piece.traverse((object) => { object.userData.fromKit = true; });
        kit.set(piece.name.replace(/^Kit_/, ""), piece);
      });
    })
    .catch(() => { kit = null; })
    .finally(() => {
      kitDone = true;
      if (waiting && !stopped) setGraph(waiting);
      waiting = null;
    });

  return {
    setGraph,
    zoomBy,
    fit: resetView,
    stop() {
      stopped = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener("pointerdown", handleDown);
      canvas.removeEventListener("pointermove", handleMove);
      canvas.removeEventListener("pointerup", handleUp);
      canvas.removeEventListener("pointercancel", handleUp);
      canvas.removeEventListener("wheel", handleWheel);
      canvas.removeEventListener("contextmenu", noMenu);
      clear();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}
