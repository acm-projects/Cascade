import { useCallback, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import "./StudioPage.css";
import TopNav from "../components/TopNav";
import EmptyState from "../components/ui/EmptyState";
import Spinner from "../components/ui/Spinner";
import { useToast } from "../components/ui/ToastContext";
import { useProject } from "../context/ProjectContext";
import useApi from "../api/useApi";
import SessionBar from "../features/studio/SessionBar";
import ChatPanel from "../features/studio/ChatPanel";
import StudioCanvas from "../features/studio/StudioCanvas";
import MediaPreview from "../features/studio/MediaPreview";
import { isSupportedMedia } from '../utils/media';
import useStudioData from "../features/studio/useStudioData";
import { nodeTypes } from "../features/studio/nodes";
import { edgeTypes } from "../features/studio/edges";
import { buildGraph, displayClips, sameRef, sessionGroups } from "../features/studio/graph";

const isRunning = (group) => ["queued", "processing"].includes(group.state);
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// What the assistant "says" about a generation in the chat
function generationStatus(group) {
  if (isRunning(group)) return group.message || "Finding your moments…";
  if (group.state === "error") return group.message || "That request failed. Use Retry on the canvas.";
  if (group.parent_clips?.length && !group.clips.length) return "No new matches. Your previous clip is kept.";
  const found = group.parent_clips?.length > 1
    ? `Combined context from ${group.parent_clips.length} clips: ${group.clips.length} of ${group.requested_clip_count || group.clips.length} results.`
    : `${group.parent_clips?.length ? "Added similar clips:" : "Found"} ${plural(group.clips.length, "clip")}.`;
  return `${found} Pick the ones you like, then go to the Editor.${group.selection_note ? ` (${group.selection_note})` : ""}`;
}

// AI Studio, connected to Kashmine's Studio backend (backend/studio.py):
// pick a video → each prompt is a generation of real clips → pick clips → Go to Editor.
// Picked clips also guide the next prompt ("more like these").
function StudioPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { projectId, sessionId } = useParams();
  const api = useApi();
  const toast = useToast();
  const { project } = useProject();
  const { studio, setStudio, groups, error, refresh } = useStudioData(projectId);

  // Video picked (here, or in the New Project pop-up), uploads with the first prompt
  const [pendingFile, setPendingFile] = useState(() => location.state?.file ?? null);
  const [uploadProgress, setUploadProgress] = useState(null); // 0-100 while the video uploads
  const [preview, setPreview] = useState(null);         // the "watch it big" pop-up: { ref } for a clip, or { path | file, title }
  const [draft, setDraft] = useState("");               // the chat box text
  const [sending, setSending] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [chatFocus, setChatFocus] = useState(null);
  const focusPrompt = useCallback((jobId) => {
    setChatFocus(previous => ({ jobId, visit: (previous?.visit || 0) + 1 }));
  }, []);
  // Re-sending the exact same prompt after a network hiccup reuses its request id, so the
  // backend never starts (and charges for) a second job
  const submission = useRef(null);

  // useMemo: these only change when the backend data does, so the canvas isn't rebuilt every render
  const session = useMemo(() => studio?.sessions.find((s) => s.id === sessionId) ?? null, [studio, sessionId]);
  const editorClips = useMemo(() => studio?.editor_clips ?? [], [studio]);
  const references = useMemo(
    () => (session ? editorClips.filter((ref) => session.job_ids.includes(ref.job_id)) : []),
    [session, editorClips]
  );
  const sourceName = session ? groups.find((g) => g.job_id === session.source_job)?.source_name : undefined;

  // ---------- What the canvas boxes can do ----------
  const chooseFile = useCallback((file) => {
    if (!file) return;
    if (!isSupportedMedia(file)) {
      toast.show("Choose MP4, MOV, WebM, MKV, MP3, WAV, M4A, or FLAC audio/video.", "error");
      return;
    }
    if (session?.source_job) {
      toast.show("This session already has a video. Start a new session for a different one.", "error");
      return;
    }
    setPendingFile(file);
  }, [session, toast]);

  const toggleClip = useCallback((ref) => {
    const next = editorClips.some((item) => sameRef(item, ref))
      ? editorClips.filter((item) => !sameRef(item, ref))
      : [...editorClips, ref];
    if (next.length > 100) {
      toast.show("Pick up to 100 clips.", "error");
      return;
    }
    setStudio((current) => ({ ...current, editor_clips: next })); // show it right away
    api.setEditorSelection(projectId, next).catch((err) => {
      toast.show(err.message, "error");
      refresh(); // put back what the server really has
    });
  }, [editorClips, setStudio, api, projectId, toast, refresh]);

  const previewSource = useCallback(() => {
    if (pendingFile) setPreview({ file: pendingFile, title: pendingFile.name });
    else if (session?.source_job) {
      setPreview({ path: `/api/projects/${projectId}/source/${session.source_job}`, title: sourceName || "Original video" });
    }
  }, [pendingFile, session, projectId, sourceName]);

  const previewClip = useCallback((_clip, ref) => setPreview({ ref }), []);

  const stop = useCallback((jobId) => {
    api.cancelFeature(jobId).then(refresh).catch((err) => toast.show(err.message, "error"));
  }, [api, refresh, toast]);

  const retry = useCallback((jobId) => {
    api.retryGeneration(projectId, jobId, crypto.randomUUID()).then(refresh).catch((err) => toast.show(err.message, "error"));
  }, [api, projectId, refresh, toast]);

  const actions = useMemo(() => ({
    editorClips, pendingFile, sourceName,
    onChooseFile: chooseFile, onPreviewSource: previewSource, onToggle: toggleClip,
    onPreview: previewClip, onStop: stop, onRetry: retry, onReuse: setDraft,
    onFocusPrompt: focusPrompt,
  }), [editorClips, pendingFile, sourceName, chooseFile, previewSource, toggleClip, previewClip, stop, retry, focusPrompt]);

  const graph = useMemo(
    () => (session ? buildGraph(session, groups, { ...actions, showHistory }) : { nodes: [], edges: [] }),
    [session, groups, actions, showHistory]
  );

  // ---------- Chat: your prompts + what happened to each ----------
  const messages = useMemo(() => {
    if (!session) return [];
    const byId = new Map(groups.map((group) => [group.job_id, group]));
    const list = [];
    const addStatus = (jobId, key) => {
      const group = byId.get(jobId);
      if (group) list.push({ id: `${key}-status`, role: "assistant", text: generationStatus(group), group });
    };
    for (const message of session.messages) {
      const guided = message.references?.length > 1 ? ` (combining ${plural(message.references.length, "picked clip")})`
        : message.references?.length ? ` (more like ${plural(message.references.length, "picked clip")})` : "";
      list.push({ id: message.id, role: message.role, text: message.text + guided, jobId: message.job_id });
      if (message.job_id) addStatus(message.job_id, message.id);
    }
    // Older generations that have no chat message yet
    for (const jobId of session.job_ids) {
      if (session.messages.some((m) => m.job_id === jobId)) continue;
      const group = byId.get(jobId);
      if (group) list.push({ id: jobId, role: "user", text: group.prompt, jobId });
      addStatus(jobId, jobId);
    }
    return list;
  }, [session, groups]);

  // ---------- Sending a prompt ----------
  async function send(text, clipCount) {
    if (!session.source_job && !pendingFile) {
      toast.show("Choose audio or video on the canvas first.", "error");
      return false;
    }
    if (references.length > 12) {
      toast.show("Use up to 12 picked clips to guide a prompt. You can keep up to 100 for the Editor.", "error");
      return false;
    }
    const signature = JSON.stringify({ sid: session.id, text, clipCount, references,
      file: pendingFile && [pendingFile.name, pendingFile.size, pendingFile.lastModified] });
    if (submission.current?.signature !== signature) submission.current = { signature, id: crypto.randomUUID() };

    setSending(true);
    try {
      if (session.source_job) {
        await api.studioGenerate(projectId, session.id, {
          prompt: text, clip_count: clipCount, references,
          operation: references.length ? "branch" : "generate",
          request_id: submission.current.id,
        });
      } else {
        setUploadProgress(0);
        await api.studioUpload(projectId, session.id, {
          video: pendingFile, prompt: text, clipCount, requestId: submission.current.id, onProgress: setUploadProgress,
        });
        setPendingFile(null);
        if (location.state?.file) navigate(location.pathname, { replace: true, state: null }); // a reload won't bring it back
      }
      submission.current = null;
      setChatFocus(null);
      await refresh();
      return true;
    } catch (err) {
      toast.show(err.message, "error"); // the prompt stays in the box; sending again retries with the same request id
      return false;
    } finally {
      setSending(false);
      setUploadProgress(null);
    }
  }

  // ---------- Sessions ----------
  function switchSession(id) {
    setChatFocus(null);
    setPendingFile(null); setDraft(""); setPreview(null); submission.current = null;
    navigate(`/projects/${projectId}/studio/${id}`);
    api.saveStudioState(projectId, id, {}).catch(() => {}); // remember it as the active one
  }

  async function createSession(name) {
    try {
      const created = await api.createStudioSession(projectId, name);
      setChatFocus(null);
      setPendingFile(null); setDraft(""); setPreview(null); submission.current = null;
      await refresh();
      navigate(`/projects/${projectId}/studio/${created.id}`);
    } catch (err) {
      toast.show(err.message, "error");
    }
  }

  async function renameSession(name) {
    try {
      await api.renameStudioSession(projectId, session.id, name);
      await refresh();
    } catch (err) {
      toast.show(err.message, "error");
    }
  }

  function savePosition(_event, node) {
    api.saveStudioState(projectId, session.id, { positions: { [node.id]: node.position } })
      .catch((err) => toast.show(`Couldn't save where you moved that box: ${err.message}`, "error"));
  }

  // ---------- Go to Editor ----------
  // The Editor loads the picked clips from the backend itself (they're saved as editor_clips)
  function goToEditor() {
    navigate(`/projects/${projectId}/editor`);
  }

  // ---------- What to show ----------
  // No (or an unknown) session in the URL: go to the one the backend says is active
  if (studio && !session) {
    return <Navigate to={`/projects/${projectId}/studio/${studio.active_session_id}`} replace state={location.state} />;
  }

  const topNav = (
    <TopNav projectTitle={studio?.project?.name ?? project?.name} active="studio"
      canOpenEditor={editorClips.length > 0} canOpenExport={editorClips.length > 0} />
  );

  if (!studio) {
    return (
      <div className="studio studio-no-session leaf-page">
        {topNav}
        <div className="studio-empty">
          {error ? (
            <div className="studio-empty-card wood-panel">
              <EmptyState icon="🌧️" title="Couldn't open AI Studio" text={error.message}
                action={{ label: "Retry", onClick: refresh }} />
            </div>
          ) : (
            <Spinner size={48} label="Opening AI Studio" />
          )}
        </div>
      </div>
    );
  }

  // A clip in the pop-up: its details, Pick, and ← / → through the clips of the same prompt
  function previewProps(shown) {
    if (!shown.ref) return { item: shown };
    const group = groups.find((g) => g.job_id === shown.ref.job_id);
    const index = shown.ref.clip_index;
    const clip = group?.clips[index];
    if (!clip) return { item: { title: "Clip", path: "" } };
    const go = (i) => () => setPreview({ ref: { job_id: group.job_id, clip_index: i } });
    return {
      item: { title: clip.title || "Clip", path: clip.clip_url },
      clip: {
        start: clip.start, end: clip.end, explanation: clip.explanation, prompt: group.prompt,
        referenceMatches: clip.reference_matches,
        referenceLabels: graph.nodes.find(node => node.id === `clip:${shown.ref.job_id}:${index}`)?.data.referenceLabels,
        position: `${index + 1} of ${group.clips.length}`,
        picked: editorClips.some((item) => sameRef(item, shown.ref)),
        onTogglePick: () => toggleClip(shown.ref),
        onPrevious: index > 0 ? go(index - 1) : undefined,
        onNext: index < group.clips.length - 1 ? go(index + 1) : undefined,
      },
    };
  }

  const clipTotal = sessionGroups(session, groups).reduce((n, group) => n + displayClips(session, groups, group).length, 0);
  let note;
  if (references.length > 1) note = `${plural(references.length, "picked clip")} will combine their qualities in each new result, connected to all selected parents.`;
  else if (references.length) note = `${plural(references.length, "picked clip")} will guide this prompt: new clips branch from them and keep the originals.`;
  else if (!session.source_job) note = pendingFile ? `“${pendingFile.name}” uploads when you send your first prompt.` : "Choose audio or video on the canvas, then describe the clips you want.";
  if (uploadProgress !== null) {
    note = (
      <span className="studio-upload">
        Uploading your video… {uploadProgress}%
        <progress max={100} value={uploadProgress} aria-label="Upload progress" />
      </span>
    );
  }

  return (
    <div className="studio leaf-page">
      {topNav}
      <SessionBar sessions={studio.sessions} activeId={session.id}
        onSwitch={switchSession} onCreate={createSession} onRename={renameSession}>
        {clipTotal > 0 && <span>{editorClips.length} of {plural(clipTotal, "clip")} picked</span>}
        <button type="button" className="btn btn-small" aria-pressed={showHistory}
          onClick={() => setShowHistory(value => !value)}
          title="Earlier attempts stay saved. Picked clips and source references always remain visible.">
          {showHistory ? 'Show latest attempts' : 'Show earlier attempts'}
        </button>
        <button type="button" className={`btn btn-small ${editorClips.length ? "btn-primary" : "disabled"}`}
          disabled={!editorClips.length}
          title={editorClips.length ? undefined : "Pick at least one clip first"} onClick={goToEditor}>
          Go to Editor →
        </button>
      </SessionBar>

      <div className="studio-body">
        <ChatPanel messages={messages} onSend={send} disabled={sending} text={draft} onTextChange={setDraft} note={note}
          focusRequest={chatFocus} onStop={stop} onRetry={retry} onReuse={setDraft} />
        <div className="studio-canvas-frame">
          <StudioCanvas nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
            onDropFile={chooseFile} onNodeDragStop={savePosition} />
        </div>
      </div>

      {preview && <MediaPreview {...previewProps(preview)} onClose={() => setPreview(null)} />}
    </div>
  );
}

export default StudioPage;
