import { useState } from "react";
import { ProjectContext } from "./projectContextValue";

// Shares the project you opened (see projectContextValue.js). Pages read it with useProject().
export function ProjectProvider({ children }) {
  const [project, setProject] = useState(null); // { id, name }

  // Clicking a project (or creating one) on the Projects page
  function openProject(saved) {
    setProject({ id: saved.id, name: saved.name });
  }

  return <ProjectContext.Provider value={{ project, openProject }}>{children}</ProjectContext.Provider>;
}
