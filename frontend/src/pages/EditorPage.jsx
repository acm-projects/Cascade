import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "./EditorPage.css";
import TopNav from "../components/TopNav";
import ChatBox from "../components/ChatBox";
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
import useEditorLayout from "../features/editor/editorLayout";
import "../features/editor/EditorRevamp.css";
const panelTabs = ["Trim", "Captions", "Trends", "Aspect Ratio", "Music", "Reel", "Chat"];
const saveLabels = { saved: <><Icon name="check" /> Saved</>, saving: "Saving…", error: <><Icon name="alert" /> Not saved</> };
// Ready-made requests shown while the Chat tab is empty
const chatSuggestions = [
  "Remove the first 2 seconds", "Make captions bigger and yellow", "Move captions to the top", "Turn captions off",
].map((prompt) => ({ label: prompt, prompt }));

// The new layout's tool rail: [panel tab, label under the icon, icon]
const railTools = [
  ["Captions", "Captions", "captions"], ["Music", "Music", "headphones"], ["B-roll", "B-roll", "film"],
  ["Trim", "Trim", "scissors"], ["Aspect Ratio", "Aspect", "phone"], ["Trends", "Trends", "sparkles"],
  ["Reel", "Reel", "repeat"], ["Chat", "Chat", "send"],
];
// Panel title + a friendly tip for each tool (new layout only)
const panelInfo = {
  "Trim": ["Trim your clip", "Clips 15–30 seconds long do best on Reels and Shorts. Try trimming a slow start!"],
  "Captions": ["Captions", "Click a caption on the timeline to fix its words."],
  "Music": ["Add music", "Keep music quiet under talking so every word is easy to hear."],
  "B-roll": ["B-roll", "Drop B-roll over the boring parts to keep people watching."],
  "Aspect Ratio": ["Aspect ratio", "9:16 fills a phone screen: best for Reels, Shorts and TikTok."],
  "Reel": ["Make a reel", "Mix your best moments into one fast reel."],
  "Chat": ["Ask the AI", "Say what you want, like \"make the captions yellow\"."],
};

// Built from the Figma "Editor" wireframe (node 560:2716), connected to backend/editor_backend.py.
// Shows the clips picked in AI Studio; every edit is saved to the backend automatically.
function EditorPage() {
  const navigate = useNavigate();
  const { projectId } = useParams();
  const [layout, toggleLayout] = useEditorLayout();
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

  // Save the clip you're on, then open another one
  async function selectClip(clip) {
    try { await flushCurrent.current?.(); setCurrentKey(clipKey(clip)); } catch (e) { toast.show(e.message, "error"); }
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
      </div>
    </aside>
  );

  // New layout: the picked clips as tabs above the video
  const clipTabs = (
    <div className="er-clip-tabs" role="tablist" aria-label="Picked clips">
      {clips?.map((clip, index) => (
        <button key={clipKey(clip)} type="button" role="tab" aria-selected={clipKey(clip) === currentKey}
          className={`er-clip-tab${clipKey(clip) === currentKey ? " active" : ""}`} onClick={() => selectClip(clip)} title={clip.title}>
          <span className="er-clip-tab-name">{index + 1}. {clip.title || "Clip"}</span>
          <span className="er-clip-tab-time">{formatTime(clip.end - clip.start)}</span>
        </button>
      ))}
    </div>
  );

  let body;
  if (error) {
    body = <EmptyState icon="cloud" title="Couldn't open the Editor" text={error.message} />;
  } else if (!clips) {
    body = <div className="editor-loading"><Spinner size={48} label="Loading your clips" /></div>;
  } else if (!hasClips) {
    body = (
      <EmptyState icon="scissors" title="No clips picked yet" text="Pick the clips you like in AI Studio, then come back here to edit them."
        action={{ label: "Go to AI Studio", onClick: () => navigate(`/projects/${projectId}/studio`) }} />
    );
  }

  return (
    <div className={`editor leaf-page${layout === "revamp" ? " editor-revamp" : ""}`}>
      <TopNav projectTitle={projectName} active="editor" canOpenEditor canOpenExport={hasClips} />
      {body ? (
        <div className="editor-empty">{body}</div>
      ) : (
        <ClipWorkspace key={currentKey} projectId={projectId} clip={current} sidebar={sidebar} layout={layout} clipTabs={clipTabs}
          registerFlush={registerFlush} onExport={() => navigate(`/projects/${projectId}/export`)} />
      )}
      <button type="button" className="er-layout-switch" onClick={toggleLayout}
        title="Switch between the original Editor layout and the new one">
        <Icon name="grid" /> {layout === "revamp" ? "Use classic layout" : "Try new layout"}
      </button>
    </div>
  );
}

