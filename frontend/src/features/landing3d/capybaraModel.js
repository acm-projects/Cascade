import * as THREE from "three";
import { material } from "./islandScene";

// Cascade's mascot as a 3D model: a chunky low-poly capybara, in the same
// flat-shaded block style as the Landing island. It faces +x, stands on y = 0 and is about 2.4 long.
// Used by the AI Assistant panel (mascotScene.js).
//
// buildCapybara() returns { group, update(time) }. Call update(seconds) each frame to make it breathe,
// blink and twitch its ears. Skip it to keep the capybara still.
const COLORS = {
  fur: "#b07a48",
  furLight: "#c99260",
  furDark: "#8a5a32",
  chest: "#d8a774",
  nose: "#3b2414",
  eye: "#1e120a",
  cheek: "#ee9a82",
};

export function buildCapybara() {
  const group = new THREE.Group();
  const made = new Map();
  const paint = (color) => {
    if (!made.has(color)) made.set(color, material(color));
    return made.get(color);
  };
  const box = (parent, size, color, at) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), paint(color));
    mesh.position.set(...at);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  };

  // The body: a loaf, with a rounder rump and a softer top so it isn't just one box
  const body = new THREE.Group();
  group.add(body);
  box(body, [1.9, 1.0, 1.2], COLORS.fur, [0, 0.75, 0]);
  box(body, [1.35, 0.22, 1.0], COLORS.fur, [-0.15, 1.33, 0]);
  box(body, [0.28, 0.78, 1.04], COLORS.furDark, [-1.06, 0.72, 0]);
  box(body, [0.14, 0.62, 0.9], COLORS.chest, [0.93, 0.62, 0]);
  for (const x of [-0.62, 0.6]) {
    for (const z of [-0.36, 0.36]) box(group, [0.3, 0.34, 0.3], COLORS.furDark, [x, 0.17, z]);   // stubby legs
  }

  // The big boxy head
  const head = new THREE.Group();
  head.position.set(1.05, 1.28, 0);
  group.add(head);
  box(head, [1.0, 0.8, 0.9], COLORS.fur, [0, 0, 0]);
  box(head, [0.46, 0.62, 0.8], COLORS.furLight, [0.66, -0.07, 0]);   // snout
  box(head, [0.06, 0.16, 0.44], COLORS.nose, [0.9, 0.12, 0]);         // nose
  box(head, [0.04, 0.04, 0.22], COLORS.nose, [0.9, -0.22, 0]);        // little mouth
  const eyes = [];
  const ears = [];
  for (const side of [-1, 1]) {
    const eye = new THREE.Group();
    eye.position.set(0.28, 0.14, side * 0.455);
    box(eye, [0.15, 0.17, 0.03], COLORS.eye, [0, 0, 0]);
    box(eye, [0.05, 0.05, 0.02], "#ffffff", [0.03, 0.04, side * 0.02]);   // shine
    head.add(eye);
    eyes.push(eye);
    box(head, [0.2, 0.1, 0.02], COLORS.cheek, [0.5, -0.12, side * 0.455]);   // rosy cheeks
    const ear = new THREE.Group();
    ear.position.set(-0.3, 0.42, side * 0.3);
    box(ear, [0.2, 0.2, 0.14], COLORS.furDark, [0, 0.08, 0]);
    head.add(ear);
    ears.push(ear);
  }

  function update(time) {
    body.scale.y = 1 + Math.sin(time * 1.8) * 0.012;                 // slow breathing
    head.rotation.z = Math.sin(time * 0.9) * 0.035;                   // a lazy nod
    head.position.y = 1.28 + Math.sin(time * 1.8) * 0.01;
    const blink = time % 4.2 < 0.13 ? 0.12 : 1;                       // blink every few seconds
    for (const eye of eyes) eye.scale.y = blink;
    const twitch = time % 6.5 < 0.25 ? Math.sin(time * 40) * 0.25 : 0; // an ear flick now and then
    for (const ear of ears) ear.rotation.x = twitch;
  }
  update(0);

  return { group, update };
}
