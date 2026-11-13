import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import "./EditorPage.css";
import TopNav from "../components/TopNav";
import WaterFlow from "../components/WaterFlow";
import { markPageReady, useLeafNavigate } from "../context/leafTransitionValue";
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
import Icon from "../components/ui/Icon";
import { EDITOR_LAYOUT } from "../features/editor/editorLayout";
import ClipLoading from "../features/editor/ClipLoading";
import UploadClipButton from "../features/editor/UploadClipButton";
import "../features/editor/EditorRevamp.css";
import "../features/editor/EditorSplit.css";
const panelTabs = ["Trim", "Captions", "B-roll", "Trends", "Aspect Ratio", "Music", "Reel", "AI Editor"];
const saveLabels = { saved: <><Icon name="check" /> Saved</>, saving: "Saving…", error: <><Icon name="alert" /> Not saved</> };
// Abhishri's layout has these tabs: trimming happens on the timeline, and Trends is a button on the player
const splitTabs = ["Captions", "Aspect Ratio", "B-roll", "Music", "AI Editor"];
// The new layout's tool rail: [panel tab, label under the icon, icon]
const railTools = [
  ["Captions", "Captions", "captions"], ["Music", "Music", "headphones"], ["B-roll", "B-roll", "film"],
  ["Trim", "Trim", "scissors"], ["Aspect Ratio", "Aspect", "phone"], ["Trends", "Trends", "sparkles"],
  ["Reel", "Reel", "repeat"], ["AI Editor", "AI Editor", "send"],
];
// Panel title + a friendly tip for each tool (new layout only)
const panelInfo = {
  "Trim": ["Trim your clip", "Clips 15–30 seconds long do best on Reels and Shorts. Try trimming a slow start!"],
  "Captions": ["Captions", "Click a caption on the timeline to fix its words."],
  "Music": ["Add music", "Keep music quiet under talking so every word is easy to hear."],
  "B-roll": ["B-roll", "Drop B-roll over the boring parts to keep people watching."],
  "Aspect Ratio": ["Aspect ratio", "9:16 fills a phone screen: best for Reels, Shorts and TikTok."],
  "Reel": ["Make a reel", "Mix your best moments into one fast reel."],
  "AI Editor": ["AI Editor", "Say what you want, like \"make the captions yellow\"."],
};

// Built from the Figma "Editor" wireframe (node 560:2716), connected to backend/editor_backend.py.
// Shows the clips picked in AI Studio; every edit is saved to the backend automatically.
function EditorPage() {
  const leafNavigate = useLeafNavigate();
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
      </div>
    </aside>
  );

  // New and Abhishri's layouts: the picked clips as tabs
  const clipTabs = (
    <div className="er-clip-tabs" role="tablist" aria-label="Picked clips">
      {clips?.map((clip, index) => (
        <button key={clipKey(clip)} type="button" role="tab" aria-selected={clipKey(clip) === currentKey}
          className={`er-clip-tab${clipKey(clip) === currentKey ? " active" : ""}`} onClick={() => selectClip(clip)} title={clip.title} aria-label={`Clip ${index + 1}`}>
          <span className="er-clip-tab-name">{layout === "split" ? index + 1 : `Clip ${index + 1}`}</span>
          {layout !== "split" && <span className="er-clip-tab-time">{formatTime(clip.end - clip.start)}</span>}
        </button>
      ))}
      <UploadClipButton projectId={projectId} onUploaded={addOwnClip} beforeUpload={saveCurrent}
        className="er-clip-tab er-clip-tab-upload" label="Upload clip" />
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
          text="Upload your own video to edit it right away, or let Canvas find the best clips for you." />
        <div className="editor-empty-actions">
          <UploadClipButton projectId={projectId} onUploaded={addOwnClip} className="btn btn-primary" label="Upload your own clip" />
          <button type="button" className="btn" onClick={() => leafNavigate(`/projects/${projectId}/studio`, { style: "falls" })}>
            <Icon name="sparkles" /> Find clips with Canvas
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`editor leaf-page editor-${layout}`}>
      <WaterFlow />
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

