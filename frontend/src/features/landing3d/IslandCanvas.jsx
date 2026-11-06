import { useEffect, useRef } from "react";
import { createIslandScene } from "./islandScene";

// The 3D island, filling its parent. If the device can't draw 3D, nothing is added and the page's sky stays behind the words.
function IslandCanvas() {
  const holderRef = useRef(null);

  useEffect(() => {
    const holder = holderRef.current;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // A new canvas each time: once a canvas's 3D is shut down, it can't be started again
    const canvas = document.createElement("canvas");
    canvas.className = "landing-3d-canvas";
    holder.append(canvas);
    let stop = null;
    try {
      stop = createIslandScene(canvas, { still });
    } catch {
      canvas.remove();
    }
    return () => {
      stop?.();
      canvas.remove();
    };
  }, []);

  return <div ref={holderRef} className="landing-3d" aria-hidden="true" />;
}

export default IslandCanvas;
