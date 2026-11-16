import { useRef, useState } from "react";
import Modal from "./ui/Modal";
import Spinner from "./ui/Spinner";
import { MEDIA_ACCEPT, VIDEO_ACCEPT, isSupportedMedia, isVideoFile } from "../utils/media";
import "./NewProjectModal.css";
import Icon from "./ui/Icon";

const MAX_NAME = 100;          // the backend's limit
const BIG_FILE = 2 * 1024 ** 3; // over 2 GB: warn (uploads still work, they just take a while)

// 1572864 -> "1.5 MB"
function fileSize(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// The "+ New Project" pop-up: name the project, pick how to start, and (optionally) pick its video.
//   "Find clips with AI": the video uploads in AI Studio together with your first prompt.
//   "Edit my own clip":   the video is required and goes straight into the Editor (no picking).
//   onCreate(name, file, mode) - mode is "studio" or "editor"; throws to show an error here
//   onClose()
function NewProjectModal({ onCreate, onClose }) {
  const [name, setName] = useState("");
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [mode, setMode] = useState("studio");
  const fileInput = useRef(null);
  const ownClip = mode === "editor";

  function choose(picked) {
    if (!picked) return;
    if (!isSupportedMedia(picked) || (ownClip && !isVideoFile(picked))) {
      setError(ownClip ? "Choose a video: MP4, MOV, WebM, MKV or AVI." : "Choose MP4, MOV, WebM, MKV, MP3, WAV, M4A, or FLAC audio/video.");
      return;
    }
    setError(null);
    setFile(picked);
  }

  async function submit(event) {
    event.preventDefault();
    if (!name.trim()) {
      setError("Give your project a name.");
      return;
    }
    if (ownClip && !file) {
      setError("Choose the video you want to edit.");
      return;
    }
    if (ownClip && !isVideoFile(file)) {
      setError("Choose a video: MP4, MOV, WebM, MKV or AVI.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await onCreate(name.trim(), file, mode);
    } catch (err) {
      setError(`Couldn't create the project: ${err.message}`);
      setCreating(false);
    }
  }

  return (
    <Modal title="New project" onClose={() => !creating && onClose()}>
      <form className="new-project" onSubmit={submit}>
        <label className="new-project-field">
          <span>Project name</span>
          <input autoFocus value={name} maxLength={MAX_NAME} placeholder="e.g. Podcast episode 12"
            onChange={(e) => setName(e.target.value)} disabled={creating} />
        </label>

        <div className="new-project-modes" role="radiogroup" aria-label="How do you want to start?">
          {[
            ["studio", "sparkles", "Find clips with AI", "Upload a long video and let AI pick the best moments"],
            ["editor", "scissors", "Edit my own clip", "Skip the AI picking and go straight to the Editor"],
          ].map(([id, icon, label, hint]) => (
            <button key={id} type="button" role="radio" aria-checked={mode === id} disabled={creating}
              className={`new-project-mode${mode === id ? " active" : ""}`}
              onClick={() => { setMode(id); setError(null); }}>
              <Icon name={icon} size={20} />
              <strong>{label}</strong>
              <span>{hint}</span>
            </button>
          ))}
        </div>

        <div
          className={`new-project-drop${dragging ? " dragging" : ""}${file ? " has-file" : ""}`}
          role="button" tabIndex={0}
          onClick={() => !creating && fileInput.current.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !creating && fileInput.current.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!creating) choose(e.dataTransfer.files[0]);
          }}
        >
          {file ? (
            <>
              <strong><Icon name="film" /> {file.name}</strong>
              <span>{fileSize(file.size)} · click to change</span>
            </>
          ) : (
            <>
              <strong>Drag a video here or click to browse</strong>
              <span>{ownClip ? "Required: this is the clip you'll edit" : "Optional: you can also pick it on Studio Island"}</span>
            </>
          )}
          <input ref={fileInput} type="file" accept={ownClip ? VIDEO_ACCEPT : MEDIA_ACCEPT} hidden
            onChange={(e) => choose(e.target.files[0])} />
        </div>

        {file?.size > BIG_FILE && (
          <p className="new-project-warning">This file is over 2 GB, so uploading may take a while.</p>
        )}
        {creating && ownClip && <p className="new-project-warning" role="status">Uploading your clip and adding captions. Longer videos can take a minute.</p>}
        {error && <p className="new-project-error" role="alert">{error}</p>}

        <div className="new-project-actions">
          <button type="button" className="btn btn-ghost btn-small" onClick={onClose} disabled={creating}>Cancel</button>
          <button type="submit" className="btn btn-primary btn-small" disabled={creating}>
            {creating
              ? <><Spinner size={14} label="Creating" /> {ownClip ? "Uploading and preparing…" : "Creating…"}</>
              : ownClip ? "Create and open Editor" : "Create project"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default NewProjectModal;
