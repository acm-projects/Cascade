import { useEffect, useRef } from "react";
import { createIslandScene } from "./islandScene";
import { createUnderwaterScene } from "./underwaterScene";
import { createBeachScene } from "./beachScene";

// The 3D world, filling its parent: the island (Landing, Sign-in), under the sea (Projects) or the beach (AI Studio's canvas).
// If the device can't draw 3D, nothing is added and the plain sea color stays.
function IslandCanvas({ framing }) {
  const holderRef = useRef(null);

  useEffect(() => {
    const holder = holderRef.current;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // A new canvas each time: once a canvas's 3D is shut down, it can't be started again
    const canvas = document.createElement("canvas");
    canvas.className = "iso-world-canvas";
    holder.append(canvas);
    let stop = null;
    try {
      const create = { underwater: createUnderwaterScene, beach: createBeachScene }[framing];
      stop = create ? create(canvas, { still }) : createIslandScene(canvas, { still, framing });
    } catch {
      canvas.remove();
    }
    return () => {
      stop?.();
      canvas.remove();
    };
  }, [framing]);

  return <div ref={holderRef} className="iso-world-holder" />;
}

export default IslandCanvas;
