import { useEffect, useRef, useState } from "react";
import "./Seahorse.css";

// Cassie, Cascade's seahorse: a chunky low-poly 3D model made in Blender (frontend/blender/seahorse.py).
//   variant="full" - the whole seahorse, floating: bobbing, swaying, fin fluttering, tail curling, blinking
//   variant="head" - a still picture of just her head (for small round badges, like Cassie's chat avatar)
//   size           - width in pixels
// The 3D code downloads on its own, after the page shows. It's decoration, so screen readers skip it.
// If the device can't draw 3D, the space just stays empty.
function Seahorse({ variant = "full", size = 120, className = "" }) {
  const holderRef = useRef(null);
  const [headPicture, setHeadPicture] = useState(null);
  const height = variant === "head" ? size : Math.round(size * 1.5);

  useEffect(() => {
    let stop = null;
    let cancelled = false;
    const holder = holderRef.current;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    import("../features/landing3d/seahorseScene").then(({ createSeahorseScene, seahorseHeadPicture }) => {
      if (cancelled) return;
      try {
        if (variant === "head") {
          seahorseHeadPicture(size * 2)   // drawn at double size so it stays sharp
            .then((picture) => { if (!cancelled) setHeadPicture(picture); })
            .catch(() => {});
          return;
        }
        // A new canvas each time: once a canvas's 3D is shut down, it can't be started again
        const canvas = document.createElement("canvas");
        canvas.className = "seahorse-canvas";
        holder?.append(canvas);
        stop = createSeahorseScene(canvas, { still });
      } catch {
        holder?.replaceChildren();
      }
    }).catch(() => {});
    return () => {
      cancelled = true;
      stop?.();
      holder?.replaceChildren();
    };
  }, [variant, size]);

  return (
    <span className={`seahorse seahorse-${variant} ${className}`} style={{ width: size, height }} aria-hidden="true">
      {variant === "head"
        ? headPicture && <img src={headPicture} alt="" width={size} height={size} />
        : <span ref={holderRef} className="seahorse-holder" />}
    </span>
  );
}

export default Seahorse;
