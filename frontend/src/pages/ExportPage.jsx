import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate, useParams } from "react-router-dom";
import "./ExportPage.css";
import TopNav from "../components/TopNav";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Spinner from "../components/ui/Spinner";
import { useToast } from "../components/ui/ToastContext";
import useApi from "../api/useApi";
import { formatTime } from "../utils/time";
import { clipKey, flattenClips } from "../features/editor/clips";
import useClipDraft from "../features/editor/useClipDraft";
import useAutoFraming from "../features/editor/useAutoFraming";
import ClipPlayer from "../features/editor/ClipPlayer";
import useDownloads from "../features/export/useDownloads";
import ExportSettings from "../features/export/ExportSettings";
import PostPanel from "../features/export/PostPanel";
import YouTubePanel from "../features/export/YouTubePanel";
import LinkedInPanel from "../features/export/LinkedInPanel";
import { isAudioClip } from '../utils/media';
import TrendsModal from '../features/editor/TrendsModal';
import { exportTree } from "../features/export/exportTree";
import Icon from "../components/ui/Icon";

// Built from the Figma "Export" wireframe (node 557:2263), connected to backend/editor_backend.py
// (rendering) and Manila's posting backend. Every download is rendered by the server with your edits.
function ExportPage() {
  const navigate = useNavigate();
  const { projectId } = useParams();
  const api = useApi();
  const [clips, setClips] = useState(null);
  const [error, setError] = useState(null);
  const [projectName, setProjectName] = useState(null);
  const [currentKey, setCurrentKey] = useState(null);
  const [downloadActionsTarget, setDownloadActionsTarget] = useState(null);
  const [showAllClips, setShowAllClips] = useState(false);
  const [inZip, setInZip] = useState([]);       // clip keys to put in the ZIP
  const [settings, setSettings] = useState({resolution: "original", includeCaptions: true});
  const downloads = useDownloads(api, projectId, projectName, settings);
  const activeFlush = useRef(null);
  const registerFlush = useCallback(fn => { activeFlush.current = fn; }, []);
  const toast = useToast();

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
  const tree = useMemo(() => exportTree(clips ?? []), [clips]);
  const picked = clips?.filter((clip) => inZip.includes(clipKey(clip))) ?? [];

  const downloadZip = async () => {
    try { await activeFlush.current?.(); await downloads.downloadSelected(clips.filter(clip => inZip.includes(clipKey(clip)))); }
    catch (err) { toast.show(err.message, 'error'); }
  };

  async function pickClip(key) {
    try { await activeFlush.current?.(); setCurrentKey(key); }
    catch (err) { toast.show(err.message, "error"); }
  }

  // Checkboxes: one clip, or every clip in a wave/session at once
  const allIn = (list) => list.every((clip) => inZip.includes(clipKey(clip)));
  function toggleGroup(list) {
    const keys = list.map(clipKey);
    setInZip((current) => (allIn(list) ? current.filter((k) => !keys.includes(k)) : [...new Set([...current, ...keys])]));
  }

  let message;
  if (error) message = <EmptyState icon="cloud" title="Couldn't open Export" text={error.message} />;
  else if (!clips) message = <Spinner size={48} label="Loading your clips" />;
  else if (!clips.length) {
    message = (
      <EmptyState icon="box" title="Nothing to export yet" text="Pick clips in AI Studio and edit them, then export them here."
        action={{ label: "Go to AI Studio", onClick: () => navigate(`/projects/${projectId}/studio`) }} />
    );
  }

  return (
    <div className="export leaf-page">
      <TopNav projectTitle={projectName} active="export" canOpenEditor canOpenExport />
      {message ? (
        <div className="export-empty">{message}</div>
      ) : (
        <div className="export-body">
          <aside className="export-sidebar" aria-label="Export options">
          <div className="export-footer">
            <Button size="sm" onClick={async () => {
              try { await activeFlush.current?.(); navigate(`/projects/${projectId}/editor`); }
              catch (err) { toast.show(err.message, "error"); }
            }}>← Back to editor</Button>
          </div>
          <section className="export-tree" aria-label="Clips to export">
            <div className="export-selection-head">
              <h2 className="export-section-title">Clips <span>{inZip.length}/{clips.length}</span></h2>
              <Button size="sm" variant="ghost" onClick={() => setInZip(inZip.length === clips.length ? [] : clips.map(clipKey))}>
                {inZip.length === clips.length ? "Clear" : "Select all"}
              </Button>
            </div>
            {tree.map((session) => {
              const sessionClips = session.waves.flatMap((wave) => wave.clips);
              return (
                <TreeGroup key={session.id} label={session.name} checked={allIn(sessionClips)}
                  onCheck={() => toggleGroup(sessionClips)}>
                  {session.waves.map((wave) => (
                    <TreeGroup key={wave.id} label={wave.name} title={wave.prompt} checked={allIn(wave.clips)}
                      onCheck={() => toggleGroup(wave.clips)}>
                      {wave.clips.map((clip) => {
                        const key = clipKey(clip);
                        return (
                          <div key={key} className="export-tree-clip">
                            <input type="checkbox" checked={inZip.includes(key)} onChange={() => toggleGroup([clip])}
                              aria-label={`Include clip ${clips.indexOf(clip) + 1} in the download`} />
                            <button type="button" className={`export-tree-clip-name${key === currentKey ? " active" : ""}`}
                              onClick={() => pickClip(key)} title={clip.title}>
                              Clip {clips.indexOf(clip) + 1}
                            </button>
                          </div>
                        );
                      })}
                    </TreeGroup>
                  ))}
                </TreeGroup>
              );
            })}
          </section>
          <section className="export-settings">
            <h3 className="export-section-title">Download</h3>
            <ExportSettings settings={settings} onChange={setSettings} downloads={downloads} selectedCount={inZip.length} audioOnly={isAudioClip(current)} />
            <div className="export-download-controls" ref={setDownloadActionsTarget} />
          </section>
          <div className="export-footer">
            <Button variant="primary" size="sm" onClick={() => navigate("/projects")}>Go to projects</Button>
          </div>
          </aside>

          <ClipExport key={currentKey} projectId={projectId} clip={current} downloads={downloads} registerFlush={registerFlush}
            clips={clips} picked={picked} onPick={pickClip} onDownloadSelected={downloadZip}
            downloadActionsTarget={downloadActionsTarget}
            expanded={showAllClips} onExpandedChange={setShowAllClips}
            clipNumber={clips.indexOf(current) + 1}
          />
        </div>
      )}
    </div>
  );
}

