import { Routes, Route } from "react-router-dom";
import RequireSignIn from "./auth/RequireSignIn";
import LandingPage from "./pages/LandingPage";
import SignInPage from "./pages/SignInPage";
import ProjectsPage from "./pages/ProjectsPage";
import StudioPage from "./pages/StudioPage";
import EditorPage from "./pages/EditorPage";
import ExportPage from "./pages/ExportPage";
import NotFoundPage from "./pages/NotFoundPage";

// Routes only. The project (and AI Studio session) live in the URL,
// so refresh and the back button keep you on the same page.
//   Flow: Landing -> Projects -> (new project) AI Studio -> Editor -> Export
//                            -> (existing project) Editor -> Export
function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/sign-in/*" element={<SignInPage />} />

      {/* Everything inside here needs a signed-in user (or dev mode) */}
      <Route element={<RequireSignIn />}>
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId/studio/:sessionId?" element={<StudioPage />} />
        <Route path="/projects/:projectId/editor" element={<EditorPage />} />
        <Route path="/projects/:projectId/export" element={<ExportPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default App;
