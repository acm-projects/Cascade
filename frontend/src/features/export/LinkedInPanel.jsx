import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";

const ACTIVE = ["Rendering", "Uploading", "Processing", "Publishing"];

export default function LinkedInPanel({ projectId, clip, post, state }) {
  const api = useApi();
  const [connection, setConnection] = useState(null);
  const [upload, setUpload] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submission = useRef(null);
  const working = ACTIVE.includes(upload?.status);

  useEffect(() => {
    let active = true;
    api.getLinkedinConnection(projectId).then((data) => active && setConnection(data))
      .catch((err) => active && setConnection({ error: err.message }));
    api.getLinkedinStatus(projectId, clip.job_id, clip.clip_index).then((data) => active && setUpload(data))
      .catch((err) => active && setError(err.message));
    return () => { active = false; };
  }, [api, projectId, clip.job_id, clip.clip_index]);

  useEffect(() => {
    if (!working) return;
    let active = true;
    const timer = setTimeout(() => {
      api.getLinkedinStatus(projectId, clip.job_id, clip.clip_index)
        .then((data) => { if (active) { setUpload(data); setError(""); } })
        .catch((err) => { if (active) { setError(err.message); setUpload((current) => ({ ...current })); } });
    }, 3000);
    return () => { active = false; clearTimeout(timer); };
  }, [working, upload, error, api, projectId, clip.job_id, clip.clip_index]);

  async function refresh() {
    try { setConnection(await api.getLinkedinConnection(projectId)); }
    catch (err) { setConnection({ error: err.message }); }
  }

  async function connect() {
    const popup = window.open("about:blank", "_blank");
    if (!popup) { setError("Allow popups for Cascade, then connect LinkedIn again."); return; }
    popup.opener = null;
    try {
      const { url } = await api.connectLinkedin(projectId);
      popup.location.href = url;
      setError("");
    } catch (err) { popup.close(); setError(err.message); }
  }

  async function publish() {
    if (busy || working) return;
    if (upload?.status === "Failed" && !upload.video && !upload.post_attempted) submission.current = null;
    submission.current ??= crypto.randomUUID();
    setBusy(true); setError("");
    try {
      setUpload(await api.publishLinkedin(projectId, clip.job_id, clip.clip_index, {
        title: (post?.name || clip.title || "Cascade clip").slice(0, 160),
        caption: post?.caption ?? "",
        hashtags: post?.hashtags ?? [],
        edit: state,
        submission_id: submission.current,
      }));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  const retained = !!upload?.video || !!upload?.post_attempted || upload?.status === "Published";
  return (
    <div className="export-post">
      <h3 className="export-social-title">LinkedIn</h3>
      {!connection ? <Spinner label="Checking LinkedIn" /> : <>
        <p className="export-social-note">
          {connection.connected ? <>Connected: <b>{connection.profile}</b></> : connection.error || "Connect your LinkedIn personal profile."}
        </p>
        <div className="export-post-actions">
          <Button size="sm" onClick={connect} disabled={busy || working || connection.configured === false}>
            {connection.connected ? "Reconnect LinkedIn" : "Connect LinkedIn"}
          </Button>
          <Button size="sm" variant="ghost" onClick={refresh}>Refresh connection</Button>
        </div>
        <p className="export-social-note">Publish the edited video as a public post on your personal profile.</p>
        <Button size="sm" variant="primary" onClick={publish} disabled={!connection.connected || !state || busy || working || retained}>
          {busy ? "Starting…" : "Publish to LinkedIn"}
        </Button>
      </>}
      {error && <p className="export-upload-status failed" role="alert">{error}</p>}
      {upload && upload.status !== "Ready" && <p className={`export-upload-status${upload.status === "Failed" ? " failed" : ""}`} role="status">
        {working && <Spinner size={14} label="Publishing" />} {upload.status}
        {upload.error && `: ${upload.error}`}
        {upload.url && <> · <a href={upload.url} target="_blank" rel="noreferrer">Open on LinkedIn</a></>}
      </p>}
    </div>
  );
}
