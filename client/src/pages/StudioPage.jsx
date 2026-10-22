import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./StudioPage.css";
import TopBar from "../components/TopBar";
import ChatBox from "../components/ChatBox";
import ClipCard from "../components/ClipCard";
import { useProject } from "../context/ProjectContext";

// FAKE results for now: pick a few random moments from the video.
// Later, the backend will send back real { start, end } times for the prompt.
function makeFakeClips(duration) {
  const length = Number.isFinite(duration) && duration > 0 ? duration : 30;
  const count = 3 + Math.floor(Math.random() * 4);            // 3 to 6 clips
  const clips = [];
  for (let i = 0; i < count; i++) {
    const clipLength = Math.min(2 + Math.random() * 4, length);
    const start = Math.random() * (length - clipLength);
    clips.push({ id: i, start, end: start + clipLength });
  }
  return clips.sort((a, b) => a.start - b.start);
}

// Built from the Figma "AI Studio Page" wireframe (node 546:2168)
function StudioPage() {
  const navigate = useNavigate();
  const {
    project, sourceVideo, setSourceVideo, messages, setMessages,
    clips, setClips, selectedIds, setSelectedIds, stepsUnlocked,
  } = useProject();

  const [showSource, setShowSource] = useState(true);      // the ▼ on the top bar
  const [isDragging, setIsDragging] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  // --- Dropping a clip ---
  function loadVideo(file) {
    if (!file || !file.type.startsWith("video/")) return;
    if (sourceVideo) URL.revokeObjectURL(sourceVideo.url);
    setSourceVideo({ name: file.name, url: URL.createObjectURL(file), duration: 0 });
    setClips([]);
    setSelectedIds([]);
    setShowSource(true);
    setMessages((current) => [
      ...current,
      { role: "assistant", text: `Got ${file.name}! What kind of clips should I find?` },
    ]);
  }

  function removeVideo() {
    URL.revokeObjectURL(sourceVideo.url);
    setSourceVideo(null);
    setClips([]);
    setSelectedIds([]);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    loadVideo(e.dataTransfer.files[0]);
  }

  // --- Prompting the chat bot ---
  function handleSend(text) {
    const userMessage = { role: "user", text };

    if (!sourceVideo) {
      setMessages([...messages, userMessage,
        { role: "assistant", text: "Drop a clip on the canvas first, then tell me what to find!" }]);
      return;
    }

    setMessages([...messages, userMessage,
      { role: "assistant", text: `Looking through ${sourceVideo.name} for: "${text}"...` }]);
    setClips([]);
    setSelectedIds([]);
    setIsGenerating(true);

    // Pretend the AI takes 2 seconds (the backend will replace this)
    setTimeout(() => {
      const results = makeFakeClips(sourceVideo.duration);
      setClips(results);
      setIsGenerating(false);
      setMessages((current) => [...current,
        { role: "assistant", text: `Found ${results.length} clips! Select the ones you want.` }]);
    }, 2000);
  }

  // --- Selecting clips ---
  function toggleClip(id) {
    setSelectedIds(selectedIds.includes(id)
      ? selectedIds.filter((selectedId) => selectedId !== id)
      : [...selectedIds, id]);
  }

  return (
    <div className="studio">
      <TopBar title={project?.name} activeStep="studio" stepsUnlocked={stepsUnlocked} />

      <div className="studio-body">
        {/* Collapsible bar: show/hide the source video, and the Go to Editor button */}
        <div className="studio-bar">
          <button
            type="button"
            className={`studio-toggle${showSource ? "" : " collapsed"}`}
            onClick={() => setShowSource(!showSource)}
            title={showSource ? "Hide source video" : "Show source video"}
          >
            ▼
          </button>
          <span className="studio-bar-label">
            {sourceVideo ? `Source video: ${sourceVideo.name}` : "No clip yet: drop one on the canvas"}
          </span>
          <span className="studio-bar-count">
            {clips.length > 0 && `${selectedIds.length} of ${clips.length} clips selected`}
          </span>
          <button
            type="button"
            className={`btn btn-small ${stepsUnlocked ? "btn-primary" : "disabled"}`}
            disabled={!stepsUnlocked}
            onClick={() => navigate("/editor")}
          >
            Go to Editor →
          </button>
        </div>

        <div className="studio-panels">
          {/* Left: chat bot */}
          <section className="studio-chat">
            <ChatBox
              title="Chat bot"
              messages={messages}
              onSend={handleSend}
              disabled={isGenerating}
              placeholder={sourceVideo ? "Describe the clips you want..." : "Drop a clip first..."}
              tag={sourceVideo?.name}
              onRemoveTag={removeVideo}
            />
          </section>

          {/* Right: dotted canvas. Drop a clip here; generated clips appear here */}
          <section
            className={`studio-canvas${isDragging ? " dragging" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            {!sourceVideo && (
              <label className="studio-dropzone">
                <input type="file" accept="video/*" hidden onChange={(e) => loadVideo(e.target.files[0])} />
                <span className="studio-dropzone-title">Drop a clip here</span>
                <span className="studio-dropzone-hint">or click to browse</span>
              </label>
            )}

            {sourceVideo && showSource && (
              <div className="studio-source">
                <video
                  className="studio-source-video"
                  src={sourceVideo.url}
                  controls
                  muted
                  playsInline
                  onLoadedMetadata={(e) => {
                    const duration = e.target.duration;
                    setSourceVideo((current) => ({ ...current, duration }));
                  }}
                />
              </div>
            )}

            {isGenerating && <p className="studio-loading">🌿 Finding your clips...</p>}

            {clips.length > 0 && (
              <div className="studio-clips">
                {clips.map((clip) => (
                  <ClipCard
                    key={clip.id}
                    sourceUrl={sourceVideo.url}
                    start={clip.start}
                    end={clip.end}
                    isSelected={selectedIds.includes(clip.id)}
                    onToggle={() => toggleClip(clip.id)}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

export default StudioPage;
