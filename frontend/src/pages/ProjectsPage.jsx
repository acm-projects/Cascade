import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import "./ProjectsPage.css";
import bg from "../assets/figma/projects-bg.jpg";
import woodPill from "../assets/figma/wood-pill.png";
import woodGreen from "../assets/figma/wood-green-btn.png";
import leafCream from "../assets/icons/leaf-cream.svg";
import searchIcon from "../assets/icons/search.svg";
import { useProject } from "../context/ProjectContext";
import useApi from "../api/useApi";
import ProjectCard from "../components/ProjectCard";
import UserAvatar from "../components/UserAvatar";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import Spinner from "../components/ui/Spinner";
import { useToast } from "../components/ui/ToastContext";

const WEEK_SECONDS = 7 * 24 * 60 * 60;

// Left sidebar (hard-coded, as the Figma meeting note says). The chosen one lives in the URL: ?view=recent
// Favorites / Archives / Trash need backend support first (ticket 7.5), so they say "coming soon".
const views = [
  { id: "all", label: "All Projects", test: () => true },
  { id: "recent", label: "Recents", test: (p) => Date.now() / 1000 - (p.updated_at ?? p.created_at) < WEEK_SECONDS },
  { id: "favorites", label: "Favorites", soon: { icon: "⭐", text: "Star your favorite projects to find them here." } },
  { id: "archives", label: "Archives", soon: { icon: "📦", text: "Archived projects will be tucked away here." } },
  { id: "trash", label: "Trash", soon: { icon: "🗑️", text: "Deleted projects will wait here before they're gone." } },
];

// Built from the Figma "Projects/Archive Page" (section 2, node 640:529)
function ProjectsPage() {
  const navigate = useNavigate();
  const api = useApi();
  const toast = useToast();
  const { startNewProject, openProject } = useProject();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");

  // What we got from the backend
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // The project waiting for "Are you sure?" (null = no pop-up)
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // Each load gets a number, so if Retry is clicked twice only the newest answer is used.
  // (The page starts with loading = true, so this only sets state once the answer arrives.)
  const loadCount = useRef(0);

  const loadProjects = useCallback(() => {
    const thisLoad = ++loadCount.current;
    api
      .listProjects()
      .then((result) => thisLoad === loadCount.current && setProjects(result.projects))
      .catch((err) => thisLoad === loadCount.current && setError(err))
      .finally(() => thisLoad === loadCount.current && setLoading(false));
  }, [api]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  function retry() {
    setLoading(true);
    setError(null);
    loadProjects();
  }

  const view = views.find((v) => v.id === searchParams.get("view")) ?? views[0];
  const query = search.trim().toLowerCase();
  const shown = view.soon
    ? []
    : projects.filter((p) => view.test(p) && p.name.toLowerCase().includes(query));

  function chooseView(id) {
    setSearchParams(id === "all" ? {} : { view: id });
  }

  // TEMPORARY until the "New Project" pop-up (ticket 2.6): starts a local draft and opens AI Studio
  function handleNewProject() {
    const id = startNewProject();
    navigate(`/projects/${id}/studio`);
  }

  function handleOpen(project) {
    openProject(project);
    navigate(`/projects/${project.id}/studio`);
  }

  async function confirmDelete() {
    const project = toDelete;
    setDeleting(true);
    try {
      await api.deleteProject(project.id);
      setProjects((list) => list.filter((p) => p.id !== project.id));
      toast.show(`Deleted "${project.name}"`);
    } catch (err) {
      // e.g. 409 "Stop active generation/research ... before deleting this project."
      toast.show(err.message, "error");
    } finally {
      setDeleting(false);
      setToDelete(null);
    }
  }

  // Pick what goes in the main area: one of six "moods"
  function renderContent() {
    // Coming-soon views don't need any data, so they never wait for the backend
    if (view.soon) {
      return <EmptyState icon={view.soon.icon} title="Coming soon" text={view.soon.text} />;
    }
    if (loading) {
      return (
        <div className="projects-state">
          <Spinner size={48} label="Loading your projects" />
        </div>
      );
    }
    if (error) {
      return (
        <div className="projects-state">
          <div className="projects-error wood-panel" role="alert">
            <h2>Couldn't load your projects</h2>
            <p>{error.message}</p>
            <Button variant="primary" size="sm" onClick={retry}>Retry</Button>
          </div>
        </div>
      );
    }
    if (projects.length === 0) {
      return (
        <EmptyState
          icon="🌿"
          title="No projects yet"
          text="Upload a video and Cascade will find the best clips for you."
          action={{ label: "Create your first project", onClick: handleNewProject }}
        />
      );
    }
    if (shown.length === 0) {
      return query ? (
        <EmptyState icon="🔍" title={`No projects match "${search.trim()}"`} text="Try a different name." />
      ) : (
        <EmptyState icon="🕰️" title="Nothing from the last 7 days" text="Projects you work on this week show up here." />
      );
    }
    return (
      <div className="projects-grid">
        {shown.map((project) => (
          <ProjectCard key={project.id} project={project} onOpen={handleOpen} onDelete={setToDelete} />
        ))}
        <button type="button" className="project-card-new" onClick={handleNewProject}>
          <span className="project-card-new-plus" aria-hidden="true">+</span>
          <span className="project-card-new-title">New Project</span>
          <span className="project-card-new-text">Upload a video to get started</span>
        </button>
      </div>
    );
  }

  return (
    <div className="projects" style={{ backgroundImage: `url(${bg})` }}>
      {/* Green top bar */}
      <header className="projects-bar">
        <div className="projects-brand">
          <img src={leafCream} alt="" className="projects-leaf" />
          <span>Cascade</span>
        </div>
        <UserAvatar />
      </header>

      <div className="projects-body">
        {/* Left sidebar: wooden view buttons */}
        <nav className="projects-sidebar" aria-label="Project views">
          {views.map((v) => (
            <button
              key={v.id}
              type="button"
              className={`projects-filter${v.id === view.id ? " active" : ""}`}
              style={{ backgroundImage: `url(${woodPill})` }}
              aria-current={v.id === view.id ? "page" : undefined}
              onClick={() => chooseView(v.id)}
            >
              {v.label}
            </button>
          ))}
        </nav>

        {/* Main area */}
        <main className="projects-main">
          <div className="projects-header">
            <div>
              <h1 className="projects-title">Your Projects</h1>
              <p className="projects-subtitle">Create, edit, and manage your videos</p>
            </div>

            <div className="projects-actions">
              <label className="projects-search" style={{ backgroundImage: `url(${woodPill})` }}>
                <img src={searchIcon} alt="" />
                <input
                  type="search"
                  aria-label="Search projects"
                  placeholder="Search projects..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="projects-new"
                style={{ backgroundImage: `url(${woodGreen})` }}
                onClick={handleNewProject}
              >
                + New Project
              </button>
            </div>
          </div>

          <div className="projects-content">{renderContent()}</div>
        </main>
      </div>

      {toDelete && (
        <Modal title="Delete project?" onClose={() => !deleting && setToDelete(null)}>
          <p className="projects-delete-text">
            Delete <strong>{toDelete.name}</strong>? This removes its sessions and clips.
          </p>
          <div className="projects-delete-actions">
            <Button variant="ghost" size="sm" onClick={() => setToDelete(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={confirmDelete} disabled={deleting}>
              {deleting ? <Spinner size={14} label="Deleting" /> : "Delete"}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default ProjectsPage;
