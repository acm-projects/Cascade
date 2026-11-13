import * as THREE from "three";
import { COLORS, lumpyBall, makeRandom, waterTexture } from "../features/landing3d/islandScene";

// The 3D waterfall for the page change between AI Studio, the Editor and Export (WaterfallCurtain.jsx).
// Layers of curved water sheets (bulging toward you, lit so they have shape) pour down at different
// depths and speeds, with chunky foam churning along their leading edge, droplets flying past at
// different distances, and mist rolling up from the bottom.
//
// createCurtainScene(canvas) returns
//   stop()

export function createCurtainScene(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.set(0, 0, 10);
  scene.add(new THREE.HemisphereLight("#f2fdff", "#0b4f7a", 1.6));
  const sun = new THREE.DirectionalLight("#ffffff", 2.2);
  sun.position.set(-4, 6, 8);
  scene.add(sun);

  const random = makeRandom(7);
  const curtain = new THREE.Group();   // everything that pours down and falls away together
  scene.add(curtain);
  const textures = [];
  let width = 1;
  let height = 1;
  let viewHeight = 9.3;
  let viewWidth = 9.3;
  let sheetHeight = 12;

  // The sheets: wide planes bent so the middle bulges toward you, at three depths
  const layers = [
    { z: -1.6, tint: "#2b8fc4", speed: 0.55, opacity: 1 },
    { z: -0.7, tint: "#5fc8e6", speed: 0.85, opacity: 0.9 },
    { z: 0.2, tint: "#bdf0fb", speed: 1.25, opacity: 0.55 },
  ];
  const sheets = [];
  const foam = [];
  let droplets = null;
  const dropletData = [];
  const mist = [];

  function build() {
    for (const sheet of sheets) { curtain.remove(sheet); sheet.geometry.dispose(); }
    for (const puff of foam) curtain.remove(puff.mesh);
    sheets.length = 0;
    foam.length = 0;
    const aspect = width / height;
    viewHeight = 2 * camera.position.z * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    viewWidth = viewHeight * aspect;
    sheetHeight = viewHeight * 1.25;
    for (const layer of layers) {
      const sheetWidth = viewWidth * 1.5;
      const geometry = new THREE.PlaneGeometry(sheetWidth, sheetHeight, 60, 24);
      const position = geometry.attributes.position;
      for (let i = 0; i < position.count; i += 1) {
        const x = position.getX(i);
        // bulge out in the middle, with a few ripples across so it isn't one smooth curve
        position.setZ(i, -(x * x) / (sheetWidth * 1.4) + Math.sin(x * 1.7) * 0.12 + Math.sin(x * 4.3) * 0.05);
      }
      geometry.computeVertexNormals();
      const texture = waterTexture(random, sheetWidth / 3, sheetHeight / 3, false);
      textures.push({ texture, speed: layer.speed });
      const sheet = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
        map: texture, color: layer.tint, roughness: 0.2, metalness: 0.1, emissive: "#0b6f86", emissiveIntensity: 0.25,
        transparent: layer.opacity < 1, opacity: layer.opacity, side: THREE.DoubleSide, depthWrite: layer.opacity === 1,
      }));
      sheet.position.z = layer.z;
      curtain.add(sheet);
      sheets.push(sheet);
    }
    // Anchor foam to the visible canvas edges, not the oversized water planes.
    // Account for perspective at each puff's depth so both rows stay in view.
    const foamMaterial = new THREE.MeshStandardMaterial({
      color: COLORS.foam, emissive: COLORS.foam, emissiveIntensity: 0.65,
      roughness: 0.6, flatShading: true,
    });
    for (const edge of [-1, 1]) {
      const count = Math.ceil(viewWidth * 2.2);
      for (let i = 0; i < count; i += 1) {
        const size = 0.25 + random() * 0.35;
        const mesh = new THREE.Mesh(lumpyBall(size, random, 0.2, 1), foamMaterial);
        const z = 1.1 + random() * 0.4;
        const depthScale = (camera.position.z - z) / camera.position.z;
        const x = (-0.55 + (i / Math.max(1, count - 1)) * 1.1) * viewWidth * depthScale;
        const y = edge * (viewHeight * depthScale / 2 - size * 0.4);
        mesh.position.set(x, y + (random() - 0.5) * 0.12, z);
        curtain.add(mesh);
        foam.push({ mesh, baseY: mesh.position.y, phase: random() * 6, speed: 3 + random() * 3 });
      }
    }
  }

  // Droplets flying down past you at different distances
  const DROPLETS = 220;
  droplets = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.06, 0), new THREE.MeshStandardMaterial({ color: "#eafcff", roughness: 0.2, flatShading: true }), DROPLETS);
  for (let i = 0; i < DROPLETS; i += 1) {
    dropletData.push({ x: (random() - 0.5) * 16, z: -1 + random() * 5, y: random(), speed: 0.35 + random() * 0.5, size: 0.25 + random() * 0.45 });
  }
  curtain.add(droplets);

  // Mist rolling up from the bottom of the screen (stays put while the water moves)
  for (let i = 0; i < 14; i += 1) {
    const puff = new THREE.Mesh(new THREE.IcosahedronGeometry(0.45 + random() * 0.4, 2),
      new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0, depthWrite: false }));
    scene.add(puff);
    mist.push({ mesh: puff, x: (random() - 0.5) * 14, phase: random() });
  }

  function resize() {
    width = canvas.clientWidth || window.innerWidth;
    height = canvas.clientHeight || window.innerHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    build();
  }

  const start = performance.now();
  let last = start;
  let frame = 0;
  const matrix = new THREE.Matrix4();

  function draw() {
    const now = performance.now();
    const time = (now - start) / 1000;
    const delta = Math.min(0.05, (now - last) / 1000);
    last = now;
    // CSS moves the opaque wrapper. Keep all depths fixed relative to it, so
    // perspective cannot make a back sheet peek out ahead of the front sheet.
    for (const { texture, speed } of textures) texture.offset.y = (texture.offset.y + delta * speed) % 1;
    for (const puff of foam) {
      const wave = Math.sin(time * puff.speed + puff.phase);
      puff.mesh.scale.setScalar(1 + wave * 0.25);
      puff.mesh.position.y = puff.baseY + wave * 0.08;
      puff.mesh.rotation.y = time * 0.5 + puff.phase;
    }
    dropletData.forEach((drop, i) => {
      const fall = (drop.y + time * drop.speed) % 1;
      matrix.makeScale(drop.size, drop.size * 4, drop.size);   // thin streaks of falling water
      matrix.setPosition(drop.x, sheetHeight / 2 - fall * sheetHeight, drop.z);
      droplets.setMatrixAt(i, matrix);
    });
    droplets.instanceMatrix.needsUpdate = true;
    for (const m of mist) {
      const p = (time * 0.25 + m.phase) % 1;
      m.mesh.position.set(m.x, -viewHeight / 2 + p * 2.2, 1.5);
      m.mesh.scale.setScalar(0.8 + p * 1.2);
      m.mesh.material.opacity = 0.22 * (1 - p);
    }
    renderer.render(scene, camera);
    frame = requestAnimationFrame(draw);
  }

  resize();
  window.addEventListener("resize", resize);
  draw();   // draw before the browser paints the moving sheet for the first time

  return {
    stop() {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      scene.traverse((object) => {
        object.geometry?.dispose();
        object.material?.map?.dispose();
        object.material?.dispose?.();
      });
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}
