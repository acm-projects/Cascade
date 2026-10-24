import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import RequireSignIn from "./auth/RequireSignIn";
import LandingPage from "./pages/LandingPage";
import SignInPage from "./pages/SignInPage";
import ProjectsPage from "./pages/ProjectsPage";
import EditorPage from "./pages/EditorPage";
import ExportPage from "./pages/ExportPage";
import NotFoundPage from "./pages/NotFoundPage";
import Spinner from "./components/ui/Spinner";

// AI Studio brings in React Flow (a big library), so it's downloaded only when someone opens it
const StudioPage = lazy(() => import("./pages/StudioPage"));

// The UI kit showroom only exists in `npm run dev`. In a real build import.meta.env.DEV is false,
// so this page isn't even included in the app's code.
const UiPreviewPage = import.meta.env.DEV ? lazy(() => import("./pages/UiPreviewPage")) : null;

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
        <Route
          path="/projects/:projectId/studio/:sessionId?"
          element={
            <Suspense fallback={<div className="page-loading"><Spinner size={48} label="Loading AI Studio" /></div>}>
              <StudioPage />
            </Suspense>
          }
        />
        <Route path="/projects/:projectId/editor" element={<EditorPage />} />
        <Route path="/projects/:projectId/export" element={<ExportPage />} />
      </Route>

      {UiPreviewPage && (
        <Route path="/dev/ui" element={<Suspense fallback={null}><UiPreviewPage /></Suspense>} />
      )}

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default App;
