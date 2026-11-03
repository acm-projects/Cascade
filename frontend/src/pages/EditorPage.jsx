import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "./EditorPage.css";
import TopNav from "../components/TopNav";
import AIEditorChat from "../features/editor/AIEditorChat";
import SequenceControls from "../features/editor/SequenceControls";
import { sameEdit, isAIUndo, canUndoAI } from "../features/editor/editorTransactions";
import EmptyState from "../components/ui/EmptyState";
import Spinner from "../components/ui/Spinner";
import { useToast } from "../components/ui/ToastContext";
import useApi from "../api/useApi";
import { formatTime } from "../utils/time";
import { clipKey, flattenClips } from "../features/editor/clips";
import useClipDraft from "../features/editor/useClipDraft";
import useAutoFraming from "../features/editor/useAutoFraming";
import ClipPlayer from "../features/editor/ClipPlayer";
import BrollPanel from "../features/editor/BrollPanel";
import Timeline from "../features/editor/Timeline";
import { TrimControls } from "../features/editor/EditorControls";
import AspectTab from "../features/editor/tabs/AspectTab";
import CaptionsTab from "../features/editor/tabs/CaptionsTab";
import { describeChanges } from "../features/editor/chatChanges";

import ReelControls from "../features/editor/ReelControls";
import TrendsModal from "../features/editor/TrendsModal";
import MusicControls from "../features/editor/MusicControls";
const panelTabs = ["Trim", "Captions", "Trends", "Aspect Ratio", "Music", "Reel", "AI Editor"];
const saveLabels = { saved: "✓ Saved", saving: "Saving…", error: "⚠ Not saved" };
// Built from the Figma "Editor" wireframe (node 560:2716), connected to backend/editor_backend.py.
// Shows the clips picked in AI Studio; every edit is saved to the backend automatically.
function EditorPage() {
  const navigate = useNavigate();
  const { projectId } = useParams();
  const api = useApi();
  const [clips, setClips] = useState(null); // null = loading
  const [error, setError] = useState(null);
  const [currentKey, setCurrentKey] = useState(null);
  const [projectName, setProjectName] = useState(null);
  const flushCurrent = useRef(null);
  const registerFlush = useCallback(value => { flushCurrent.current = value; }, []);
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

  const current = clips?.find((clip) => clipKey(clip) === currentKey);
  const hasClips = Boolean(clips?.length);

  const sidebar = (
    <aside className="editor-sidebar">
      <span className="editor-sidebar-tab active">Picked clips</span>
      <div className="editor-sidebar-content">
        {clips?.map((clip, index) => (
          <button key={clipKey(clip)} type="button"
            className={`editor-media-item${clipKey(clip) === currentKey ? " active" : ""}`}
            onClick={async () => { try { await flushCurrent.current?.(); setCurrentKey(clipKey(clip)); } catch(e) { toast.show(e.message, "error"); } }} title={clip.title}>
            {index + 1}. {clip.title || "Clip"}
            <span>{clip.sessionName ? `${clip.sessionName} · ` : ""}{formatTime(clip.end - clip.start)}</span>
          </button>
        ))}
      </div>
    </aside>
  );

  let body;
  if (error) {
    body = <EmptyState icon="🌧️" title="Couldn't open the Editor" text={error.message} />;
  } else if (!clips) {
    body = <div className="editor-loading"><Spinner size={48} label="Loading your clips" /></div>;
  } else if (!hasClips) {
    body = (
      <EmptyState icon="✂️" title="No clips picked yet" text="Pick the clips you like in AI Studio, then come back here to edit them."
        action={{ label: "Go to AI Studio", onClick: () => navigate(`/projects/${projectId}/studio`) }} />
    );
  }

  return (
    <div className="editor leaf-page">
      <TopNav projectTitle={projectName} active="editor" canOpenEditor canOpenExport={hasClips} />
      {body ? (
        <div className="editor-empty">{body}</div>
      ) : (
        <ClipWorkspace key={currentKey} projectId={projectId} clip={current} sidebar={sidebar}
          registerFlush={registerFlush} onExport={() => navigate(`/projects/${projectId}/export`)} />
      )}
    </div>
  );
}

