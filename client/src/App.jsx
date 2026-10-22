import { Routes, Route } from "react-router-dom";
import LandingPage from "./pages/LandingPage";
import ProjectsPage from "./pages/ProjectsPage";
import StudioPage from "./pages/StudioPage";
import EditorPage from "./pages/EditorPage";
import ExportPage from "./pages/ExportPage";
// Fawaz's versions, kept so the team can compare (not linked from the app)
import LandingPageAlt from "./pages/LandingPageAlt";
import ProjectsArchivePage from "./pages/ProjectsArchivePage";

// Flow: Landing -> Projects -> (new project) AI Studio -> Editor -> Export
//                          -> (existing project) Editor -> Export
function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/studio" element={<StudioPage />} />
      <Route path="/editor" element={<EditorPage />} />
      <Route path="/export" element={<ExportPage />} />
      <Route path="/landing-alt" element={<LandingPageAlt />} />
      <Route path="/projects-alt" element={<ProjectsArchivePage />} />
    </Routes>
  );
}

export default App;
