import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./EditorPage.css";
import TopBar from "../components/TopBar";
import ChatBox from "../components/ChatBox";
import SequencePlayer from "../components/SequencePlayer";
import { useProject } from "../context/ProjectContext";
import { formatTime } from "../utils/time";

const sidebarTabs = ["Media", "B-roll", "Brand Assets", "Stickers"];
const panelTabs = ["Chat", "Captions", "Aspect Ratio"];
const ratios = [
  { id: "16:9", label: "16:9 Horizontal" },
  { id: "9:16", label: "9:16 Vertical" },
  { id: "1:1", label: "1:1 Square" },
];

// Built from the Figma "Editor" wireframe (node 560:2716)
function EditorPage() {
  const navigate = useNavigate();
  const { project, sourceVideo, selectedClips, stepsUnlocked, aspectRatio, setAspectRatio } = useProject();

  const [currentIndex, setCurrentIndex] = useState(0);     // which clip the preview shows
  const [sidebarTab, setSidebarTab] = useState("Media");
  const [panelTab, setPanelTab] = useState("Chat");
  const [chat, setChat] = useState([]);                    // the editor's own chat
  const [captionsOn, setCaptionsOn] = useState(false);

  const sourceUrl = sourceVideo?.url ?? null;

  function handleChat(text) {
    setChat([...chat, { role: "user", text },
      { role: "assistant", text: "Got it! Editing by chat is coming soon." }]);
  }

  return (
    <div className="editor">
      <TopBar title={project?.name} activeStep="editor" stepsUnlocked={stepsUnlocked} />

      {/* Tool strip: 87 tall */}
      <div className="editor-tools">
        <button type="button" className="btn btn-small" disabled>↶ Undo</button>
        <button type="button" className="btn btn-small" disabled>↷ Redo</button>
        <button type="button" className="btn btn-small" disabled>✂ Split</button>
        <button type="button" className="btn btn-small" disabled>🗑 Delete</button>
        <button
          type="button"
          className={`btn btn-small editor-export ${stepsUnlocked ? "btn-primary" : "disabled"}`}
          disabled={!stepsUnlocked}
          onClick={() => navigate("/export")}
        >
          Go to Export →
        </button>
      </div>

      <div className="editor-body">
        {/* Left sidebar: Media, B-roll, Brand Assets, Stickers */}
        <aside className="editor-sidebar">
          {sidebarTabs.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`editor-sidebar-tab${tab === sidebarTab ? " active" : ""}`}
              onClick={() => setSidebarTab(tab)}
            >
              {tab}
            </button>
          ))}

          <div className="editor-sidebar-content">
            {sidebarTab === "Media" ? (
              selectedClips.map((clip, index) => (
                <button
                  key={clip.id}
                  type="button"
                  className={`editor-media-item${index === currentIndex ? " active" : ""}`}
                  onClick={() => setCurrentIndex(index)}
                >
                  Clip {index + 1}
                  <span>{formatTime(clip.start)} – {formatTime(clip.end)}</span>
                </button>
              ))
            ) : (
              <p className="editor-coming-soon">{sidebarTab} coming soon</p>
            )}
          </div>
        </aside>

        {/* Center: preview + timeline */}
        <main className="editor-center">
          <section className="editor-preview">
            <SequencePlayer
              sourceUrl={sourceUrl}
              clips={selectedClips}
              currentIndex={currentIndex}
              onIndexChange={setCurrentIndex}
              aspectRatio={aspectRatio}
            />
            {captionsOn && <p className="editor-caption">Captions will appear here</p>}
          </section>

          <section className="editor-timeline">
            <div className="editor-track">
              {selectedClips.map((clip, index) => (
                <button
                  key={clip.id}
                  type="button"
                  className={`editor-block${index === currentIndex ? " active" : ""}`}
                  style={{ flexGrow: clip.end - clip.start }}
                  onClick={() => setCurrentIndex(index)}
                  title={`${formatTime(clip.start)} – ${formatTime(clip.end)}`}
                >
                  {index + 1}
                </button>
              ))}
              {selectedClips.length === 0 && <p className="editor-coming-soon">No clips yet. Pick some in AI Studio.</p>}
            </div>
            {/* Audio waveform placeholder */}
            <div className="editor-waveform" />
          </section>
        </main>

        {/* Right panel: Chat / Captions / Aspect Ratio */}
        <aside className="editor-panel">
          <div className="editor-panel-tabs">
            {panelTabs.map((tab) => (
              <button
                key={tab}
                type="button"
                className={`editor-panel-tab${tab === panelTab ? " active" : ""}`}
                onClick={() => setPanelTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="editor-panel-content">
            {panelTab === "Chat" && (
              <ChatBox messages={chat} onSend={handleChat} placeholder="Ask for an edit..." />
            )}

            {panelTab === "Captions" && (
              <label className="editor-option">
                <input type="checkbox" checked={captionsOn} onChange={(e) => setCaptionsOn(e.target.checked)} />
                Show captions
              </label>
            )}

            {panelTab === "Aspect Ratio" && (
              <div className="editor-ratios">
                {ratios.map((ratio) => (
                  <button
                    key={ratio.id}
                    type="button"
                    className={`editor-ratio${ratio.id === aspectRatio ? " active" : ""}`}
                    onClick={() => setAspectRatio(ratio.id)}
                  >
                    {ratio.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default EditorPage;
