import { Routes, Route } from "react-router-dom";
import Landing from "./pages/Landing";
import LandingVideo from "./pages/LandingVideo";
import ProjectsPage from "./pages/ProjectsPage";
import DrawingPage from "./pages/DrawingPage";
import EditorPage from "./pages/EditorPage";
import ExportPage from "./pages/ExportPage";

const USE_VIDEO = true;   // ← flip to switch the landing between video and letters

function App() {
  return (
    <Routes>
      <Route path="/" element={USE_VIDEO ? <LandingVideo /> : <Landing />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/new" element={<DrawingPage />} />
      <Route path="/editor" element={<EditorPage />} />
      <Route path="/export" element={<ExportPage />} />
    </Routes>
  );
}

export default App;