import { useEffect, useRef, useState } from "react";
import "./Mascot.css";

// Cascade's mascot: the chunky low-poly 3D frog from "How it works", made in Blender (frontend/blender/frog.py).
//   variant="full" - the whole frog, idling: breathing, blinking, puffing its throat, and a little hop now and then
//   variant="head" - a still picture of just its head (for small badges, like next to "AI Assistant")
//   size           - width in pixels
// The 3D code downloads on its own, after the page shows. It's decoration, so screen readers skip it.
// If the device can't draw 3D, the space just stays empty.
function Mascot({ variant = "full", size = 96, className = "" }) {
  const holderRef = useRef(null);
  const [headPicture, setHeadPicture] = useState(null);
  const height = variant === "head" ? size : Math.round(size * 0.8);

  useEffect(() => {
    let stop = null;
    let cancelled = false;
    const holder = holderRef.current;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    import("../features/landing3d/mascotScene").then(({ createMascotScene, mascotHeadPicture }) => {
      if (cancelled) return;
      try {
        if (variant === "head") {
          mascotHeadPicture(size * 2)   // drawn at double size so it stays sharp
            .then((picture) => { if (!cancelled) setHeadPicture(picture); })
            .catch(() => {});
          return;
        }
        // A new canvas each time: once a canvas's 3D is shut down, it can't be started again
        const canvas = document.createElement("canvas");
        canvas.className = "mascot-canvas";
        holder?.append(canvas);
        stop = createMascotScene(canvas, { still });
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
    <span className={`mascot mascot-${variant} ${className}`} style={{ width: size, height }} aria-hidden="true">
      {variant === "head"
        ? headPicture && <img src={headPicture} alt="" width={size} height={size} />
        : <span ref={holderRef} className="mascot-holder" />}
    </span>
  );
}

export default Mascot;
