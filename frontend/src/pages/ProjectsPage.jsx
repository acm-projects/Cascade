import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./ProjectsPage.css";
import bg from "../assets/figma/projects-bg.jpg";
import woodPill from "../assets/figma/wood-pill.png";
import woodCard from "../assets/figma/wood-card.png";
import woodGreen from "../assets/figma/wood-green-btn.png";
import avatar from "../assets/figma/avatar.png";
import leafCream from "../assets/icons/leaf-cream.svg";
import searchIcon from "../assets/icons/search.svg";
import fakeProjects from "../data/fakeProjects";
import { useProject } from "../context/ProjectContext";

// Sidebar filters: each one decides which projects to show
const filters = [
  { id: "all", label: "All Projects", test: (p) => !p.trashed && !p.archived },
  { id: "recent", label: "Recents", test: (p) => !p.trashed && /hour|day/.test(p.edited) },
  { id: "favorites", label: "Favorites", test: (p) => !p.trashed && p.favorite },
  { id: "archives", label: "Archives", test: (p) => !p.trashed && p.archived },
  { id: "trash", label: "Trash", test: (p) => p.trashed },
];

// Built from the Figma "Projects/Archive Page" (section 2, node 640:529)
function ProjectsPage() {
  const navigate = useNavigate();
  const { startNewProject, openProject } = useProject();
  const [filterId, setFilterId] = useState("all");
  const [search, setSearch] = useState("");

  const filter = filters.find((f) => f.id === filterId);
  const shown = fakeProjects.filter(
    (p) => filter.test(p) && p.name.toLowerCase().includes(search.toLowerCase())
  );

  // New project -> AI Studio
  function handleNewProject() {
    startNewProject();
    navigate("/studio");
  }

  // Existing project -> straight to its editor
  function handleOpen(project) {
    openProject(project);
    navigate("/editor");
  }

  return (
    <div className="projects" style={{ backgroundImage: `url(${bg})` }}>
      {/* Green top bar */}
      <header className="projects-bar">
        <div className="projects-brand">
          <img src={leafCream} alt="" className="projects-leaf" />
          <span>Cascade</span>
        </div>
        <img src={avatar} alt="Your account" className="projects-avatar" />
      </header>

      <div className="projects-body">
        {/* Left sidebar: wooden filter buttons */}
        <nav className="projects-sidebar">
          {filters.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`projects-filter${f.id === filterId ? " active" : ""}`}
              style={{ backgroundImage: `url(${woodPill})` }}
              onClick={() => setFilterId(f.id)}
            >
              {f.label}
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

          {/* Grid of wooden project cards */}
          <div className="projects-grid">
            {shown.map((project) => (
              <button
                key={project.id}
                type="button"
                className="projects-card"
                style={{ backgroundImage: `url(${woodCard})` }}
                onClick={() => handleOpen(project)}
              >
                <div className="projects-thumb">▶</div>
                <span className="projects-card-name">{project.name}</span>
                <span className="projects-card-meta">
                  Edited {project.edited} · {project.clips.length} clips
                </span>
              </button>
            ))}
            {shown.length === 0 && <p className="projects-empty">No projects here yet.</p>}
          </div>
        </main>
      </div>
    </div>
  );
}

export default ProjectsPage;
