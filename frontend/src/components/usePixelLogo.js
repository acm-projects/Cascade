import { useEffect, useState } from "react";
import logo from "../assets/icons/cascade-logo.svg";

// The Cascade logo as pixel art, for the pixel-art parts of the app (the waterfall page change, the top bar).
// The logo is drawn small (grid x grid squares), each square is made fully solid or fully clear, and its colour
// is snapped to the nearest of the logo's own main colours, so there are no soft in-between edges, and the
// squares along the edge are drawn in the outline colour (navy), so the outline survives even when small.
// Show it with CSS image-rendering: pixelated, at a size that's a whole multiple of the grid
// (38px with grid 19 = 2px squares), so every square is the same size.
//
//   const src = usePixelLogo(19);   // a picture URL; the normal logo for the moment before it's made
//
// Each grid size is made once and shared.
const made = new Map();   // grid -> Promise of the picture URL

// The most common colours in the logo, drawn full size (only fully solid pixels count)
function mainColors(image, count) {
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(image, 0, 0, size, size);
  const data = context.getImageData(0, 0, size, size).data;
  const counts = new Map();
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 250) continue;
    const key = `${data[i] >> 4},${data[i + 1] >> 4},${data[i + 2] >> 4}`;
    const entry = counts.get(key) ?? { n: 0, rgb: [data[i], data[i + 1], data[i + 2]] };
    entry.n += 1;
    counts.set(key, entry);
  }
  return [...counts.values()].sort((a, b) => b.n - a.n).slice(0, count).map((entry) => entry.rgb);
}

function makePixelLogo(grid) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = grid;
      canvas.height = grid;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      context.drawImage(image, 0, 0, grid, grid);
      const picture = context.getImageData(0, 0, grid, grid);
      const data = picture.data;
      // the logo's main colours, read from a full-size drawing (in the tiny one the thin navy outline is
      // mostly blended away, so it wouldn't make the list)
      const palette = mainColors(image, 5);
      const darkest = palette.reduce((a, b) => (a[0] + a[1] + a[2] <= b[0] + b[1] + b[2] ? a : b));
      const solid = (x, y) => x >= 0 && y >= 0 && x < grid && y < grid && data[(y * grid + x) * 4 + 3] >= 110;
      const edge = [];   // solid squares that touch the see-through background
      for (let y = 0; y < grid; y += 1) {
        for (let x = 0; x < grid; x += 1) {
          if (solid(x, y) && !(solid(x - 1, y) && solid(x + 1, y) && solid(x, y - 1) && solid(x, y + 1))) edge.push((y * grid + x) * 4);
        }
      }
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] < 110) { data[i + 3] = 0; continue; }
        let best = palette[0];
        let bestDistance = Infinity;
        for (const rgb of palette) {
          const distance = (rgb[0] - data[i]) ** 2 + (rgb[1] - data[i + 1]) ** 2 + (rgb[2] - data[i + 2]) ** 2;
          if (distance < bestDistance) { bestDistance = distance; best = rgb; }
        }
        [data[i], data[i + 1], data[i + 2], data[i + 3]] = [...best, 255];
      }
      // the edge squares become the outline colour (navy), so the logo keeps its outline at any size
      for (const i of edge) [data[i], data[i + 1], data[i + 2]] = darkest;
      context.putImageData(picture, 0, 0);
      resolve(canvas.toDataURL());
    };
    image.onerror = () => resolve(logo);
    image.src = logo;
  });
}

function pixelLogo(grid) {
  if (!made.has(grid)) {
    const entry = { src: null, ready: null };
    entry.ready = makePixelLogo(grid).then((src) => { entry.src = src; return src; });
    made.set(grid, entry);
  }
  return made.get(grid);
}

// Start the common sizes as the app loads, so they're ready before they're first shown
if (typeof window !== "undefined") { pixelLogo(19); pixelLogo(24); }

export default function usePixelLogo(grid) {
  const entry = pixelLogo(grid);
  const [src, setSrc] = useState(entry.src);
  useEffect(() => {
    if (src) return undefined;
    let active = true;
    entry.ready.then((ready) => { if (active) setSrc(ready); });
    return () => { active = false; };
  }, [entry, src]);
  return src ?? logo;
}
