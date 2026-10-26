import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "./ExportPage.css";
import TopNav from "../components/TopNav";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Spinner from "../components/ui/Spinner";
import { useToast } from "../components/ui/ToastContext";
import useApi from "../api/useApi";
import { formatTime } from "../utils/time";
import { clipKey, downloadBlob, fileSafe, flattenClips } from "../features/editor/clips";
import useClipDraft from "../features/editor/useClipDraft";
import useAutoFraming, { needsFraming } from "../features/editor/useAutoFraming";
import ClipPlayer from "../features/editor/ClipPlayer";
import PostPanel from "../features/export/PostPanel";
import YouTubePanel from "../features/export/YouTubePanel";

// Built from the Figma "Export" wireframe (node 557:2263), connected to backend/editor_backend.py
// (rendering) and Manila's posting backend. Every download is rendered by the server with your edits.
function ExportPage() {
  const navigate = useNavigate();
  const { projectId } = useParams();
  const api = useApi();
  const toast = useToast();
  const [clips, setClips] = useState(null);
  const [error, setError] = useState(null);
  const [projectName, setProjectName] = useState(null);
  const [currentKey, setCurrentKey] = useState(null);
  const [inZip, setInZip] = useState([]);       // clip keys to put in the ZIP
  const [zipping, setZipping] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([api.getEditorIndex(projectId, { selectedOnly: true }), api.getProject(projectId)])
      .then(([index, project]) => {
        if (!active) return;
        const list = flattenClips(index);
        setClips(list);
        setProjectName(project.name);
        setCurrentKey(list[0] && clipKey(list[0]));
        setInZip(list.map(clipKey));
      })
      .catch((err) => active && setError(err));
    return () => {
      active = false;
    };
  }, [api, projectId]);

  const current = clips?.find((clip) => clipKey(clip) === currentKey);

  // Render every checked clip with its saved edits, as one ZIP
  async function downloadZip() {
    const chosen = clips.filter((clip) => inZip.includes(clipKey(clip)));
    setZipping(true);
    try {
      const drafts = await Promise.all(chosen.map((clip) => api.getDraft(projectId, clip.job_id, clip.clip_index)));
      // Fill (crop) clips need their framing analysis first: say which ones, instead of a vague server error
      const waiting = chosen.filter((_, i) => needsFraming(drafts[i].draft.state, drafts[i]) && !drafts[i].draft.state.reframe.analysis_id);
      if (waiting.length) {
        const names = waiting.map((clip) => `"${clip.title || "Clip"}"`).join(", ");
        toast.show(`${names} uses Fill (crop) and its automatic framing isn't ready. Open it here first, or switch it to Fit in the Editor.`, "error");
        return;
      }
      const zip = await api.exportSelected(projectId,
        chosen.map((clip, i) => ({ job_id: clip.job_id, clip_index: clip.clip_index, edit: drafts[i].draft.state })));
      downloadBlob(zip, `${fileSafe(projectName, "cascade")}-clips.zip`);
      toast.show(`Downloaded ${chosen.length} clip${chosen.length === 1 ? "" : "s"}`);
    } catch (err) {
      toast.show(`Export failed: ${err.message}`, "error");
    } finally {
      setZipping(false);
    }
  }

  const toggleZip = (key) => setInZip((keys) => (keys.includes(key) ? keys.filter((k) => k !== key) : [...keys, key]));

  let message;
  if (error) message = <EmptyState icon="🌧️" title="Couldn't open Export" text={error.message} />;
  else if (!clips) message = <Spinner size={48} label="Loading your clips" />;
  else if (!clips.length) {
    message = (
      <EmptyState icon="📦" title="Nothing to export yet" text="Pick clips in AI Studio and edit them, then export them here."
        action={{ label: "Go to AI Studio", onClick: () => navigate(`/projects/${projectId}/studio`) }} />
    );
  }

  return (
    <div className="export leaf-page">
      <TopNav projectTitle={projectName} active="export" canOpenEditor canOpenExport />
      {message ? (
        <div className="export-empty">{message}</div>
      ) : (
        <ClipExport key={currentKey} projectId={projectId} clip={current}
          picker={
            <div className="export-clip-tabs" role="tablist" aria-label="Picked clips">
              {clips.map((clip, index) => (
                <button key={clipKey(clip)} type="button" role="tab" aria-selected={clipKey(clip) === currentKey}
                  className={`export-clip-tab${clipKey(clip) === currentKey ? " active" : ""}`}
                  onClick={() => setCurrentKey(clipKey(clip))} title={clip.title}>
                  {index + 1}. {clip.title || "Clip"}
                </button>
              ))}
            </div>
          }
          zip={
            <div className="export-section">
              <h3 className="export-section-title">All picked clips</h3>
              <div className="export-zip-list">
                {clips.map((clip, index) => (
                  <label key={clipKey(clip)} className="export-check">
                    <input type="checkbox" checked={inZip.includes(clipKey(clip))} onChange={() => toggleZip(clipKey(clip))} />
                    {index + 1}. {clip.title || "Clip"}
                  </label>
                ))}
              </div>
              <Button variant="primary" size="sm" onClick={downloadZip} disabled={zipping || !inZip.length}>
                {zipping ? <><Spinner size={14} label="Rendering" /> Rendering {inZip.length}…</> : `⬇ Download ${inZip.length} as ZIP`}
              </Button>
            </div>
          }
          onEdit={() => navigate(`/projects/${projectId}/editor`)}
        />
      )}
    </div>
  );
}

