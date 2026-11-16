import { useEffect, useState } from "react";
import logo from "../assets/icons/cascade-logo.svg";

// The Cascade logo as pixel art, for the pixel-art parts of the app (the waterfall page change, the top bar).
// The logo is drawn small (grid x grid squares), each square is made fully solid or fully clear, and its colour
// is snapped to the nearest of the logo's own main colours, so there are no soft in-between edges.
// Show it with CSS image-rendering: pixelated, at a size that's a whole multiple of the grid
// (38px with grid 19 = 2px squares), so every square is the same size.
//
//   const src = usePixelLogo(19);   // a picture URL; the normal logo for the moment before it's made
//
// Each grid size is made once and shared.
const made = new Map();   // grid -> Promise of the picture URL

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
      // the logo's main colours: the most common ones among the fully solid squares
      const counts = new Map();
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] < 250) continue;
        const key = `${data[i] >> 4},${data[i + 1] >> 4},${data[i + 2] >> 4}`;
        const entry = counts.get(key) ?? { n: 0, rgb: [data[i], data[i + 1], data[i + 2]] };
        entry.n += 1;
        counts.set(key, entry);
      }
      const palette = [...counts.values()].sort((a, b) => b.n - a.n).slice(0, 5).map((entry) => entry.rgb);
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