// Everything for the clip being edited. It has key={clip key}, so switching clips loads that clip's own draft.
function ClipWorkspace({ projectId, clip, sidebar, layout, clipTabs, onExport, registerFlush }) {
  const api = useApi();
  const toast = useToast();
  const draft = useClipDraft(projectId, clip);
  const [panelTab, setPanelTab] = useState("Trim");
  const [trendsOpen, setTrendsOpen] = useState(false);
  const [chatChanges, setChatChanges] = useState({});
  const [chatNote, setChatNote] = useState(null);
  const [thinking, setThinking] = useState(false);
  const [brollOpen, setBrollOpen] = useState(false);
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

  // "Make the captions yellow": the backend's editor AI returns a new edit + a reply
  async function sendChat(message, research = {}) {
    const history = draft.chat;
    const sent = state;
    draft.setChat([...history, { role: "user", text: message }]);
    setChatNote(null);
    setThinking(true);
    try {
      const result = await api.sendEditorChat(projectId, clip.job_id, clip.clip_index, { state, chat: history, message, ...research,
        result_ids: (brollSearch?.results || []).map(a => a.id), selected_segment: selectedBroll });
      if (latestState.current !== sent) toast.show("The AI edit replaced changes made while it was working. Undo to restore them.");
      change(result.state);
      setChatChanges(all => ({ ...all, [history.length + 1]: describeChanges(sent, result.state) }));
      if (result.broll_search) { setBrollSearch(result.broll_search); setBrollOpen(true); }
      draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: result.message }]);
      return result;
    } catch (err) {
      draft.setChat(history);
      if (err.status === 503) setChatNote(err.message);
      else toast.show(err.message, "error");
      if (research.research_id) throw err;
    } finally {
      setThinking(false);
    }
  }

  const chatMessages = draft.chat.map((message, index) => ({ ...message, changes: chatChanges[index] }));
  if (chatNote) chatMessages.push({ role: "system", text: chatNote });

  // ---------- Pieces both layouts use ----------
  async function goToExport() {
    try { await draft.flush(); onExport(); } catch (e) { toast.show(e.message, "error"); }
  }
  const undoRedo = <>
    <button type="button" className="btn btn-small" onClick={draft.undo} disabled={!draft.canUndo}><Icon name="undo" /> Undo</button>
    <button type="button" className="btn btn-small" onClick={draft.redo} disabled={!draft.canRedo}><Icon name="redo" /> Redo</button>
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
    <div className="editor-loading"><Spinner label="Loading clip" /></div>
  );
  const timeline = info && state && (
    <Timeline duration={info.duration} cues={info.cues} state={state} player={player}
      change={change} patch={draft.patch} recordUndo={draft.recordUndo}
      selectedBroll={selectedBroll} onSelectBroll={selectBroll} disabled={thinking}
      focusedCue={focusedCue} onCueClick={(index) => {
        setFocusedCue(index);
        if (layout === "revamp") setBrollOpen(false); // the new layout shows one panel at a time
        setPanelTab("Captions");
        setCaptionsView("Text");
      }} />
  );
  const panelContent = !state ? (
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
    <ChatBox messages={chatMessages} onSend={sendChat} disabled={thinking} typing={thinking}
      quickActions={draft.chat.length === 0 ? chatSuggestions : []}
      placeholder={thinking ? "Editing…" : "e.g. add dramatic music, a punch-in on the reaction, and relevant B-roll"} />
  );
  const brollPanel = state && <BrollPanel projectId={projectId} clip={clip} state={state} duration={info.duration}
    player={player} change={change} search={brollSearch} onSearch={setBrollSearch} selectedId={selectedBroll}
    onSelect={selectBroll} onClose={() => setBrollOpen(false)} disabled={thinking} />;
  const trendsModal = trendsOpen && state && <TrendsModal projectId={projectId} clip={clip} info={info} state={state} flush={draft.flush} disabled={thinking}
    onClose={() => setTrendsOpen(false)} onApply={(research_id, selection) => sendChat('Apply selected edits from YouTube research.', { research_id, ...(Array.isArray(selection) ? { suggestions: selection } : { suggestion: selection }) })}>
    <div className="export-post-actions"><button className="editor-choice" onClick={draft.undo} disabled={!draft.canUndo}><Icon name="undo" /> Undo</button><button className="editor-choice" onClick={draft.redo} disabled={!draft.canRedo}><Icon name="redo" /> Redo</button><small>{draft.saveStatus}</small></div>
  </TrendsModal>;

  // ---------- New layout (Figma "Editor Page – Revamp") ----------
  if (layout === "revamp") {
    const tool = brollOpen ? "B-roll" : panelTab; // the tool that's lit up in the rail
    const [title, tip] = panelInfo[tool] ?? panelInfo.Chat;
    function chooseTool(id) {
      if (id === "Trends") return setTrendsOpen(true);
      if (id === "B-roll") return setBrollOpen(true);
      setBrollOpen(false);
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
            <div className="er-panel-content editor-panel-content">{tool === "B-roll" ? brollPanel : panelContent}</div>
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

  // ---------- Classic layout ----------
  return (
    <>
      <div className="editor-tools">
        {undoRedo}
        {statuses}
        <button type="button" className="btn btn-small btn-primary editor-export" onClick={goToExport}>Go to Export →</button>
      </div>

      <div className={`editor-body${brollOpen ? " broll-open" : ""}`}>
        <div className="editor-left-column">
          <nav className="editor-tool-rail" aria-label="Editor tools">
            <button className="btn btn-small" type="button" aria-pressed={brollOpen} disabled={!state || info?.has_video === false}
              onClick={() => setBrollOpen(open => !open)}>B-roll</button>
          </nav>
          {brollOpen && state ? brollPanel : sidebar}
        </div>

        <main className="editor-center">
          <section className="editor-preview">{preview}</section>
          {timeline && <section className="editor-timeline" aria-label="Timeline">{timeline}</section>}
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
          <div className="editor-panel-content">{panelContent}</div>
        </aside>
      </div>
      {trendsModal}
    </>
  );
}

export default EditorPage;
