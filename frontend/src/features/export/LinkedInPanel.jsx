import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import Icon from "../../components/ui/Icon";
import { connectAndWait } from "./connectAndWait";

const ACTIVE = ["Rendering", "Uploading", "Processing", "Publishing"];

// Publish the edited clip as a public post on your LinkedIn profile, with one button: if LinkedIn isn't connected
// yet it opens LinkedIn's sign-in, waits for it, then publishes. Use with key={clip key}.
export default function LinkedInPanel({ projectId, clip, post, state }) {
  const api = useApi();
  const [connection, setConnection] = useState(null);
  const [upload, setUpload] = useState(null);
  const [busy, setBusy] = useState(null);   // null | "connect" | "publish"
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

  async function connectAndPublish() {
    if (busy || working) return;
    setError("");
    try {
      if (!connection?.connected) {
        setBusy("connect");
        setConnection(await connectAndWait({
          name: "LinkedIn",
          connect: () => api.connectLinkedin(projectId),
          check: () => api.getLinkedinConnection(projectId),
        }));
      }
      setBusy("publish");
      if (upload?.status === "Failed" && !upload.video && !upload.post_attempted) submission.current = null;
      submission.current ??= crypto.randomUUID();
      setUpload(await api.publishLinkedin(projectId, clip.job_id, clip.clip_index, {
        title: (post?.name || clip.title || "Cascade clip").slice(0, 160),
        caption: post?.caption ?? "",
        hashtags: post?.hashtags ?? [],
        edit: state,
        submission_id: submission.current,
      }));
    } catch (err) { setError(err.message); }
    finally { setBusy(null); }
  }

  const retained = !!upload?.video || !!upload?.post_attempted || upload?.status === "Published";
  let label = connection?.connected ? "Publish to LinkedIn" : "Connect & publish to LinkedIn";
  if (busy === "connect") label = "Waiting for LinkedIn sign-in…";
  if (busy === "publish") label = "Publishing…";

  return (
    <div className="export-publish-row">
      <h3 className="export-social-title"><Icon name="linkedin" /> LinkedIn</h3>
      {!connection ? <Spinner label="Checking LinkedIn" />
        : connection.configured === false ? <p className="export-social-note">{connection.error}</p>
          : <>
            <div className="export-publish-controls">
              <Button size="sm" variant="primary" onClick={connectAndPublish} disabled={!!busy || working || !state || retained}>
                {busy && <Spinner size={14} label="Working" />} {label}
              </Button>
            </div>
            <p className="export-social-note">
              {connection.connected ? <>Public post as <b>{connection.profile}</b></> : "Posts publicly on your personal profile."}
            </p>
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
