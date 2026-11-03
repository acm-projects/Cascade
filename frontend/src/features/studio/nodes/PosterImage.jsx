import { useState } from "react";

// A still from the source video behind a poster's ▶ (GET /api/projects/{id}/source/{job}/frame).
// Audio, or a frame that can't be made, keeps the plain green poster.
//   src - the frame URL, or nothing for no picture
function PosterImage({ src }) {
  const [failed, setFailed] = useState(null); // the src that failed to load
  const [loaded, setLoaded] = useState(null); // the src that finished loading: it fades in instead of popping
  if (!src || failed === src) return null;
  return <img className={`studio-poster-image${loaded === src ? " is-loaded" : ""}`} src={src} alt="" draggable={false}
    onLoad={() => setLoaded(src)} onError={() => setFailed(src)} />;
}

export default PosterImage;
