import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./StudioPage.css";
import TopBar from "../components/TopBar";
import ChatBox from "../components/ChatBox";
import ClipCard from "../components/ClipCard";
import BranchCanvas from "../components/BranchCanvas";
import { useProject } from "../context/ProjectContext";
import { layoutBatch, arrangeClips } from "../utils/canvasLayout";

// Buttons under the chat box that send a ready-made prompt
const quickActions = [
  { label: "✦ Generate Clips", prompt: "Find the best moments for short clips" },
  { label: "CC Add Captions", prompt: "Add captions to my clips" },
];

// FAKE results for now: pick a few random moments from the video.
// Later, the backend will send back real { start, end } times for the prompt.
function makeFakeClips(duration) {
  const length = Number.isFinite(duration) && duration > 0 ? duration : 30;
  const count = 3 + Math.floor(Math.random() * 2);            // 3 or 4 clips
  const clips = [];
  for (let i = 0; i < count; i++) {
    const clipLength = Math.min(2 + Math.random() * 4, length);
    const start = Math.random() * (length - clipLength);
    clips.push({ start, end: start + clipLength });
  }
  return clips.sort((a, b) => a.start - b.start);
}

// AI Studio: chat on the left, the branch canvas on the right
function StudioPage() {
  const navigate = useNavigate();
  const {
    project, sourceVideo, setSourceVideo, messages, setMessages,
    clips, setClips, selectedIds, setSelectedIds, stepsUnlocked, sourcePos, setSourcePos,
  } = useProject();
  const [isGenerating, setIsGenerating] = useState(false);

  const batchCount = new Set(clips.map((clip) => clip.batch)).size;
  // Placeholder nodes where the next clips will appear, while the AI "thinks"
  const ghosts = isGenerating ? layoutBatch(sourcePos, batchCount, 3) : [];

  // --- The video ---
  function loadVideo(file) {
    if (!file || !file.type.startsWith("video/")) return;
    if (sourceVideo) URL.revokeObjectURL(sourceVideo.url);
    setSourceVideo({ name: file.name, url: URL.createObjectURL(file), duration: 0 });
    setClips([]);
    setSelectedIds([]);
    setMessages((current) => [...current,
      { role: "assistant", text: `Got ${file.name}! What kind of clips should I find?` }]);
  }

  function removeVideo() {
    URL.revokeObjectURL(sourceVideo.url);
    setSourceVideo(null);
    setClips([]);
    setSelectedIds([]);
  }

  // --- Prompting ---
  function handleSend(text) {
    const userMessage = { role: "user", text };

    if (!sourceVideo) {
      setMessages([...messages, userMessage,
        { role: "assistant", text: "Drop a video on the canvas first, then tell me what to find!" }]);
      return;
    }
    if (/caption/i.test(text)) {
      setMessages([...messages, userMessage,
        { role: "assistant", text: "Captions are added in the Editor. Pick your clips, then head there!" }]);
      return;
    }

    setMessages([...messages, userMessage,
      { role: "assistant", text: `Looking through ${sourceVideo.name} for: "${text}"...` }]);
    setIsGenerating(true);

    // Pretend the AI takes 2 seconds (the backend will replace this).
    // Each prompt grows a new branch: a new column of clips.
    setTimeout(() => {
      const found = makeFakeClips(sourceVideo.duration);
      const spots = layoutBatch(sourcePos, batchCount, found.length);
      const newClips = found.map((clip, i) => ({
        ...clip, id: `${batchCount}-${i}`, batch: batchCount, ...spots[i],
      }));
      setClips((current) => [...current, ...newClips]);
      setIsGenerating(false);
      setMessages((current) => [...current,
        { role: "assistant", text: `Found ${found.length} clips! Click the ones you want, then go to the Editor.` }]);
    }, 2000);
  }

  // --- Clips on the canvas ---
  function toggleClip(id) {
    setSelectedIds(selectedIds.includes(id)
      ? selectedIds.filter((selectedId) => selectedId !== id)
      : [...selectedIds, id]);
  }

  function moveClip(id, pos) {
    setClips((current) => current.map((clip) => (clip.id === id ? { ...clip, ...pos } : clip)));
  }

  function removeClip(id) {
    setClips((current) => current.filter((clip) => clip.id !== id));
    setSelectedIds((current) => current.filter((selectedId) => selectedId !== id));
  }

  // What goes inside the video node
  function renderSource() {
    if (!sourceVideo) {
      return (
        <label className="studio-drop" data-no-drag>
          <input type="file" accept="video/*" hidden onChange={(e) => loadVideo(e.target.files[0])} />
          <span className="studio-drop-icon">▶</span>
          <span className="studio-drop-title">Drop a video here</span>
          <span className="studio-drop-hint">or click to upload</span>
          <span className="btn btn-primary studio-drop-btn">⬆ Upload Video</span>
        </label>
      );
    }
    return (
      <>
        <video
          className="studio-source-video"
          src={sourceVideo.url}
          controls
          muted
          playsInline
          data-no-drag
          onLoadedMetadata={(e) => {
            const duration = e.target.duration;
            setSourceVideo((current) => ({ ...current, duration }));
          }}
        />
        <div className="studio-source-name">
          <span>{sourceVideo.name}</span>
          <button type="button" data-no-drag onClick={removeVideo} title="Remove video">✕</button>
        </div>
      </>
    );
  }

  // What goes inside each clip node
  function renderClip(clip) {
    return (
      <>
        <ClipCard
          sourceUrl={sourceVideo?.url}
          start={clip.start}
          end={clip.end}
          isSelected={selectedIds.includes(clip.id)}
          onToggle={() => toggleClip(clip.id)}
        />
        <button type="button" className="studio-clip-remove" data-no-drag onClick={() => removeClip(clip.id)} title="Remove clip">
          ✕
        </button>
      </>
    );
  }

  return (
    <div className="studio leaf-page">
      <TopBar title={project?.name} activeStep="studio" stepsUnlocked={stepsUnlocked} />

      <div className="studio-body">
        <section className="studio-chat wood-panel">
          <ChatBox
            title="AI Assistant"
            subtitle="Turn your ideas into videos."
            onNewChat={() => setMessages([])}
            messages={messages}
            onSend={handleSend}
            disabled={isGenerating}
            placeholder={sourceVideo ? "Describe the clips you want..." : "Drop a video first..."}
            tag={sourceVideo?.name}
            onRemoveTag={removeVideo}
            quickActions={quickActions}
          />
        </section>

        <section className="studio-canvas">
          <BranchCanvas
            sourcePos={sourcePos}
            onMoveSource={setSourcePos}
            renderSource={renderSource}
            clips={clips}
            onMoveClip={moveClip}
            renderClip={renderClip}
            ghosts={ghosts}
            onDropFile={loadVideo}
            onArrange={() => setClips(arrangeClips(clips, sourcePos))}
            extra={
              <>
                {clips.length > 0 && (
                  <span className="studio-count">{selectedIds.length} of {clips.length} selected</span>
                )}
                <button
                  type="button"
                  className={`btn btn-small ${stepsUnlocked ? "btn-primary" : "disabled"}`}
                  disabled={!stepsUnlocked}
                  onClick={() => navigate("/editor")}
                >
                  Go to Editor →
                </button>
              </>
            }
          />
        </section>
      </div>
    </div>
  );
}

export default StudioPage;
