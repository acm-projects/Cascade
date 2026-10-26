import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/ToastContext";

const WORKING = ["Rendering", "Uploading", "Processing", "Verifying"];
const POLL_MS = 3000;

// Upload one clip to YouTube (backend/social_youtube.py, Manila).
// The server renders the clip with its edits, then uploads it. Needs Google keys in the server's .env.
//   post  - { name, caption, hashtags } from PostPanel: used as the YouTube title/description
//   state - the clip's edit (draft state)
// Use with key={clip key}.
function YouTubePanel({ projectId, clip, post, state }) {
  const api = useApi();
  const toast = useToast();
  const [connection, setConnection] = useState(null); // { connected, channel } or { error }
  const [privacy, setPrivacy] = useState("private");
  const [upload, setUpload] = useState(null);         // { status, url?, error? }
  const [busy, setBusy] = useState(false);
  const submission = useRef(null);

  useEffect(() => {
    let active = true;
    api.getYoutubeConnection(projectId)
      .then((result) => active && setConnection(result))
      .catch((err) => active && setConnection({ error: err }));
    api.getYoutubeStatus(projectId, clip.job_id, clip.clip_index)
      .then((result) => active && setUpload(result))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [api, projectId, clip.job_id, clip.clip_index]);

  // While YouTube is rendering/uploading/processing, check again every few seconds
  const working = upload && WORKING.includes(upload.status);
  useEffect(() => {
    if (!working) return;
    const timer = setTimeout(() => {
      api.getYoutubeStatus(projectId, clip.job_id, clip.clip_index).then(setUpload).catch(() => {});
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [working, upload, api, projectId, clip.job_id, clip.clip_index]);

  async function connect() {
    try {
      const { url } = await api.connectYoutube(projectId);
      window.open(url, "_blank", "noopener"); // Google's sign-in; come back and press "Check again"
    } catch (err) {
      toast.show(err.message, "error");
    }
  }

  function checkAgain() {
    api.getYoutubeConnection(projectId).then(setConnection).catch((err) => setConnection({ error: err }));
  }

  async function publish() {
    // Same submission id if you press again after a hiccup: the backend never uploads twice
    submission.current = submission.current ?? crypto.randomUUID();
    setBusy(true);
    try {
      const result = await api.publishYoutube(projectId, clip.job_id, clip.clip_index, {
        title: (post?.name || clip.title || "Cascade clip").slice(0, 100),
        description: post?.caption ?? "",
        hashtags: post?.hashtags ?? [],
        privacy,
        submission_id: submission.current,
        edit: state,
      });
      setUpload(result);
    } catch (err) {
      toast.show(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  let content;
  if (!connection) {
    content = <Spinner label="Checking YouTube" />;
  } else if (connection.error) {
    content = (
      <p className="export-social-note">
        YouTube isn't set up on this server yet. Add <code>GOOGLE_YOUTUBE_CLIENT_ID</code> and{" "}
        <code>GOOGLE_YOUTUBE_CLIENT_SECRET</code> to <code>.env</code> (ask Manila), then restart the backend.
      </p>
    );
  } else if (!connection.connected) {
    content = (
      <div className="export-post-actions">
        <Button size="sm" variant="primary" onClick={connect}>Connect YouTube</Button>
        <Button size="sm" variant="ghost" onClick={checkAgain}>Check again</Button>
      </div>
    );
  } else {
    content = (
      <>
        <p className="export-social-note">Connected: <b>{connection.channel}</b></p>
        <label className="export-post-field">
          Visibility
          <select value={privacy} onChange={(e) => setPrivacy(e.target.value)} disabled={busy || working}>
            <option value="private">Private</option>
            <option value="unlisted">Unlisted</option>
            <option value="public">Public</option>
          </select>
        </label>
        <Button size="sm" variant="primary" onClick={publish} disabled={busy || working || !state}>
          {busy ? "Starting…" : "Upload to YouTube"}
        </Button>
      </>
    );
  }

  return (
    <div className="export-post">
      <h3 className="export-social-title">▶️ YouTube</h3>
      {content}
      {upload && upload.status !== "Ready" && (
        <p className={`export-upload-status${upload.status === "Failed" ? " failed" : ""}`} role="status">
          {working && <Spinner size={14} label="Uploading" />} {upload.status}
          {upload.error && `: ${upload.error}`}
          {upload.url && <> · <a href={upload.url} target="_blank" rel="noreferrer">Open on YouTube</a></>}
        </p>
      )}
    </div>
  );
}

export default YouTubePanel;
