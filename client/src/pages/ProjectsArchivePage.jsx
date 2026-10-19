import { useState } from "react";
import { Link } from "react-router-dom";
import "./ProjectsArchivePage.css";

// Fake projects for now; real ones (with real thumbnails) will come from the backend
const projects = [
  { id: 1, name: "My first video", editedHoursAgo: 2, thumbnail: null, favorite: true, archived: false, trashed: false },
  { id: 2, name: "Test", editedHoursAgo: 5, thumbnail: null, favorite: false, archived: false, trashed: false },
  { id: 3, name: "Yooooo", editedHoursAgo: 26, thumbnail: null, favorite: false, archived: true, trashed: false },
  { id: 4, name: "Old draft", editedHoursAgo: 90, thumbnail: null, favorite: false, archived: false, trashed: true },
];

const icons = {
  all: "M6 2h8l4 4v16H6zM14 2v4h4",
  recent: "M12 7v5l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
  favorites: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
  archives: "M3 4h18v4H3zM5 8v12h14V8M10 12h4",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
};

const sections = [
  { key: "all", label: "All projects", match: (p) => !p.trashed && !p.archived },
  { key: "recent", label: "Recent", match: (p) => !p.trashed && !p.archived && p.editedHoursAgo < 24 },
  { key: "favorites", label: "Favorites", match: (p) => !p.trashed && p.favorite },
  { key: "archives", label: "Archives", match: (p) => !p.trashed && p.archived },
  { key: "trash", label: "Trash", match: (p) => p.trashed },
];

function Icon({ path }) {
  return (
    <svg className="pa-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

function editedLabel(hours) {
  if (hours < 24) return `Edited ${hours} hours ago`;
  return `Edited ${Math.floor(hours / 24)} days ago`;
}

function ProjectsArchivePage() {
  const [section, setSection] = useState("all");
  const [query, setQuery] = useState("");

  const current = sections.find((s) => s.key === section);
  const visible = projects.filter(
    (p) => current.match(p) && p.name.toLowerCase().includes(query.trim().toLowerCase())
  );

  return (
    <div className="pa">
      <header className="pa-topbar">
        <Link to="/" className="pa-brand">
          <svg className="pa-leaf" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
            <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
          </svg>
          <span>Cascade</span>
        </Link>
        <div className="pa-avatar" role="img" aria-label="Your account" />
      </header>

      <div className="pa-body">
        <nav className="pa-sidebar" aria-label="Project filters">
          {sections.map((s) => (
            <button
              key={s.key}
              type="button"
              className={`pa-side-btn${s.key === section ? " is-active" : ""}`}
              onClick={() => setSection(s.key)}
            >
              <Icon path={icons[s.key]} />
              {s.label}
            </button>
          ))}
        </nav>

        <main className="pa-main">
          <div className="pa-head">
            <div>
              <h1>Your Projects</h1>
              <p>Create, edit, and manage your videos</p>
            </div>
            <div className="pa-actions">
              <label className="pa-search">
                <svg className="pa-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <circle cx="11" cy="11" r="6" />
                  <path d="M16 16l4 4" />
                </svg>
                <input
                  type="search"
                  placeholder="Search projects..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <Link to="/projects/new" className="pa-new">+ New Project</Link>
            </div>
          </div>

          <div className="pa-grid">
            {visible.map((project) => (
              <Link key={project.id} to="/editor" className="pa-card">
                <div className="pa-thumb">
                  {project.thumbnail && <img src={project.thumbnail} alt="" />}
                </div>
                <h2>{project.name}</h2>
                <span className="pa-edited">{editedLabel(project.editedHoursAgo)}</span>
              </Link>
            ))}
            {visible.length === 0 && <p className="pa-empty">No projects here yet.</p>}
          </div>
        </main>
      </div>
    </div>
  );
}

export default ProjectsArchivePage;
