// Water shared by the AI Studio world (studioWorldScene.js): its moving material, pond discs, waterfall
// sheets and lips, and one helper that draws many copies of a shape at once.
import * as THREE from "three";
import { material } from "../../landing3d/islandScene";

const UP = new THREE.Vector3(0, 1, 0);

// The water's waves move with this clock (set every frame in draw)
export const waveTime = { value: 0 };

// waves: how tall the rolling waves are (0 = still). Wavy water is faceted, like low-poly water,
// so each little wave catches the light.
export function waterMaterial(map, waves = 0) {
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
export function waterDisc(radius) {
  return new THREE.RingGeometry(0.001, radius, 28, 6).rotateX(-Math.PI / 2);
}

// A sheet of falling water that isn't flat: it shoots out from the lip and curves down, and bulges in the
// middle. Its top is at y = 0 and it hangs down to -drop; +z is out from the cliff.
export function fallGeometry(width, drop, reach = 0.32) {
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

// A continuous quarter-turn of water from the flat stream onto the falling sheet.
// Its axis is Z (across the channel); the old cylinder turned about X and left
// the soil behind the lip exposed when viewed from above.
export function waterfallLipGeometry(width) {
  const geometry = new THREE.PlaneGeometry(width, 1, 8, 12);
  const position = geometry.attributes.position;
  for (let i = 0; i < position.count; i += 1) {
    const across = position.getX(i);
    const angle = (0.5 - position.getY(i)) * Math.PI / 2;
    position.setXYZ(i, -0.18 + 0.34 * Math.sin(angle), -0.04 - 0.22 * (1 - Math.cos(angle)), across);
  }
  geometry.computeVertexNormals();
  return geometry;
}

// Many copies of one small shape in one draw: items [{ x, y, z, ry, s, sy, color }]
export function instances(group, geometry, items, shadows = false) {
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