// Preview, MP4 download and posting for one clip. key={clip key}, so it follows the chosen clip.
function ClipExport({ projectId, clip, picker, zip, onEdit }) {
  const api = useApi();
  const toast = useToast();
  const { info, state, error, patch } = useClipDraft(projectId, clip); // only patch()ed by framing below
  // Fill (crop) exports need the framing analysis first; this starts it if the Editor didn't finish it
  const framing = useAutoFraming(projectId, clip, state, info, patch);
  const [rendering, setRendering] = useState(false);
  const [rendered, setRendered] = useState(null); // the last MP4, so it can be shared
  const [post, setPost] = useState(null);
  const fileName = `${fileSafe(post?.name || clip.title)}.mp4`;

  async function downloadMp4() {
    setRendering(true);
    try {
      const video = await api.exportClip(projectId, clip.job_id, clip.clip_index, state);
      downloadBlob(video, fileName);
      setRendered(new File([video], fileName, { type: "video/mp4" }));
    } catch (err) {
      toast.show(`Export failed: ${err.message}`, "error");
    } finally {
      setRendering(false);
    }
  }

  // Instagram/TikTok/etc. have no upload API for us, so hand the file to the phone/computer's share sheet
  const canShare = rendered && navigator.canShare?.({ files: [rendered] });
  async function share() {
    try {
      await navigator.share({ files: [rendered], text: [post?.caption, ...(post?.hashtags ?? [])].filter(Boolean).join(" ") });
    } catch (err) {
      if (err.name !== "AbortError") toast.show(`Sharing failed: ${err.message}`, "error");
    }
  }

  return (
    <div className="export-body">
      <section className="export-preview">
        {picker}
        <div className="export-player">
          {error ? <p role="alert">{error.message}</p>
            : info && state ? <ClipPlayer projectId={projectId} clip={clip} info={info} state={state} />
              : <Spinner label="Loading clip" />}
        </div>
      </section>

      <section className="export-settings">
        <h2 className="export-title">Export</h2>
        <div className="export-section">
          <h3 className="export-section-title">This clip</h3>
          {state && (
            <p className="export-summary">
              {formatTime(state.end - state.start)} long · {state.composition.ratio === "original" ? "original shape" : state.composition.ratio}
              {" · "}captions {state.captions.enabled ? "on" : "off"}
            </p>
          )}
          <div className="export-post-actions">
            <Button variant="primary" size="sm" onClick={downloadMp4} disabled={!state || rendering || framing.status === "working"}>
              {rendering ? <><Spinner size={14} label="Rendering" /> Rendering…</>
                : framing.status === "working" ? <><Spinner size={14} label="Preparing" /> Preparing framing {Math.round(framing.progress * 100)}%</>
                  : "⬇ Download MP4"}
            </Button>
            <Button variant="ghost" size="sm" onClick={onEdit}>✎ Edit</Button>
          </div>
        </div>
        {framing.status === "error" && <p className="export-summary" role="alert">⚠ {framing.message}</p>}
        {zip}
      </section>

      <section className="export-social">
        <PostPanel projectId={projectId} clip={clip} onChange={setPost} />
        <YouTubePanel projectId={projectId} clip={clip} post={post} state={state} />
        <div className="export-post">
          <h3 className="export-social-title">📱 Instagram, TikTok & more</h3>
          <p className="export-social-note">
            {rendered
              ? canShare ? "Share the MP4 you just downloaded to any app on this device." : "This browser can't share files. Upload the downloaded MP4 in the app."
              : "Download the MP4 first, then share it to Instagram, TikTok or anywhere else."}
          </p>
          {canShare && <Button size="sm" onClick={share}>Share…</Button>}
        </div>
      </section>
    </div>
  );
}

export default ExportPage;
