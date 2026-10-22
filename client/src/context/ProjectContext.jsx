import { createContext, useContext, useState } from "react";

// The project being worked on, shared by AI Studio -> Editor -> Export.
// Any page can read it with:  const project = useProject();
const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const [project, setProject] = useState(null);           // { id, name, isExisting }
  const [sourceVideo, setSourceVideo] = useState(null);   // the dropped video: { name, url, duration }
  const [messages, setMessages] = useState([]);           // AI Studio chat: [{ role, text }]
  const [clips, setClips] = useState([]);                 // generated / saved clips: [{ id, start, end }]
  const [selectedIds, setSelectedIds] = useState([]);     // which clips go to the editor
  const [aspectRatio, setAspectRatio] = useState("16:9"); // chosen in the editor, used by export

  function resetWork() {
    if (sourceVideo) URL.revokeObjectURL(sourceVideo.url);
    setSourceVideo(null);
    setMessages([]);
    setClips([]);
    setSelectedIds([]);
    setAspectRatio("16:9");
  }

  // "+ New Project" on the Projects page
  function startNewProject() {
    resetWork();
    setProject({ id: "new", name: "Untitled project", isExisting: false });
  }

  // Clicking an existing project: it goes straight to the editor with its saved clips
  function openProject(saved) {
    resetWork();
    setProject({ id: saved.id, name: saved.name, isExisting: true });
    setClips(saved.clips);
    setSelectedIds(saved.clips.map((clip) => clip.id));
  }

  const selectedClips = clips.filter((clip) => selectedIds.includes(clip.id));

  const value = {
    project, setProject,
    sourceVideo, setSourceVideo,
    messages, setMessages,
    clips, setClips,
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
