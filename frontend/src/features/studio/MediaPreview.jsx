import { useEffect, useState } from "react";
import Modal from "../../components/ui/Modal";
import Spinner from "../../components/ui/Spinner";
import useApi from "../../api/useApi";

// Watch a clip (or the original video) big, in a pop-up.
//   item - { title, path } for a video on the server, or { title, file } for one picked but not uploaded yet
// Server videos need the sign-in token, so we download them first and play the downloaded copy.
// The copy is thrown away when the pop-up closes.
function MediaPreview({ item, onClose }) {
  const api = useApi();
  const [url, setUrl] = useState(null);
  const [error, setError] = useState(null);
  const [audio, setAudio] = useState(false);

  useEffect(() => {
    let active = true;
    let objectUrl = null;
    const load = item.file ? Promise.resolve(item.file) : api.getMedia(item.path);
    load
      .then((blob) => {
        setAudio(blob.type.startsWith('audio/') || /\.(mp3|wav|m4a|flac)$/i.test(item.file?.name || ''));
        objectUrl = URL.createObjectURL(blob);
        if (active) setUrl(objectUrl);
      })
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [item, api]);

  return (
    <Modal title={item.title} onClose={onClose}>
      {error ? (
        <p role="alert">{error}</p>
      ) : url ? (
        audio ? <audio aria-label="Audio preview" src={url} controls autoPlay style={{width:'100%'}} />
          : <video className="studio-preview-video" src={url} controls autoPlay playsInline />
      ) : (
        <div className="studio-preview-loading"><Spinner label="Loading video" /> Loading…</div>
      )}
    </Modal>
  );
}

export default MediaPreview;
