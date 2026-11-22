import { useCallback, useEffect, useRef, useState } from "react";
import { markPageReady } from "../../context/leafTransitionValue";
import AIEditorChat from "./AIEditorChat";
import SequenceControls from "./SequenceControls";
import { sameEdit, isAIUndo, canUndoAI } from "./editorTransactions";
import EmptyState from "../../components/ui/EmptyState";
import Spinner from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/ToastContext";
import useApi from "../../api/useApi";
import useClipDraft from "./useClipDraft";
import useAutoFraming from "./useAutoFraming";
import ClipPlayer from "./ClipPlayer";
import BrollPanel from "./BrollPanel";
import Timeline from "./Timeline";
import { TrimControls } from "./EditorControls";
import AspectTab from "./tabs/AspectTab";
import CaptionsTab from "./tabs/CaptionsTab";
import { describeChanges } from "./chatChanges";
import ReelControls from "./ReelControls";
import TrendsModal from "./TrendsModal";
import MusicControls from "./MusicControls";
import Icon from "../../components/ui/Icon";
import ClipLoading from "./ClipLoading";
import { ClassicLayout, RevampLayout, SplitLayout, splitTabs } from "./EditorLayouts";

const saveLabels = { saved: <><Icon name="check" /> Saved</>, saving: "Saving…", error: <><Icon name="alert" /> Not saved</> };