// A folder in the left list (a session or a wave): ▾ to fold it, a checkbox for all its clips, then its contents
function TreeGroup({ label, title, checked, onCheck, children }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="export-tree-group">
      <div className="export-tree-row" title={title}>
        <button type="button" className="export-tree-fold" onClick={() => setOpen(!open)}
          aria-expanded={open} aria-label={`${open ? "Fold" : "Unfold"} ${label}`}><Icon name={open ? "chevronDown" : "chevronRight"} /></button>
        <input type="checkbox" checked={checked} onChange={onCheck} aria-label={`Include all of ${label}`} />
        <span>{label}</span>
      </div>
      {open && <div className="export-tree-children">{children}</div>}
    </div>
  );
}

// Everything right of the list, for the clip on screen. key={clip key}, so it follows the chosen clip.
function ClipExport({ projectId, clip, clips, picked, onPick, onDownloadSelected, downloads, clipNumber, registerFlush, downloadActionsTarget, expanded, onExpandedChange }) {
  const toast = useToast();
  const draft = useClipDraft(projectId, clip);
  const [trendsOpen, setTrendsOpen] = useState(false);
  const navigate = useNavigate();
  const { info, state, error, patch } = draft;
  useEffect(() => { registerFlush(draft.flush); return () => registerFlush(null); }, [registerFlush, draft.flush]);
  // Fill (crop) exports need the framing analysis first; this starts it if the Editor didn't finish it
  const framing = useAutoFraming(projectId, clip, state, info, patch);
  const rendering = downloads.working;
  const [rendered, setRendered] = useState(null); // the last MP4, so it can be shared
  const [post, setPost] = useState(null);
  async function downloadMp4() {
    try {
      await draft.flush();
      const result = await downloads.downloadOne(clip, clipNumber);
      if(result) setRendered(new File([result.blob], result.filename, {type: result.blob.type}));
    } catch (err) { toast.show(err.message, 'error'); }
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

  const index = clipNumber - 1;
  const goTo = (i) => onPick(clipKey(clips[i]));
  let status = null;
  if (framing.status === "error") status = `Couldn't prepare framing: ${framing.message}`;
  else if (framing.status === "working") status = `Preparing automatic framing… ${Math.round(framing.progress * 100)}%`;
  else if (state) {
    status = `${formatTime(state.end - state.start)} · ${isAudioClip(clip) ? "Audio"
      : state.composition.ratio === "original" ? "Original" : state.composition.ratio} · captions ${state.captions.enabled ? "on" : "off"}`;
  }

  return (
    <>
    {downloadActionsTarget && createPortal(<>

          <div className="export-actions">
            <Button variant="primary" size="sm" onClick={onDownloadSelected} disabled={!state || rendering || framing.status === "working" || !picked.length}>
              Download selected ({picked.length})
            </Button>
            <Button variant="ghost" size="sm" onClick={downloadMp4} disabled={!state || rendering || framing.status === "working"}>
              {rendering ? <><Spinner size={14} label="Rendering" /> Rendering…</> : "Download clip"}
            </Button>
          </div>
    </>, downloadActionsTarget)}
    <main className="export-main">
      <section className="export-stage">
        <header className="export-stage-head">
          <div className="export-preview-heading">
            <h2 className="export-section-title">Clip {clipNumber}</h2>
            <span title={clip.title}>{clip.title || "Preview"}</span>
          </div>
          {clips.length > 1 && (
            <button type="button" className="btn btn-small btn-ghost" onClick={() => onExpandedChange(!expanded)} aria-expanded={expanded}>
              {expanded ? "Back to preview" : "Browse clips"}
            </button>
          )}
        </header>
        {expanded ? (
          <div className="export-grid">
            {clips.map((item, i) => (
              <button key={clipKey(item)} type="button" className={`export-grid-card${i === index ? " active" : ""}`}
                onClick={() => { goTo(i); onExpandedChange(false); }}>
                <b>Clip {i + 1}</b>
                <span>{item.title || "Clip"}</span>
                <span>{formatTime(item.end - item.start)}</span>
              </button>
            ))}
          </div>
        ) : (
          <div className={`export-stack${clips.length > 1 ? " is-stacked" : ""}`}>
            <div className="export-player">
              {error ? <p role="alert">{error.message}</p>
                : info && state ? <ClipPlayer projectId={projectId} clip={clip} info={info} state={state} />
                  : <Spinner label="Loading clip" />}
            </div>
          </div>
        )}
        <footer className="export-preview-footer">
          {status && <p className={`export-status${framing.status === "error" ? " is-error" : ""}`} role="status">{status}</p>}
        <div className="export-pager">
          <button type="button" className="btn btn-small" onClick={() => goTo(index - 1)} disabled={index === 0} aria-label="Previous clip">←</button>
          <span>{clipNumber} of {clips.length}</span>
          <button type="button" className="btn btn-small" onClick={() => goTo(index + 1)} disabled={index === clips.length - 1} aria-label="Next clip">→</button>
        </div>
        </footer>
      </section>

    </main>
    <aside className="export-publishing" aria-label="Publishing tools">
      <section className="export-social">
        <PostPanel projectId={projectId} clip={clip} onChange={setPost} />
        {trendsOpen && state && <TrendsModal projectId={projectId} clip={clip} info={info} state={state} flush={draft.flush} change={draft.change}
          onClose={() => setTrendsOpen(false)} onOpenEditor={async () => { await draft.flush(); navigate(`/projects/${projectId}/editor`); }} />}
        {!isAudioClip(clip) && <section className="export-youtube" aria-label="YouTube tools">
          {state && <Button size="sm" aria-haspopup="dialog" onClick={() => setTrendsOpen(true)}>Trends analysis</Button>}
          <YouTubePanel projectId={projectId} clip={clip} post={post} state={state} />
        </section>}
        {!isAudioClip(clip) && <LinkedInPanel key={`${projectId}:${clip.job_id}:${clip.clip_index}`} projectId={projectId} clip={clip} post={post} state={state} />}
        <div className="export-post">
          <h3 className="export-social-title">{isAudioClip(clip) ? <><Icon name="headphones" /> Share audio</> : <><Icon name="phone" /> Share clip</>}</h3>
          <p className="export-social-note">
            {isAudioClip(clip) ? 'Download the MP3, or share it with apps on this device that accept audio files.' : rendered
              ? canShare ? "Share the MP4 you just downloaded to any app on this device." : "This browser can't share files. Upload the downloaded MP4 in the app."
              : "Download a clip to share it."}
          </p>
          {canShare && <Button size="sm" onClick={share}>Share…</Button>}
        </div>
      </section>

    </aside>
    </>
  );
}

export default ExportPage;
