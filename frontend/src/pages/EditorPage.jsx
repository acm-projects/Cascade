import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import TopNav from "../components/TopNav";
import { markPageReady, useLeafNavigate } from "../context/leafTransitionValue";
import EmptyState from "../components/ui/EmptyState";
import Spinner from "../components/ui/Spinner";
import { useToast } from "../components/ui/ToastContext";
import useApi from "../api/useApi";
import { formatTime } from "../utils/time";
import { clipKey, combinable, flattenClips } from "../features/editor/clips";
import Icon from "../components/ui/Icon";
import { EDITOR_LAYOUT } from "../features/editor/editorLayout";
import UploadClipButton from "../features/editor/UploadClipButton";
import CombineClips from "../features/editor/CombineClips";
import ClipWorkspace from "../features/editor/ClipWorkspace";
import "./EditorPage.css";
import "../features/editor/EditorRevamp.css";
import "../features/editor/EditorSplit.css";

// Built from the Figma "Editor" wireframe (node 560:2716), connected to backend/editor_backend.py.
// Shows the clips picked in AI Studio; every edit is saved to the backend automatically.
function EditorPage() {
  const leafNavigate = useLeafNavigate();
  const navigate = useNavigate();
  const location = useLocation();
  const { projectId } = useParams();
  const layout = EDITOR_LAYOUT;
  const api = useApi();
  const [clips, setClips] = useState(null); // null = loading
  const [error, setError] = useState(null);
  const [currentKey, setCurrentKey] = useState(null);
  const [projectName, setProjectName] = useState(null);
  const flushCurrent = useRef(null);
  const registerFlush = useCallback(value => { flushCurrent.current = value; }, []);
  const [trendsFor, setTrendsFor] = useState(null); // reopen Trend Analysis after picking another clip from inside it
  const [combining, setCombining] = useState(false);
  const autoCombine = useRef(Boolean(location.state?.combine)); // "Combine & edit" in AI Studio
  const toast = useToast();

  useEffect(() => {
    let active = true;
    Promise.all([api.getEditorIndex(projectId, { selectedOnly: true }), api.getProject(projectId)])
      .then(([index, project]) => {
        if (!active) return;
        const list = flattenClips(index);
        setClips(list);
        setProjectName(project.name);
        const first = index.selection && list.find((clip) => clipKey(clip) === clipKey(index.selection));
        setCurrentKey(first ? clipKey(first) : list[0] && clipKey(list[0]));
      })
      .catch((err) => active && setError(err));
    return () => {
      active = false;
    };
  }, [api, projectId]);

  // After "Upload a clip": reload the list and open the new clip
  async function addOwnClip(added) {
    const list = flattenClips(await api.getEditorIndex(projectId, { selectedOnly: true }));
    setClips(list);
    setCurrentKey(clipKey(added));
  }
  const saveCurrent = () => flushCurrent.current?.();

  // Multi-clip editing: join the chosen clips into one new clip and open it
  const combine = useCallback(async (chosen) => {
    setCombining(true);
    try {
      await flushCurrent.current?.();
      const made = await api.combineClips(projectId, chosen);
      const list = flattenClips(await api.getEditorIndex(projectId, { selectedOnly: true }));
      setClips(list);
      setCurrentKey(clipKey(made));
      toast.show(`Combined ${made.parts} clips into one edit (${formatTime(made.duration)}). Ask the AI Editor to edit it.`);
    } catch (err) {
      toast.show(`Couldn't combine the clips: ${err.message}`, "error");
      throw err;
    } finally {
      setCombining(false);
    }
  }, [api, projectId, toast]);

  // Came from "Combine & edit": join every picked clip once, then forget the request (a reload won't repeat it)
  useEffect(() => {
    if (!autoCombine.current || !clips) return;
    autoCombine.current = false;
    navigate(location.pathname, { replace: true, state: null });
    const parts = combinable(clips);
    if (parts.length >= 2) combine(parts).catch(() => {});
  }, [clips, combine, navigate, location.pathname]);
  const combineButton = (className, compact) => <CombineClips key={clips?.length} clips={clips} onCombine={combine} busy={combining} className={className} compact={compact} />;

  const current = clips?.find((clip) => clipKey(clip) === currentKey);
  const hasClips = Boolean(clips?.length);
  // Nothing more to load (an error, or no clips): let a waterfall page change fall away. With clips,
  // ClipWorkspace says so once the clip's edits have loaded.
  const settled = Boolean(error || (clips && !hasClips));
  useEffect(() => { if (settled) markPageReady(); }, [settled]);

  // Save the clip you're on, then open another one
  async function selectClip(clip, { trends = false } = {}) {
    try { await flushCurrent.current?.(); setTrendsFor(trends ? clipKey(clip) : null); setCurrentKey(clipKey(clip)); } catch (e) { toast.show(e.message, "error"); }
  }

  const sidebar = (
    <aside className="editor-sidebar">
      <span className="editor-sidebar-tab active">Picked clips</span>
      <div className="editor-sidebar-content">
        {clips?.map((clip, index) => (
          <button key={clipKey(clip)} type="button"
            className={`editor-media-item${clipKey(clip) === currentKey ? " active" : ""}`}
            onClick={() => selectClip(clip)} title={clip.title}>
            {index + 1}. {clip.title || "Clip"}
            <span>{clip.sessionName ? `${clip.sessionName} · ` : ""}{formatTime(clip.end - clip.start)}</span>
          </button>
        ))}
        <UploadClipButton projectId={projectId} onUploaded={addOwnClip} beforeUpload={saveCurrent}
          className="btn btn-small editor-upload-clip" label="Upload your own clip" />
        {combineButton("btn btn-small editor-upload-clip")}
      </div>
    </aside>
  );

  // New and Abhishri's layouts: the picked clips as tabs
  const clipTabs = (
    <div className="er-clip-tabs" role="tablist" aria-label="Picked clips">
      {clips?.map((clip, index) => (
        <button key={clipKey(clip)} type="button" role="tab" aria-selected={clipKey(clip) === currentKey}
          className={`er-clip-tab${clipKey(clip) === currentKey ? " active" : ""}`} onClick={() => selectClip(clip)} title={clip.title} aria-label={`Clip ${index + 1}`}>
          <span className="er-clip-tab-name">{layout === "split" ? index + 1 : clip.kind === "combined" ? `Combined ${index + 1}` : `Clip ${index + 1}`}</span>
          {layout !== "split" && <span className="er-clip-tab-time">{formatTime(clip.end - clip.start)}</span>}
        </button>
      ))}
      <UploadClipButton projectId={projectId} onUploaded={addOwnClip} beforeUpload={saveCurrent}
        className="er-clip-tab er-clip-tab-upload" label="Upload clip" />
      {combineButton("er-clip-tab", layout === "split")}
    </div>
  );

  let body;
  if (error) {
    body = <EmptyState icon="cloud" title="Couldn't open the Editor" text={error.message} />;
  } else if (!clips) {
    body = <div className="editor-loading"><Spinner size={48} label="Loading your clips" /></div>;
  } else if (!hasClips) {
    body = (
      <div className="editor-empty-choices">
        <EmptyState icon="scissors" title="No clips yet"
          text="Upload your own video to edit it right away, or let Studio Island find the best clips for you." />
        <div className="editor-empty-actions">
          <UploadClipButton projectId={projectId} onUploaded={addOwnClip} className="btn btn-primary" label="Upload your own clip" />
          <button type="button" className="btn" onClick={() => leafNavigate(`/projects/${projectId}/studio`, { style: "falls" })}>
            <Icon name="sparkles" /> Find clips on Studio Island
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`editor leaf-page editor-${layout}`}>
      <TopNav projectTitle={projectName} active="editor" canOpenEditor canOpenExport={hasClips} />
      {body ? (
        <div className="editor-empty">{body}</div>
      ) : (
        <ClipWorkspace key={currentKey} projectId={projectId} clip={current} sidebar={sidebar} layout={layout} clipTabs={clipTabs}
          clips={clips} openTrends={trendsFor === currentKey} onSelectClipForTrends={clip => selectClip(clip, { trends: true })}
          registerFlush={registerFlush} onExport={() => leafNavigate(`/projects/${projectId}/export`, { style: "falls" })} />
      )}
    </div>
  );
}

export default EditorPage;
