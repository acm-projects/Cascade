import { createContext, useContext, useState } from "react";

// The project being worked on, shared by AI Studio -> Editor -> Export.
// Any page can read it with:  const project = useProject();
const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const [project, setProject] = useState(null);           // { id, name, isExisting }
  const [sourceVideo, setSourceVideo] = useState(null);   // the dropped video: { name, url, duration }
  const [messages, setMessages] = useState([]);           // AI Studio chat: [{ role, text }]
  const [clips, setClips] = useState([]);                 // generated / saved clips: [{ id, start, end, x, y, batch }]
  const [sourcePos, setSourcePos] = useState({ x: 80, y: 260 }); // where the video node sits on the AI Studio canvas
  const [selectedIds, setSelectedIds] = useState([]);     // which clips go to the editor
  const [aspectRatio, setAspectRatio] = useState("16:9"); // chosen in the editor, used by export

  function resetWork() {
    if (sourceVideo) URL.revokeObjectURL(sourceVideo.url);
    setSourceVideo(null);
    setMessages([]);
    setClips([]);
    setSelectedIds([]);
    setAspectRatio("16:9");
    setSourcePos({ x: 80, y: 260 });
  }

  // "+ New Project" on the Projects page. Returns the new id so the page can go to /projects/<id>/studio.
  // FAKE id until the backend creates real projects (ticket 1.6).
  function startNewProject() {
    resetWork();
    const id = `draft-${Date.now().toString(36)}`;
    setProject({ id, name: "Untitled project", isExisting: false });
    return id;
  }

  // Clicking an existing project. Real projects from the backend don't carry clips yet (loading them is
  // ticket 3.4), so clips are optional.
  function openProject(saved) {
    resetWork();
    setProject({ id: saved.id, name: saved.name, isExisting: true });
    const savedClips = saved.clips ?? [];
    setClips(savedClips);
    setSelectedIds(savedClips.map((clip) => clip.id));
  }

  // Selected clips, in the order the user picked them (that's their order in the editor)
  const selectedClips = selectedIds
    .map((id) => clips.find((clip) => clip.id === id))
    .filter(Boolean);

  const value = {
    project, setProject,
    sourceVideo, setSourceVideo,
    messages, setMessages,
    clips, setClips,
    sourcePos, setSourcePos,
    selectedIds, setSelectedIds,
    selectedClips,
    aspectRatio, setAspectRatio,
    startNewProject, openProject,
    // Editor and Export unlock once there are clips to work with
    stepsUnlocked: selectedClips.length > 0,
  };

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  return useContext(ProjectContext);
}
