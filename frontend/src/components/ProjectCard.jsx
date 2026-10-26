import { useEffect, useRef, useState } from "react";
import "./ProjectCard.css";
import woodCard from "../assets/figma/wood-card.png";
import leafIcon from "../assets/icons/leaf.svg";
import { timeAgo } from "../utils/time";

// One project in the Projects grid (Figma: 382 x 292 wooden card).
//   project  - from the backend: { id, name, created_at, updated_at?, thumbnail_url?, clip_count? }
//   onOpen   - called when you click the card or "Open"
//   onDelete - called when you pick "Delete" from the … menu
// The card holds two separate buttons (open + menu), because a button can't go inside another button.
function ProjectCard({ project, onOpen, onDelete }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  // Close the menu when you click anywhere else or press Esc
  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(event) {
      if (!menuRef.current?.contains(event.target)) setMenuOpen(false);
    }
    function handleKey(event) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [menuOpen]);

  const edited = project.updated_at ?? project.created_at;

  return (
    <div className="project-card" style={{ backgroundImage: `url(${woodCard})` }}>
      <button type="button" className="project-card-open" onClick={() => onOpen(project)}>
        <div className="project-card-thumb">
          {project.thumbnail_url ? (
            <img src={project.thumbnail_url} alt="" />
          ) : (
            <img src={leafIcon} alt="" className="project-card-leaf" />
          )}
        </div>
        <span className="project-card-name">{project.name}</span>
        <span className="project-card-meta">
          {edited ? `Edited ${timeAgo(edited)}` : "Never edited"}
          {project.clip_count != null && ` · ${project.clip_count} clip${project.clip_count === 1 ? "" : "s"}`}
        </span>
      </button>

      <div className="project-card-menu" ref={menuRef}>
        <button
          type="button"
          className="project-card-dots"
          aria-label={`More options for ${project.name}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          …
        </button>
        {menuOpen && (
          <div className="project-card-popup wood-panel" role="menu">
            <button type="button" role="menuitem" onClick={() => { setMenuOpen(false); onOpen(project); }}>
              Open
            </button>
            <button type="button" role="menuitem" className="danger"
              onClick={() => { setMenuOpen(false); onDelete(project); }}>
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ProjectCard;
