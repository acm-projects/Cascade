import { useEffect, useRef, useState } from "react";
import "./Capybara.css";

// Cascade's mascot: a chunky low-poly 3D capybara, made in Blender (frontend/blender/capybara.py).
//   variant="full" - the whole capybara, idling: breathing, blinking, ear flicks (for empty spaces)
//   variant="head" - a still picture of just its head (for small badges, like next to "AI Assistant")
//   size           - width in pixels
// The 3D code downloads on its own, after the page shows. It's decoration, so screen readers skip it.
// If the device can't draw 3D, the space just stays empty.
function Capybara({ variant = "full", size = 96, className = "" }) {
  const holderRef = useRef(null);
  const [headPicture, setHeadPicture] = useState(null);
  const height = variant === "head" ? size : Math.round(size * 0.8);

  useEffect(() => {
    let stop = null;
    let cancelled = false;
    const holder = holderRef.current;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    import("../features/landing3d/mascotScene").then(({ createMascotScene, capybaraHeadPicture }) => {
      if (cancelled) return;
      try {
        if (variant === "head") {
          capybaraHeadPicture(size * 2)   // drawn at double size so it stays sharp
            .then((picture) => { if (!cancelled) setHeadPicture(picture); })
            .catch(() => {});
          return;
        }
        // A new canvas each time: once a canvas's 3D is shut down, it can't be started again
        const canvas = document.createElement("canvas");
        canvas.className = "capybara-canvas";
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
    <span className={`capybara capybara-${variant} ${className}`} style={{ width: size, height }} aria-hidden="true">
      {variant === "head"
        ? headPicture && <img src={headPicture} alt="" width={size} height={size} />
        : <span ref={holderRef} className="capybara-holder" />}
    </span>
  );
}

export default Capybara;
