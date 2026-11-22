// Rivers in the AI Studio world (studioWorldScene.js): they follow the ground and drop in a waterfall
// wherever the land steps down. `flow(texture, speed)` makes a water texture scroll; `movers` get the time
// every frame.
import * as THREE from "three";
import { COLORS, clipTexture, lumpyBall, makeRandom, material, pick, waterTexture } from "../../landing3d/islandScene";
import { fallGeometry, instances, waterMaterial } from "./studioWater";

const RIVER_WIDTH = 1.15;
// The little stones along the river banks: one chunky low-poly pebble shape, in a few earthy browns
const BANK_STONES = ["#a8784a", "#b88a5a", "#9a6a40", "#c29a6a", "#8c6038"];
const bankStone = lumpyBall(1, makeRandom(5), 0.12, 1);   // round pebbles, not spiky shards
// The raised banks either side of a river, so the water looks sunk into a channel in the grass
const BANK_HEIGHT = 0.16;   // how far the bank's top sits above the water
const BANK_TOP = 0.22;      // how wide its flat grassy top is
const BANK_SLOPE = 0.14;    // how far out its outer side slopes back down to the ground

export function createRivers({ flow, movers }) {
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

  // One side of a river's bank along a flat run of the river (side = -1 or 1): a brown dirt wall facing the
  // water, a flat grassy top, then a grassy slope back down to the ground. Each is a strip between two lines
  // that run alongside the river, given as [how far out from the middle, how high above the water].
  function buildBank(group, run, side) {
    const sides = run.map((point, i) => {
      const before = run[Math.max(0, i - 1)];
      const after = run[Math.min(run.length - 1, i + 1)];
      const flat = new THREE.Vector3(after.x - before.x, 0, after.z - before.z);
      if (flat.lengthSq() < 1e-6) flat.set(1, 0, 0);
      flat.normalize();
      return new THREE.Vector3(-flat.z, 0, flat.x).multiplyScalar(side);
    });
    const edge = RIVER_WIDTH / 2;
    const strip = (inner, outer, color) => {
      const positions = [];
      const indices = [];
      run.forEach((point, i) => {
        for (const [out, up] of [inner, outer]) {
          positions.push(point.x + sides[i].x * out, point.y + up, point.z + sides[i].z * out);
        }
        if (i < run.length - 1) {
          const a = i * 2;
          indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
        }
      });
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      geometry.setIndex(indices);
      geometry.computeVertexNormals();
      const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color, roughness: 0.9, flatShading: true, side: THREE.DoubleSide }));
      mesh.receiveShadow = true;
      mesh.castShadow = true;
      group.add(mesh);
    };
    const wallFoot = [edge - 0.03, -0.03];
    const wallTop = [edge + 0.02, BANK_HEIGHT];
    const topEnd = [edge + 0.02 + BANK_TOP, BANK_HEIGHT];
    const slopeFoot = [edge + 0.02 + BANK_TOP + BANK_SLOPE, -0.07];
    strip(wallFoot, wallTop, COLORS.dirt[1]);
    strip(wallTop, topEnd, COLORS.grass[0]);
    strip(topEnd, slopeFoot, COLORS.grass[3]);
  }

  function buildRiver(group, random, from, to, heightAt, busy) {
    const { path, drops } = riverPath(from, to, heightAt);
    const { geometry, length } = ribbonAlong(path, RIVER_WIDTH);
    const texture = flow(waterTexture(random, 1, 1, false), 0.5);
    const water = new THREE.Mesh(geometry, waterMaterial(texture, 0.045));
    water.receiveShadow = true;
    group.add(water);
    // Raised banks along each flat stretch (not down the waterfalls), so the water sits in a channel
    let run = [path[0]];
    const finishRun = () => {
      if (run.length > 1) for (const side of [-1, 1]) buildBank(group, run, side);
    };
    for (let i = 1; i < path.length; i += 1) {
      const a = path[i - 1];
      const b = path[i];
      if (Math.abs(b.y - a.y) > Math.hypot(b.x - a.x, b.z - a.z)) {   // a waterfall: end this stretch
        finishRun();
        run = [b];
      } else {
        run.push(b);
      }
    }
    finishRun();
    // Small brown stones along the tops of both banks.
    // Not on the waterfalls themselves, nor right at a cliff edge (they'd hang in the air), nor at the very ends.
    const stones = [];
    const edgesX = drops.map((spot) => spot.x - 0.35);
    let travelled = 0;
    let next = 0.35;
    for (let i = 1; i < path.length; i += 1) {
      const a = path[i - 1];
      const b = path[i];
      const segment = a.distanceTo(b);
      const across = Math.hypot(b.x - a.x, b.z - a.z);
      const start = travelled;
      travelled += segment;
      if (Math.abs(b.y - a.y) > across) { next = Math.max(next, travelled); continue; }   // a waterfall
      while (next <= travelled && next < length - 0.35) {
        const point = a.clone().lerp(b, (next - start) / (segment || 1));
        next += 0.2 + random() * 0.09;
        if (edgesX.some((edge) => Math.abs(point.x - edge) < 0.28)) continue;
        const side = new THREE.Vector3(-(b.z - a.z), 0, b.x - a.x).normalize();
        for (const s of [-1, 1]) {
          const out = RIVER_WIDTH / 2 + 0.02 + BANK_TOP * (0.3 + random() * 0.4);   // on the bank's flat top
          stones.push({
            x: point.x + side.x * out * s + (random() - 0.5) * 0.05,
            y: point.y + BANK_HEIGHT - 0.02,   // half sunk into the bank
            z: point.z + side.z * out * s + (random() - 0.5) * 0.05,
            s: 0.09 + random() * 0.06,
            sy: (0.09 + random() * 0.06) * 0.5,   // flattened, like river pebbles
            ry: random() * Math.PI * 2,
            color: pick(BANK_STONES, random),
          });
        }
      }
    }
    instances(group, bankStone, stones, true);
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

  return { buildRiver };
}
