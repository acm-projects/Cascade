import { useEffect, useState } from "react";
import Modal from "../../components/ui/Modal";
import Spinner from "../../components/ui/Spinner";
import useApi from "../../api/useApi";
import { formatTime } from "../../utils/time";

// Watch a clip (or the original video) big, in a pop-up.
//   item - { title, path } for a video on the server, or { title, file } for one picked but not uploaded yet
//   clip - optional, for a clip: { start, end, explanation, prompt, position: "2 of 4", picked,
//          onTogglePick(), onPrevious(), onNext() } (onPrevious/onNext are missing at the ends of the list)
// ← / → move to the previous/next clip from the same prompt; Esc closes.
// Server videos need the sign-in token, so we download them first and play the downloaded copy.
// The copy is thrown away when the pop-up closes or shows another clip.
function MediaPreview({ item, clip, onClose }) {
  const api = useApi();
  const [loaded, setLoaded] = useState(null); // { key, url, audio } for the video that finished downloading
  const [error, setError] = useState(null);
  const { path, file } = item;
  const key = path ?? file?.name;

  useEffect(() => {
    let active = true;
    let objectUrl = null;
    const load = file ? Promise.resolve(file) : api.getMedia(path);
    load
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        const audio = blob.type.startsWith("audio/") || /\.(mp3|wav|m4a|flac)$/i.test(file?.name || "");
        if (active) setLoaded({ key, url: objectUrl, audio });
      })
      .catch((err) => active && setError({ key, message: err.message }));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api, path, file, key]);

  // ← / → between clips (not while the video's own controls have focus: there the arrows seek)
  const onPrevious = clip?.onPrevious;
  const onNext = clip?.onNext;
  useEffect(() => {
    function handleKey(event) {
      if (event.target.closest?.("video, audio, input, textarea")) return;
      if (event.key === "ArrowLeft" && onPrevious) onPrevious();
      else if (event.key === "ArrowRight" && onNext) onNext();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onPrevious, onNext]);

  const media = loaded?.key === key ? loaded : null;
  const failed = error?.key === key ? error.message : null;

  return (
    <Modal title={item.title} onClose={onClose} wide>
      {failed ? (
        <p role="alert">{failed}</p>
      ) : media ? (
        media.audio ? <audio aria-label="Audio preview" src={media.url} controls autoPlay style={{ width: "100%" }} />
          : <video className="studio-preview-video" src={media.url} controls autoPlay playsInline />
      ) : (
        <div className="studio-preview-loading"><Spinner label="Loading video" /> Loading…</div>
      )}

      {clip && (
        <>
          <div className="studio-preview-details">
            <span>From the original: <b>{formatTime(clip.start)} – {formatTime(clip.end)}</b></span>
            <span>Length: <b>{formatTime(clip.end - clip.start)}</b></span>
            {clip.prompt && <span>Prompt: <b>“{clip.prompt}”</b></span>}
          </div>
          {clip.explanation && <p className="studio-preview-why">{clip.explanation}</p>}
          {clip.referenceLabels?.length > 1 && <section className="studio-combination" aria-label="Combined clip context">
            <strong>Combines {clip.referenceLabels.map(ref => `Clip ${ref.label}`).join(' + ')}</strong>
            {clip.referenceMatches?.map(match => <p key={match.reference}>
              <b>Clip {clip.referenceLabels[match.reference - 1]?.label || match.reference}:</b> {match.explanation}
            </p>)}
          </section>}
          <div className="studio-preview-actions">
            <button type="button" className="btn btn-small" onClick={onPrevious} disabled={!onPrevious}
              aria-label="Previous clip" title="Previous clip (←)">←</button>
            <span className="studio-preview-count">Clip {clip.position}</span>
            <button type="button" className={`btn btn-small ${clip.picked ? "" : "btn-primary"}`} onClick={clip.onTogglePick}
              title="Picked clips go to the Editor and guide your next prompt">
              {clip.picked ? "Picked ✓ (unpick)" : "Pick clip"}
            </button>
            <button type="button" className="btn btn-small" onClick={onNext} disabled={!onNext}
              aria-label="Next clip" title="Next clip (→)">→</button>
          </div>
        </>
      )}
    </Modal>
  );
}

export default MediaPreview;
