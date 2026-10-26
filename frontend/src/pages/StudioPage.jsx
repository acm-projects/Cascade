import { useCallback, useMemo } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import "./StudioPage.css";
import TopNav from "../components/TopNav";
import EmptyState from "../components/ui/EmptyState";
import { useProject } from "../context/ProjectContext";
import SessionBar from "../features/studio/SessionBar";
import ChatPanel from "../features/studio/ChatPanel";
import StudioCanvas from "../features/studio/StudioCanvas";
import { nodeTypes } from "../features/studio/nodes";
import { edgeTypes } from "../features/studio/edges";
import { mockSession, makeFakeClips, layoutBatch, buildPretendGraph } from "../features/studio/mockData";

// AI Studio (Figma Page 7 "AI Studio Page"): TopNav, session bar, chat on the left, big canvas on the right.
// The flow is PRETEND for demos: upload a video -> each prompt grows a branch of fake clips ->
// pick clips -> Go to Editor. Real data comes in 3.4, the session dropdown in 3.6.
function StudioPage() {
  const navigate = useNavigate();
  const { projectId, sessionId } = useParams();
  const {
    project, sourceVideo, setSourceVideo, messages, setMessages,
    prompts, setPrompts, clips, setClips, selectedIds, setSelectedIds, stepsUnlocked,
  } = useProject();
  const isGenerating = prompts.some((prompt) => prompt.loading);

  // --- The video (stays in your browser for now) ---
  // useCallback: these only change when the video does, so the canvas isn't rebuilt on every render
  const loadVideo = useCallback((file) => {
    if (!file?.type.startsWith("video/")) return;
    if (sourceVideo) URL.revokeObjectURL(sourceVideo.url);
    setSourceVideo({ name: file.name, url: URL.createObjectURL(file), duration: 0 });
    setPrompts([]);
    setClips([]);
    setSelectedIds([]);
    setMessages((current) => [...current,
      { role: "assistant", text: `Got ${file.name}! What kind of clips should I find?` }]);
  }, [sourceVideo, setSourceVideo, setPrompts, setClips, setSelectedIds, setMessages]);

  const removeVideo = useCallback(() => {
    URL.revokeObjectURL(sourceVideo.url);
    setSourceVideo(null);
    setPrompts([]);
    setClips([]);
    setSelectedIds([]);
  }, [sourceVideo, setSourceVideo, setPrompts, setClips, setSelectedIds]);

  // --- Prompting: each prompt grows a new branch of clips ---
  function handleSend(text, clipCount) {
    const reply = (answer) =>
      setMessages((current) => [...current, { role: "user", text }, { role: "assistant", text: answer }]);

    if (!sourceVideo) {
      reply("Drop a video on the canvas first, then tell me what to find!");
      return;
    }
    if (/caption/i.test(text)) {
      reply("Captions are added in the Editor. Pick your clips, then head there!");
      return;
    }

    const batch = prompts.length;
    const promptId = `prompt-${batch}`;
    const { prompt: promptSpot, spots } = layoutBatch(prompts, clips, clipCount);
    setPrompts((current) => [...current, { id: promptId, text, batch, ...promptSpot, loading: true }]);
    reply(`Looking through ${sourceVideo.name} for: "${text}"...`);

    // Pretend the AI takes 2 seconds (the backend replaces this in ticket 3.4)
    setTimeout(() => {
      const found = makeFakeClips(sourceVideo.duration, clipCount);
      setClips((current) => [...current,
        ...found.map((clip, i) => ({ ...clip, id: `${batch}-${i}`, batch, ...spots[i] }))]);
      setPrompts((current) => current.map((p) => (p.id === promptId ? { ...p, loading: false } : p)));
      setMessages((current) => [...current,
        { role: "assistant", text: `Found ${found.length} clips! Click the ones you want, then go to the Editor.` }]);
    }, 2000);
  }

  // Boxes and lines for the canvas. useMemo: only rebuild them when the video, prompts or clips change
  // (picking a clip doesn't rebuild anything: the clip box reads that itself).
  const graph = useMemo(
    () => buildPretendGraph({
      sourceVideo,
      prompts,
      clips,
      sourceActions: {
        onFile: loadVideo,
        onRemove: removeVideo,
        onDuration: (duration) => setSourceVideo((current) => current && { ...current, duration }),
      },
    }),
    [sourceVideo, prompts, clips, loadVideo, removeVideo, setSourceVideo]
  );

  // TEMPORARY until ticket 3.6 remembers your last session: coming back from the Editor
  // (whose URL has no session) with work in progress goes straight back to it
  if (!sessionId && sourceVideo) {
    return <Navigate to={`/projects/${projectId}/studio/${mockSession.id}`} replace />;
  }


  return (
    <div className={`studio leaf-page${sessionId ? "" : " studio-no-session"}`}>
      <TopNav
        projectTitle={project?.name}
        active="studio"
        canOpenEditor={stepsUnlocked}
        canOpenExport={stepsUnlocked}
      />

      {sessionId ? (
        <>
          <SessionBar name={mockSession.name}>
            {clips.length > 0 && <span>{selectedIds.length} of {clips.length} picked</span>}
            <button
              type="button"
              className={`btn btn-small ${stepsUnlocked ? "btn-primary" : "disabled"}`}
              disabled={!stepsUnlocked}
              title={stepsUnlocked ? undefined : "Pick at least one clip first"}
              onClick={() => navigate(`/projects/${projectId}/editor`)}
            >
              Go to Editor →
            </button>
          </SessionBar>
          <div className="studio-body">
            <ChatPanel messages={messages} onSend={handleSend} disabled={isGenerating} />
            <div className="studio-canvas-frame">
              <StudioCanvas
                nodes={graph.nodes}
                edges={graph.edges}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                onDropFile={loadVideo}
              />
            </div>
          </div>
        </>
      ) : (
        // No session in the URL. Picking/creating real sessions is ticket 3.6.
        <div className="studio-empty">
          <div className="studio-empty-card wood-panel">
            <EmptyState
              icon="🌱"
              title="Pick or create a session"
              text="A session is one round of prompts and clips for this project."
              action={{
                label: "Start a session",
                onClick: () => navigate(`/projects/${projectId}/studio/${mockSession.id}`),
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default StudioPage;
