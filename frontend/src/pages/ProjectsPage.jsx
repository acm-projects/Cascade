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
import { deleteTrashedProjects, isTrashed, projectMatchesView } from "../utils/projectViews";
import ProjectCard from "../components/ProjectCard";
import UserAvatar from "../components/UserAvatar";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import Spinner from "../components/ui/Spinner";
import { useToast } from "../components/ui/ToastContext";

const views = [
  { id: "all", label: "All Projects" },
  { id: "recent", label: "Recents" },
  { id: "favorites", label: "Favorites" },
  { id: "archives", label: "Archives" },
  { id: "trash", label: "Trash" },
];

const emptyViews = {
  all: ["🌿", "No active projects", "Create a project or restore one from Archives or Trash."],
  recent: ["🕰️", "Nothing from the last 7 days", "Projects you work on this week show up here."],
  favorites: ["⭐", "No favorites yet", "Choose Favorite from a project's menu to find it here."],
  archives: ["📦", "No archived projects", "Archive a project from its menu to keep it here."],
  trash: ["🗑️", "Trash is empty", "Projects moved to trash can be restored here."],
};

// Built from the Figma "Projects/Archive Page" (section 2, node 640:529)
function ProjectsPage() {
  const navigate = useNavigate();
  const api = useApi();
  const toast = useToast();
  const { openProject } = useProject();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");

  // What we got from the backend
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Bulk deletion only runs after the user confirms the Trash dialog.
  const [emptyTrashOpen, setEmptyTrashOpen] = useState(false);
  const [updating, setUpdating] = useState(new Set());
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
  const trashedProjects = projects.filter(isTrashed);
  const shown = projects.filter((p) => projectMatchesView(p, view.id) && p.name.toLowerCase().includes(query));

  function chooseView(id) {
    setSearchParams(id === "all" ? {} : { view: id });
  }

  // Creates a real (empty) project on the backend and opens its AI Studio, where you pick the video.
  // TEMPORARY until the "New Project" pop-up (ticket 2.6) lets you name it first.
  async function handleNewProject() {
    try {
      const created = await api.createProject("Untitled project");
      openProject(created);
      navigate(`/projects/${created.id}/studio`);
    } catch (err) {
      toast.show(`Couldn't create a project: ${err.message}`, "error");
    }
  }

  function handleOpen(project) {
    openProject(project);
    navigate(`/projects/${project.id}/studio`);
  }

  async function handleUpdate(project, changes) {
    setUpdating((ids) => new Set(ids).add(project.id));
    // Discard any older list response so it cannot overwrite this mutation.
    ++loadCount.current;
    try {
      const updated = await api.updateProject(project.id, changes);
      setProjects((list) => list.map((p) => p.id === updated.id ? updated : p));
      if (changes.trashed === true) toast.show(`Moved "${project.name}" to trash`);
      if (changes.trashed === false) toast.show(`Restored "${project.name}"`);
    } catch (err) {
      toast.show(err.message, "error");
    } finally {
      setUpdating((ids) => { const next = new Set(ids); next.delete(project.id); return next; });
    }
  }

  async function confirmEmptyTrash() {
    setDeleting(true);
    // Use the existing owner-checked delete endpoint; retain projects that fail.
    const { removed, failures } = await deleteTrashedProjects(trashedProjects, api.deleteProject);
    setProjects((list) => list.filter((p) => !removed.has(p.id)));
    if (removed.size) toast.show(`Permanently deleted ${removed.size} project${removed.size === 1 ? "" : "s"}`);
    if (failures.length) toast.show(`Some projects could not be deleted. ${failures.join(" ")}`, "error");
    setDeleting(false);
    setEmptyTrashOpen(false);
  }

  // Loading, errors and empty states stay specific to the selected view.
  function renderContent() {
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
    if (projects.length === 0 && view.id === "all") {
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
        <EmptyState icon={emptyViews[view.id][0]} title={emptyViews[view.id][1]} text={emptyViews[view.id][2]} />
      );
    }
    return (
      <div className="projects-grid">
        {shown.map((project) => (
          <ProjectCard key={project.id} project={project} onOpen={handleOpen} onUpdate={handleUpdate} busy={deleting || updating.has(project.id)} />
        ))}
        {view.id !== "trash" && <button type="button" className="project-card-new" onClick={handleNewProject}>
          <span className="project-card-new-plus" aria-hidden="true">+</span>
          <span className="project-card-new-title">New Project</span>
          <span className="project-card-new-text">Upload a video to get started</span>
        </button>}
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
              {view.id === "trash" && <Button size="sm" disabled={loading || deleting || updating.size > 0 || trashedProjects.length === 0}
                onClick={() => setEmptyTrashOpen(true)}>Empty trash</Button>}
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

      {emptyTrashOpen && (
        <Modal title="Empty trash?" onClose={() => !deleting && setEmptyTrashOpen(false)}>
          <p className="projects-delete-text">
            Permanently delete all <strong>{trashedProjects.length}</strong> trashed projects and their sessions and clips? This cannot be undone.
          </p>
          <div className="projects-delete-actions">
            <Button variant="ghost" size="sm" onClick={() => setEmptyTrashOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={confirmEmptyTrash} disabled={deleting}>
              {deleting ? <Spinner size={14} label="Deleting" /> : "Empty trash permanently"}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default ProjectsPage;
