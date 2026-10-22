import { Routes, Route } from "react-router-dom";
import LandingPage from "./pages/LandingPage";
import ProjectsPage from "./pages/ProjectsPage";
import StudioPage from "./pages/StudioPage";
import EditorPage from "./pages/EditorPage";
import ExportPage from "./pages/ExportPage";

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
    </Routes>
  );
}

export default App;
