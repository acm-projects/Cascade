import { createContext, useContext } from "react";

// The project you opened on the Projects page: { id, name }. Lets the AI Studio show the name
// right away while it loads the rest from the backend. Filled in by ProjectProvider.
export const ProjectContext = createContext(null);

export function useProject() {
  return useContext(ProjectContext);
}
