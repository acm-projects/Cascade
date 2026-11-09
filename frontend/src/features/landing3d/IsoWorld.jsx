import { lazy, Suspense } from "react";
import "./IsoWorld.css";

// The 3D library is big, so it's downloaded only on pages that use it. The sea color shows until it's ready.
const IslandCanvas = lazy(() => import("./IslandCanvas"));

// The 3D island and its surroundings, behind a page. The page needs: position: relative; isolation: isolate.
//   framing="hero"     - big, on the right, next to the words (Landing)
//   framing="backdrop"   - low on the screen, behind the page's content (Sign-in)
//   framing="underwater" - under the sea below the island, behind the page's content (Projects)
//   framing="lake"       - the lake at the foot of a waterfall, behind the AI Studio canvas
function IsoWorld({ framing = "hero" }) {
  return (
    <div className={`iso-world iso-world-${framing}`} aria-hidden="true">
      <Suspense fallback={null}>
        <IslandCanvas framing={framing} />
      </Suspense>
    </div>
  );
}

export default IsoWorld;