// Everything for the clip being edited. It has key={clip key}, so switching clips loads that clip's own draft.
function ClipWorkspace({ projectId, clip, sidebar, layout, clipTabs, onExport, registerFlush, clips, openTrends, onSelectClipForTrends }) {
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

  // ---------- New layout (Figma "Editor Page – Revamp") ----------
  if (layout === "revamp") {
    const tool = panelTab; // the tool that's lit up in the rail
    const [title, tip] = panelInfo[tool] ?? panelInfo["AI Editor"];
    function chooseTool(id) {
      if (id === "Trends") return setTrendsOpen(true);
      if (id === "B-roll") return setPanelTab("B-roll");
      setPanelTab(id);
    }
    const unavailable = (id) => (id === "Aspect Ratio" || id === "B-roll") && info?.has_video === false;

    return (
      <>
        <div className="er-body">
          <nav className="er-rail" aria-label="Editor tools">
            {railTools.map(([id, label, icon]) => (
              <button key={id} type="button" className={`er-tool${id === tool ? " active" : ""}`}
                aria-pressed={id === tool} disabled={!state || unavailable(id)}
                title={unavailable(id) ? "Audio recordings have no video" : undefined}
                aria-haspopup={id === "Trends" ? "dialog" : undefined} onClick={() => chooseTool(id)}>
                <Icon name={icon} size={30} />
                <span>{label}</span>
              </button>
            ))}
          </nav>

          <aside className="er-panel">
            <h2 className="er-panel-title">{title}</h2>
            <div className="er-panel-content editor-panel-content">{panelContent}</div>
            <div className="er-tip">
              <span className="er-tip-mascot" aria-hidden="true"><Icon name="leaf" size={26} /></span>
              <p><strong>Tip</strong>{tip}</p>
            </div>
          </aside>

          <main className="er-stage">
            {clipTabs}
            <section className="er-preview">{preview}</section>
            <div className="er-stage-bar">
              {undoRedo}
              {statuses}
              <button type="button" className="btn btn-small btn-primary er-export" onClick={goToExport}>Go to Export <Icon name="chevronRight" /></button>
            </div>
            {info?.warning && <p className="editor-warning">{info.warning}</p>}
          </main>

          {timeline && <section className="er-timeline" aria-label="Timeline">{timeline}</section>}
        </div>
        {trendsModal}
      </>
    );
  }

  // ---------- Abhishri's layout (from davebranch) ----------
  if (layout === "split") {
    return (
      <>
        <div className="es-body">
          <section className="es-preview">
            <nav className="es-clip-rail" aria-label="Select clip">{clipTabs}</nav>
            <div className="es-preview-player">
            {draft.error ? (
              <EmptyState icon="cloud" title="Couldn't load this clip" text={draft.error.message} />
            ) : info && state ? (
              <ClipPlayer projectId={projectId} clip={clip} info={info} state={state} controlRef={player} saveStatus={statuses}
                framing={{ patch: draft.patch, recordUndo: draft.recordUndo }} />
            ) : (
              <ClipLoading />
            )}
            </div>
          </section>
          <aside className="es-panel">
            <div className="es-panel-workspace">
            <div className="editor-panel-tabs">
              <button type="button" className="btn btn-small btn-primary es-export" onClick={goToExport}>Export →</button>
              <div className="es-history">{undoRedo}</div>
              {splitTabs.map((tab) => (
                <button key={tab} type="button" className={`editor-panel-tab${tab === activeTab ? " active" : ""}`}
                  disabled={info?.has_video === false && ["Aspect Ratio", "B-roll"].includes(tab)}
                  title={info?.has_video === false && ["Aspect Ratio", "B-roll"].includes(tab) ? "Audio recordings have no video" : undefined}
                  aria-label={tab} aria-pressed={tab === activeTab}
                  onClick={() => setPanelTab(tab)}>
                  <Icon name={railTools.find(([id]) => id === tab)?.[2]} size={22} />
                  <span className="es-tab-label">{tab}</span>
                </button>
              ))}
              <button type="button" className="btn btn-small btn-primary es-trends"
                disabled={!state || info?.has_video === false} aria-haspopup="dialog" aria-expanded={trendsOpen}
                onClick={() => setTrendsOpen(true)}>
                <Icon name="sparkles" size={18} /> Trends
              </button>
            </div>
            <div className="editor-panel-content">{panelContent}</div>
            </div>
          </aside>
          {timeline && <section className="es-timeline" aria-label="Timeline">{timeline}</section>}
          {info?.warning && <p className="es-warning editor-warning">{info.warning}</p>}
        </div>
        {trendsModal}
      </>
    );
  }

  // ---------- Classic layout ----------
  return (
    <>
      <div className="editor-tools">
        {undoRedo}
        {statuses}
        <button type="button" className="btn btn-small btn-primary editor-export" onClick={goToExport}>Go to Export →</button>
      </div>

      <div className="editor-body">
        <div className="editor-left-column">
          {sidebar}
        </div>

        <main className={`editor-center${state?.fablecut ? ' has-ai-sequence' : ''}`}>
          <section className="editor-preview">{preview}</section>
          {timeline && <section className="editor-timeline" aria-label="Timeline">{timeline}</section>}
          {info?.warning && <p className="editor-warning">{info.warning}</p>}
        </main>

        <aside className="editor-panel">
          <div className="editor-panel-tabs">
            {panelTabs.map((tab) => (
              <button key={tab} type="button" className={`editor-panel-tab${tab === panelTab ? " active" : ""}`}
                disabled={info?.has_video === false && ["Aspect Ratio", "B-roll"].includes(tab)}
                title={info?.has_video === false && ["Aspect Ratio", "B-roll"].includes(tab) ? 'Audio recordings have no video' : undefined}
                aria-haspopup={tab === 'Trends' ? 'dialog' : undefined}
                aria-expanded={tab === 'Trends' ? trendsOpen : undefined}
                onClick={() => tab === 'Trends' ? setTrendsOpen(true) : setPanelTab(tab)}>{tab}</button>
            ))}
          </div>
          <div className="editor-panel-content">{panelContent}</div>
        </aside>
      </div>
      {trendsModal}
    </>
  );
}

export default EditorPage;