// Everything for the clip being edited. It has key={clip key}, so switching clips loads that clip's own draft.
export default function ClipWorkspace({ projectId, clip, sidebar, layout, clipTabs, onExport, registerFlush, clips, openTrends, onSelectClipForTrends }) {
  const api = useApi();
  const toast = useToast();
  const draft = useClipDraft(projectId, clip);
  const [panelTab, setPanelTab] = useState("Trim");
  const [trendsOpen, setTrendsOpen] = useState(Boolean(openTrends));
  const [chatChanges, setChatChanges] = useState({});
  const [editorResult, setEditorResult] = useState(null);
  const aiTransactions = useRef([]);
  const [chatNote, setChatNote] = useState(null);
  const [aiStatus, setAIStatus] = useState(null);
  const refreshAIStatus = useCallback(() => api.getEditorAIStatus(projectId).then(setAIStatus).catch(() => {}), [api, projectId]);
  useEffect(() => { refreshAIStatus(); }, [refreshAIStatus]);
  const [thinking, setThinking] = useState(false);
  const [brollSearch, setBrollSearch] = useState(null);
  const [selectedSegment, setSelectedSegment] = useState(null);
  const selectBroll = useCallback(id => setSelectedSegment(id), []);
  const [focusedCue, setFocusedCue] = useState(null); // caption line clicked on the timeline (for the Captions tab)
  const [captionsView, setCaptionsView] = useState("Style"); // the Captions tab's sub-tab: "Style" | "Text"
  const player = useRef(null); // the ClipPlayer's remote control: seek(t), getTime()
  const { info, state, change } = draft;
  const latestState = useRef(state);
  useEffect(() => { latestState.current = state; });
  const selectedBroll = state?.broll?.some(s => s.id === selectedSegment) ? selectedSegment : null;
  useEffect(() => { registerFlush(draft.flush); return () => registerFlush(null); }, [registerFlush, draft.flush]);
  const framing = useAutoFraming(projectId, clip, state, info, draft.patch);
  const loaded = Boolean((info && state) || draft.error);
  useEffect(() => { if (loaded) markPageReady(); }, [loaded]);   // the Editor is ready to use
  // The background edit for this clip. It keeps running if you switch clips or reload; this picks it back up.
  const [aiJob, setAIJob] = useState(null);
  const serverJob = info?.ai_job;
  useEffect(() => { if (serverJob) setAIJob(serverJob); }, [serverJob]);
  const adoptAIEdit = draft.adoptAIEdit;
  const jobRunning = aiJob?.status === "queued" || aiJob?.status === "running";
  useEffect(() => {
    if (!jobRunning) return undefined;
    let active = true;
    const poll = () => api.getAIEdit(projectId, clip.job_id, clip.clip_index).then(({ job, saved }) => {
      if (!active || !job) return;
      setAIJob(job);
      if (job.status === "done" || job.status === "failed") {
        if (saved?.chat) adoptAIEdit(saved.ai_edit ?? null, saved.chat);
        setPanelTab("AI Editor");
      }
    }).catch(() => {});
    const timer = setInterval(poll, 2000);
    poll();
    return () => { active = false; clearInterval(timer); };
  }, [api, projectId, clip.job_id, clip.clip_index, jobRunning, adoptAIEdit]);
  const waitingBoard = info?.storyboard; // a storyboard still waiting for notes or "render" after a reload
  useEffect(() => { if (waitingBoard) setEditorResult(current => current || { storyboard: waitingBoard }); }, [waitingBoard]);

  // "Make the captions yellow": the backend's editor AI returns a new edit + a reply
  async function sendChat(message, research = {}) {
    const history = draft.chat;
    if (isAIUndo(message)) {
      const transaction = aiTransactions.current.at(-1);
      if (!state.ai_edit && !canUndoAI(transaction, state)) {
        draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: transaction
          ? "Not undone: manual edits changed this clip after the AI transaction. Use the shared Undo controls to review those edits first."
          : "No AI edit is available to undo in this editing session. Undo history resets when the page reloads." }]);
        return;
      }
      if (state.ai_edit) return sendEdit(message);
      draft.undo();
      aiTransactions.current.pop();
      setEditorResult(null);
      draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: "UNDONE: The last AI Editor transaction. Use Redo to restore it. Your earlier edits remain." }]);
      return;
    }
    return sendEdit(message, research);
  }

  async function sendEdit(message, research = {}) {
    const history = draft.chat;
    const sent = state;
    const sentRevision = draft.getRevision();
    draft.setChat([...history, { role: "user", text: message }]);
    setChatNote(null);
    setThinking(true);
    try {
      const result = await api.sendEditorChat(projectId, clip.job_id, clip.clip_index, { state, chat: history, message, ...research,
        result_ids: (brollSearch?.results || []).map(a => a.id), selected_segment: selectedBroll });
      if (result.ai_job) setAIJob(result.ai_job);
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
      if (result.broll_search) { setBrollSearch(result.broll_search); setPanelTab("B-roll"); }
      draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: result.message }]);
      return result;
    } catch (err) {
      draft.setChat(history);
      // Quota, engine and planning failures stay visible in the chat; nothing was applied.
      if ([429, 502, 503, 504].includes(err.status)) setChatNote(`NOT APPLIED: ${err.message}`);
      else toast.show(err.message, "error");
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

  // ---------- Pieces both layouts use ----------
  async function goToExport() {
    try { await draft.flush(); onExport(); } catch (e) { toast.show(e.message, "error"); }
  }
  const undoRedo = <>
    <button type="button" className="btn btn-small editor-history-btn" onClick={draft.undo} disabled={!draft.canUndo} aria-label="Undo" title="Undo"><Icon name="undo" /></button>
    <button type="button" className="btn btn-small editor-history-btn" onClick={draft.redo} disabled={!draft.canRedo} aria-label="Redo" title="Redo"><Icon name="redo" /></button>
  </>;
  const statuses = <>
    <span className={`editor-save editor-save-${draft.saveStatus}`} role="status">{saveLabels[draft.saveStatus]}</span>
    {framing.status === "working" && (
      <span className="editor-save" role="status">
        <Spinner size={14} label="Preparing framing" /> Preparing automatic framing… {Math.round(framing.progress * 100)}%
      </span>
    )}
    {framing.status === "error" && <span className="editor-save editor-save-error" role="alert"><Icon name="alert" /> {framing.message}</span>}
  </>;
  const preview = draft.error ? (
    <EmptyState icon="cloud" title="Couldn't load this clip" text={draft.error.message} />
  ) : info && state ? (
    <ClipPlayer projectId={projectId} clip={clip} info={info} state={state} controlRef={player}
      framing={{ patch: draft.patch, recordUndo: draft.recordUndo }} />
  ) : (
    <ClipLoading />
  );
  const timeline = info && state && (<>
    <SequenceControls state={state} change={change} player={player} />
    <Timeline projectId={projectId} clip={clip} hasVideo={info.has_video !== false}
      duration={info.duration} cues={info.cues} state={state} player={player}
      change={change} patch={draft.patch} recordUndo={draft.recordUndo}
      selectedBroll={selectedBroll} onSelectBroll={selectBroll} disabled={thinking}
      focusedCue={focusedCue} onCueClick={(index) => {
        setFocusedCue(index);
        setPanelTab("Captions");
        setCaptionsView("Text");
      }}
      onOpenTool={(tool) => {
        if (tool === "B-roll") return setPanelTab("B-roll");
        setPanelTab(tool);
      }} />
  </>);
  const activeTab = layout === "split" && !splitTabs.includes(panelTab) ? "Captions" : panelTab;
  const brollPanel = state && <BrollPanel projectId={projectId} clip={clip} state={state} duration={info.duration}
    player={player} change={change} search={brollSearch} onSearch={setBrollSearch} selectedId={selectedBroll}
    onSelect={selectBroll} inline disabled={thinking} />;
  const panelContent = !state ? (
    <div className="editor-loading"><Spinner label="Loading edits" /></div>
  ) : activeTab === "Trim" ? (
    <TrimControls state={state} duration={info.duration} change={change} />
  ) : activeTab === "Captions" ? (
    <CaptionsTab state={state} info={info} change={change} patch={draft.patch} recordUndo={draft.recordUndo}
      player={player} view={captionsView} onView={setCaptionsView}
      focusedCue={focusedCue} onFocusCue={setFocusedCue} />
  ) : activeTab === "B-roll" ? (
    brollPanel
  ) : activeTab === "Aspect Ratio" ? (
    <AspectTab state={state} info={info} change={change} patch={draft.patch} recordUndo={draft.recordUndo} />
  ) : activeTab === "Reel" ? (
    <ReelControls state={state} change={change} onApply={sendChat} thinking={thinking} />
  ) : activeTab === "Music" ? (
    <MusicControls projectId={projectId} clip={clip} state={state} duration={info.duration} change={change} />
  ) : (
    <AIEditorChat messages={chatMessages} onSend={sendChat} onClear={clearChat} disabled={thinking || jobRunning} typing={thinking}
      clip={clip} result={editorResult} status={aiStatus} cues={info?.cues} job={jobRunning ? aiJob : null} aiEdit={state.ai_edit}
      onUseTimeline={() => change(s => ({ ...s, ai_edit: null }))} />
  );
  const trendsModal = trendsOpen && state && <TrendsModal projectId={projectId} clip={clip} info={info} state={state} flush={draft.flush}
    change={change} clips={clips} onSelectClip={onSelectClipForTrends} onClose={() => setTrendsOpen(false)}
    onOpenEditor={(t) => { setTrendsOpen(false); if (Number.isFinite(t)) setTimeout(() => player.current?.seek(t), 50); }} />;

  const pieces = { info, state, draft, projectId, clip, player, panelTab, setPanelTab, activeTab, trendsOpen, setTrendsOpen, goToExport, clipTabs, sidebar, preview, undoRedo, statuses, timeline, panelContent, trendsModal };
  if (layout === "revamp") return <RevampLayout {...pieces} />;
  if (layout === "split") return <SplitLayout {...pieces} />;
  return <ClassicLayout {...pieces} />;
}
