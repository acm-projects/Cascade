// The plants and rocks on the AI Studio island (studioWorldScene.js). Plants that sway push a function onto
// `movers`, which the world calls every frame with the time.
import * as THREE from "three";
import { COLORS, leafShape, lumpyBall, material, pick } from "../../landing3d/islandScene";

export function createPlants(movers) {
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

  return { addTree, addPalm, addFern, addBush, addMushrooms, addRock };
}
