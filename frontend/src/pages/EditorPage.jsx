import { useEffect, useRef, useState } from "react";
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
import Timeline from "../features/editor/Timeline";
import { TrimControls } from "../features/editor/EditorControls";
import AspectTab from "../features/editor/tabs/AspectTab";
import CaptionsTab from "../features/editor/tabs/CaptionsTab";
import { describeChanges } from "../features/editor/chatChanges";

const panelTabs = ["Trim", "Captions", "Aspect Ratio", "Chat"];
const saveLabels = { saved: "✓ Saved", saving: "Saving…", error: "⚠ Not saved" };
// Ready-made requests shown while the Chat tab is empty
const chatSuggestions = [
  "Remove the first 2 seconds", "Make captions bigger and yellow", "Move captions to the top", "Turn captions off",
].map((prompt) => ({ label: prompt, prompt }));

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
            onClick={() => setCurrentKey(clipKey(clip))} title={clip.title}>
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
          onExport={() => navigate(`/projects/${projectId}/export`)} />
      )}
    </div>
  );
}

// Everything for the clip being edited. It has key={clip key}, so switching clips loads that clip's own draft.
function ClipWorkspace({ projectId, clip, sidebar, onExport }) {
  const api = useApi();
  const toast = useToast();
  const draft = useClipDraft(projectId, clip);
  const [panelTab, setPanelTab] = useState("Trim");
  const [thinking, setThinking] = useState(false);
  const [focusedCue, setFocusedCue] = useState(null); // caption line clicked on the timeline (for the Captions tab)
  const [captionsView, setCaptionsView] = useState("Style"); // the Captions tab's sub-tab: "Style" | "Text"
  const player = useRef(null); // the ClipPlayer's remote control: seek(t), getTime()
  const { info, state, change, undo, redo } = draft;
  const framing = useAutoFraming(projectId, clip, state, info, draft.patch);

  // Cmd/Ctrl+Z = undo, Cmd/Ctrl+Shift+Z = redo (text boxes keep their own undo)
  useEffect(() => {
    function handleKey(event) {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") return;
      if (event.target.closest?.("input:not([type]), input[type=text], textarea, [contenteditable]")) return;
      event.preventDefault();
      if (event.shiftKey) redo();
      else undo();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [undo, redo]);

  // The Chat tab's extras that aren't saved with the draft: what each AI reply changed, and app notes
  const [chatChanges, setChatChanges] = useState({}); // { [message index]: ["Trim 3.0–30.0 s", …] }
  const [chatNote, setChatNote] = useState(null);
  const latestState = useRef(state);
  useEffect(() => {
    latestState.current = state;
  });

  // "Make the captions yellow": the backend's editor AI returns a new edit + a reply.
  // The new edit goes in as ONE undo step, so Cmd+Z takes back the whole AI change.
  async function sendChat(message) {
    const history = draft.chat;
    const sent = state;
    draft.setChat([...history, { role: "user", text: message }]);
    setChatNote(null);
    setThinking(true);
    try {
      const result = await api.sendEditorChat(projectId, clip.job_id, clip.clip_index,
        { state: sent, chat: history.slice(-20), message });
      if (latestState.current !== sent) {
        toast.show("The AI's edit replaced changes you made while it was working. Undo to get them back.");
      }
      change(result.state);
      draft.setChat([...history, { role: "user", text: message }, { role: "assistant", text: result.message }]);
      setChatChanges((all) => ({ ...all, [history.length + 1]: describeChanges(sent, result.state) }));
    } catch (err) {
      draft.setChat(history);
      if (err.status === 503) setChatNote(err.message); // the editing AI isn't set up on the server
      else toast.show(err.message, "error");
    } finally {
      setThinking(false);
    }
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
        <button type="button" className="btn btn-small btn-primary editor-export" onClick={onExport}>Go to Export →</button>
      </div>

      <div className="editor-body">
        {sidebar}

        <main className="editor-center">
          <section className="editor-preview">
            {draft.error ? (
              <EmptyState icon="🌧️" title="Couldn't load this clip" text={draft.error.message} />
            ) : info && state ? (
              <ClipPlayer projectId={projectId} clip={clip} info={info} state={state} controlRef={player}
                framing={{ patch: draft.patch, recordUndo: draft.recordUndo }} />
            ) : (
              <div className="editor-loading"><Spinner label="Loading clip" /></div>
            )}
          </section>
          {info && state && (
            <section className="editor-timeline" aria-label="Timeline">
              <Timeline duration={info.duration} cues={info.cues} state={state} player={player}
                change={change} patch={draft.patch} recordUndo={draft.recordUndo}
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
                onClick={() => setPanelTab(tab)}>{tab}</button>
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
            ) : (
              <ChatBox messages={chatMessages} onSend={sendChat} disabled={thinking} typing={thinking}
                quickActions={draft.chat.length === 0 ? chatSuggestions : []}
                placeholder={thinking ? "Editing…" : "e.g. cut the first 2 seconds, make captions yellow"} />
            )}
          </div>
        </aside>
      </div>
    </>
  );
}

export default EditorPage;