// Everything for the clip being edited. It has key={clip key}, so switching clips loads that clip's own draft.
function ClipWorkspace({ projectId, clip, sidebar, onExport, registerFlush }) {
  const api = useApi();
  const toast = useToast();
  const draft = useClipDraft(projectId, clip);
  const [panelTab, setPanelTab] = useState("Trim");
  const [trendsOpen, setTrendsOpen] = useState(false);
  const [chatChanges, setChatChanges] = useState({});
  const [editorResult, setEditorResult] = useState(null);
  const aiTransactions = useRef([]);
  const [chatNote, setChatNote] = useState(null);
  const [aiStatus, setAIStatus] = useState(null);
  const refreshAIStatus = useCallback(() => api.getEditorAIStatus(projectId).then(setAIStatus).catch(() => {}), [api, projectId]);
  useEffect(() => { refreshAIStatus(); }, [refreshAIStatus]);
  const [thinking, setThinking] = useState(false);
  const [brollOpen, setBrollOpen] = useState(false);
  const [brollSearch, setBrollSearch] = useState(null);
  const [selectedSegment, setSelectedSegment] = useState(null);
  const selectBroll = useCallback(id => setSelectedSegment(id), []);
  const [focusedCue, setFocusedCue] = useState(null); // caption line clicked on the timeline (for the Captions tab)
  const [captionsView, setCaptionsView] = useState("Style"); // the Captions tab's sub-tab: "Style" | "Text"
  const [sourceMedia, setSourceMedia] = useState(null);
  const player = useRef(null); // the ClipPlayer's remote control: seek(t), getTime()
  const { info, state, change } = draft;
  const latestState = useRef(state);
  useEffect(() => { latestState.current = state; });
  const selectedBroll = state?.broll?.some(s => s.id === selectedSegment) ? selectedSegment : null;
  useEffect(() => { registerFlush(draft.flush); return () => registerFlush(null); }, [registerFlush, draft.flush]);
  const framing = useAutoFraming(projectId, clip, state, info, draft.patch);

  // "Make the captions yellow": the backend's editor AI returns a new edit + a reply
  async function sendChat(message, research = {}) {
    const history = draft.chat;
    if (isAIUndo(message)) {
      const transaction = aiTransactions.current.at(-1);
      if (!canUndoAI(transaction, state)) {
        draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: transaction
          ? "Not undone: manual edits changed this clip after the AI transaction. Use the shared Undo controls to review those edits first."
          : "No AI edit is available to undo in this editing session. Undo history resets when the page reloads." }]);
        return;
      }
      draft.undo();
      aiTransactions.current.pop();
      setEditorResult(null);
      draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: "UNDONE: The last AI Editor transaction. Use Redo to restore it. Your earlier edits remain." }]);
      return;
    }
    const sent = state;
    const sentRevision = draft.getRevision();
    draft.setChat([...history, { role: "user", text: message }]);
    setChatNote(null);
    setThinking(true);
    try {
      const result = await api.sendEditorChat(projectId, clip.job_id, clip.clip_index, { state, chat: history, message, ...research,
        result_ids: (brollSearch?.results || []).map(a => a.id), selected_segment: selectedBroll });
      if (draft.getRevision() !== sentRevision || !sameEdit(latestState.current, sent)) {
        draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: "NOT APPLIED: The clip changed while I was planning. Your newer manual edits were preserved. Send the request again to plan against the current timeline." }]);
        return;
      }
      if (!sameEdit(sent, result.state)) {
        aiTransactions.current.push({ before: sent, after: result.state });
        change(result.state);
      }
      setEditorResult(result);
      setChatChanges(all => ({ ...all, [history.length + 1]: describeChanges(sent, result.state) }));
      if (result.broll_search) { setBrollSearch(result.broll_search); setBrollOpen(true); }
      draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: result.message }]);
      return result;
    } catch (err) {
      draft.setChat(history);
      // Quota, engine and planning failures stay visible in the chat; nothing was applied.
      if ([429, 502, 503, 504].includes(err.status)) setChatNote(`NOT APPLIED: ${err.message}`);
      else toast.show(err.message, "error");
      if (research.research_id) throw err;
    } finally {
      setThinking(false);
      refreshAIStatus();
    }
  }

  // Clears the conversation only; edits already applied to the clip stay (Undo still works).
  function clearChat() {
    if (!window.confirm("Clear this clip's AI Editor chat history? Your edits stay applied.")) return;
    draft.setChat([]);
    setChatChanges({});
    setChatNote(null);
    setEditorResult(null);
  }

  const chatMessages = draft.chat.map((message, index) => ({ ...message, changes: chatChanges[index] }));
  if (chatNote) chatMessages.push({ role: "system", text: chatNote });

  return (
    <>
      <div className="editor-tools">
        <button type="button" className="btn btn-small" onClick={draft.undo} disabled={!draft.canUndo}>↶ Undo</button>
        <button type="button" className="btn btn-small" onClick={draft.redo} disabled={!draft.canRedo}>↷ Redo</button>
        <span className={`editor-save editor-save-${draft.saveStatus}`} role="status">{saveLabels[draft.saveStatus]}</span>
        {framing.status === "working" && (
          <span className="editor-save" role="status">
            <Spinner size={14} label="Preparing framing" /> Preparing automatic framing… {Math.round(framing.progress * 100)}%
          </span>
        )}
        {framing.status === "error" && <span className="editor-save editor-save-error" role="alert">⚠ {framing.message}</span>}
        <button type="button" className="btn btn-small btn-primary editor-export" onClick={async () => { try { await draft.flush(); onExport(); } catch(e) { toast.show(e.message, "error"); } }}>Go to Export →</button>
      </div>

      <div className={`editor-body${brollOpen ? " broll-open" : ""}`}>
        <div className="editor-left-column">
          <nav className="editor-tool-rail" aria-label="Editor tools">
            <button className="btn btn-small" type="button" aria-pressed={brollOpen} disabled={!state || info?.has_video === false}
              onClick={() => setBrollOpen(open => !open)}>B-roll</button>
          </nav>
          {brollOpen && state ? <BrollPanel projectId={projectId} clip={clip} state={state} duration={info.duration}
            player={player} change={change} search={brollSearch} onSearch={setBrollSearch} selectedId={selectedBroll}
            onSelect={selectBroll} onClose={() => setBrollOpen(false)} disabled={thinking} /> : sidebar}
        </div>

        <main className={`editor-center${state?.fablecut ? ' has-ai-sequence' : ''}`}>
          <section className="editor-preview">
            {draft.error ? (
              <EmptyState icon="🌧️" title="Couldn't load this clip" text={draft.error.message} />
            ) : info && state ? (
              <ClipPlayer projectId={projectId} clip={clip} info={info} state={state} controlRef={player} onSourceMedia={setSourceMedia}
                framing={{ patch: draft.patch, recordUndo: draft.recordUndo }} />
            ) : (
              <div className="editor-loading"><Spinner label="Loading clip" /></div>
            )}
          </section>
          {info && state && (
            <section className="editor-timeline" aria-label="Timeline">
              <SequenceControls state={state} change={change} player={player} />
              <Timeline projectId={projectId} clip={clip} sourceUrl={sourceMedia} hasVideo={info.has_video !== false} onTrackClick={setPanelTab} duration={info.duration} cues={info.cues} state={state} player={player}
                change={change} patch={draft.patch} recordUndo={draft.recordUndo}
                selectedBroll={selectedBroll} onSelectBroll={selectBroll} disabled={thinking}
                focusedCue={focusedCue} onCueClick={(index) => {
                  setFocusedCue(index);
                  setPanelTab("Captions");
                  setCaptionsView("Text");
                }} />
            </section>
          )}
          {info?.warning && <p className="editor-warning">{info.warning}</p>}
        </main>

        <aside className="editor-panel">
          <div className="editor-panel-tabs">
            {panelTabs.map((tab) => (
              <button key={tab} type="button" className={`editor-panel-tab${tab === panelTab ? " active" : ""}`}
                disabled={info?.has_video === false && tab === 'Aspect Ratio'}
                title={info?.has_video === false && tab === 'Aspect Ratio' ? 'Audio recordings have no video framing' : undefined}
                aria-haspopup={tab === 'Trends' ? 'dialog' : undefined}
                aria-expanded={tab === 'Trends' ? trendsOpen : undefined}
                onClick={() => tab === 'Trends' ? setTrendsOpen(true) : setPanelTab(tab)}>{tab}</button>
            ))}
          </div>
          <div className="editor-panel-content">
            {!state ? (
              <Spinner label="Loading edits" />
            ) : panelTab === "Trim" ? (
              <TrimControls state={state} duration={info.duration} change={change} />
            ) : panelTab === "Captions" ? (
              <CaptionsTab state={state} info={info} change={change} patch={draft.patch} recordUndo={draft.recordUndo}
                player={player} view={captionsView} onView={setCaptionsView}
                focusedCue={focusedCue} onFocusCue={setFocusedCue} />
            ) : panelTab === "Aspect Ratio" ? (
              <AspectTab state={state} info={info} change={change} patch={draft.patch} recordUndo={draft.recordUndo} />
            ) : panelTab === "Reel" ? (
              <ReelControls state={state} change={change} onApply={sendChat} thinking={thinking} />
            ) : panelTab === "Music" ? (
              <MusicControls projectId={projectId} clip={clip} state={state} duration={info.duration} change={change} />
            ) : (
              <AIEditorChat messages={chatMessages} onSend={sendChat} onClear={clearChat} disabled={thinking} typing={thinking}
                clip={clip} result={editorResult} status={aiStatus} />
            )}
          </div>
        </aside>
      </div>
      {trendsOpen && state && <TrendsModal projectId={projectId} clip={clip} info={info} state={state} flush={draft.flush} disabled={thinking}
        onClose={() => setTrendsOpen(false)} onApply={(research_id, selection) => sendChat('Apply selected edits from YouTube research.', { research_id, ...(Array.isArray(selection) ? { suggestions: selection } : { suggestion: selection }) })}>
        <div className="export-post-actions"><button className="editor-choice" onClick={draft.undo} disabled={!draft.canUndo}>↶ Undo</button><button className="editor-choice" onClick={draft.redo} disabled={!draft.canRedo}>↷ Redo</button><small>{draft.saveStatus}</small></div>
      </TrendsModal>}
    </>
  );
}

export default EditorPage;
