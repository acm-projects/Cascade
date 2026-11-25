import { useRef, useState } from "react";
import Modal from "./ui/Modal";
import Spinner from "./ui/Spinner";
import { MEDIA_ACCEPT, VIDEO_ACCEPT, isSupportedMedia, isVideoFile } from "../utils/media";
import "./NewProjectModal.css";
import Icon from "./ui/Icon";

const MAX_NAME = 100;          // the backend's limit
const MAX_FILES = 10;          // the backend joins up to 10 files into one source

// 1572864 -> "1.5 MB"
function fileSize(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// The "+ New Project" pop-up: name the project, pick how to start, and (optionally) pick its video.
//   "Find clips with AI": pick one or more files; they upload in AI Studio together with your first prompt
//                         (several are joined end to end into one source).
//   "Edit my own clip":   one video is required and goes straight into the Editor (no picking).
//   onCreate(name, files, mode) - files is an array; mode is "studio" or "editor"; throws to show an error here
//   onClose()
function NewProjectModal({ onCreate, onClose }) {
  const [name, setName] = useState("");
  const [files, setFiles] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [mode, setMode] = useState("studio");
  const fileInput = useRef(null);
  const ownClip = mode === "editor";

  // "Edit my own clip" takes one video, so a new pick replaces it. "Find clips with AI" adds to the list.
  function choose(picked) {
    const list = Array.from(picked || []);
    if (!list.length) return;
    const ok = list.filter((f) => isSupportedMedia(f) && (!ownClip || isVideoFile(f)));
    const typeError = ownClip ? "Choose a video: MP4, MOV, WebM, MKV or AVI." : "Choose MP4, MOV, WebM, MKV, MP3, WAV, M4A, or FLAC audio/video.";
    if (!ok.length) {
      setError(typeError);
      return;
    }
    if (ownClip) {
      setError(list.length > 1 ? "Edit my own clip takes one video. The first one was used." : null);
      setFiles([ok[0]]);
      return;
    }
    const key = (f) => [f.name, f.size, f.lastModified].join("|");
    const next = [...files, ...ok.filter((f) => !files.some((c) => key(c) === key(f)))];
    setError(ok.length < list.length ? `Some files were skipped. ${typeError}`
      : next.length > MAX_FILES ? `Up to ${MAX_FILES} files can be joined. The extra ones were left out.` : null);
    setFiles(next.slice(0, MAX_FILES));
  }

  function switchMode(id) {
    setMode(id);
    setError(null);
    if (id === "editor" && files.length > 1) setFiles(files.slice(0, 1)); // one video for "Edit my own clip"
  }

  async function submit(event) {
    event.preventDefault();
    if (!name.trim()) {
      setError("Give your project a name.");
      return;
    }
    if (ownClip && !files.length) {
      setError("Choose the video you want to edit.");
      return;
    }
    if (ownClip && !isVideoFile(files[0])) {
      setError("Choose a video: MP4, MOV, WebM, MKV or AVI.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await onCreate(name.trim(), files, mode);
    } catch (err) {
      setError(`Couldn't create the project: ${err.message}`);
      setCreating(false);
    }
  }

  return (
    <Modal title="New project" className="new-project-modal" onClose={() => !creating && onClose()}>
      <form className="new-project" onSubmit={submit}>
        <label className="new-project-field">
          <span>Project name</span>
          <input autoFocus value={name} maxLength={MAX_NAME} placeholder="e.g. Podcast episode 12"
            onChange={(e) => setName(e.target.value)} disabled={creating} />
        </label>

        <div className="new-project-modes" role="radiogroup" aria-label="How do you want to start?">
          {[
            ["studio", "sparkles", "Find clips with AI"],
            ["editor", "scissors", "Edit my own clip"],
          ].map(([id, icon, label]) => (
            <button key={id} type="button" role="radio" aria-checked={mode === id} disabled={creating}
              className={`new-project-mode${mode === id ? " active" : ""}`}
              onClick={() => switchMode(id)}>
              <Icon name={icon} size={20} />
              <strong>{label}</strong>
            </button>
          ))}
        </div>

        <div
          className={`new-project-drop${dragging ? " dragging" : ""}${files.length ? " has-file" : ""}`}
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
            if (!creating) choose(e.dataTransfer.files);
          }}
        >
          {files.length === 1 ? (
            <>
              <strong><Icon name="film" /> {files[0].name}</strong>
              <span>{fileSize(files[0].size)} · click to {ownClip ? "change" : "add more"}</span>
            </>
          ) : files.length ? (
            <>
              <strong><Icon name="film" /> {files.length} files · {fileSize(files.reduce((n, f) => n + f.size, 0))}</strong>
              <span>Joined in this order · click to add more</span>
            </>
          ) : (
            <>
              <strong>{ownClip ? "Drag a video here or click to browse" : "Drag videos here or click to browse"}</strong>
              {ownClip ? <span>Required: this is the clip you'll edit</span> : <span>You can pick several files</span>}
            </>
          )}
          <input ref={fileInput} type="file" accept={ownClip ? VIDEO_ACCEPT : MEDIA_ACCEPT} hidden multiple={!ownClip}
            onChange={(e) => { choose(e.target.files); e.target.value = ""; }} />
        </div>

        {files.length > 1 && (
          <ol className="new-project-files">
            {files.map((f, index) => (
              <li key={`${f.name}|${f.size}|${f.lastModified}`}>
                <span title={f.name}>{f.name}</span>
                <span className="new-project-file-size">{fileSize(f.size)}</span>
                <button type="button" className="new-project-file-remove" aria-label={`Remove ${f.name}`} title="Remove"
                  disabled={creating} onClick={() => setFiles(files.filter((_, i) => i !== index))}>
                  <Icon name="close" />
                </button>
              </li>
            ))}
          </ol>
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
