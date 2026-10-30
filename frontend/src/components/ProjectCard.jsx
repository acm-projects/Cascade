import { useEffect, useRef, useState } from "react";
import "./ProjectCard.css";
import woodCard from "../assets/figma/wood-card.png";
import leafIcon from "../assets/icons/leaf.svg";
import { isTrashed } from "../utils/projectViews";
import { timeAgo } from "../utils/time";

// One project in the Projects grid (Figma: 382 x 292 wooden card).
//   project  - from the backend: { id, name, created_at, updated_at?, thumbnail_url?, clip_count? }
//   onOpen   - called when you click the card or "Open"
//   onUpdate - persists favorite, archive and trash actions
// The card holds two separate buttons (open + menu), because a button can't go inside another button.
function ProjectCard({ project, onOpen, onUpdate, busy = false }) {
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

  const trashed = isTrashed(project);
  const update = (changes) => { setMenuOpen(false); onUpdate(project, changes); };
  const edited = project.updated_at ?? project.created_at;

  return (
    <div className="project-card" style={{ backgroundImage: `url(${woodCard})` }}>
      <button type="button" className="project-card-open" onClick={() => onOpen(project)} disabled={trashed || busy}>
        <div className="project-card-thumb">
          {project.thumbnail_url ? (
            <img src={project.thumbnail_url} alt="" />
          ) : (
            <img src={leafIcon} alt="" className="project-card-leaf" />
          )}
        </div>
        <span className="project-card-name">{project.favorite && <span className="project-card-star" aria-label="Favorite">★ </span>}{project.name}</span>
        <span className="project-card-meta">
          {trashed ? `Deleted ${timeAgo(project.trashed_at)}` : edited ? `Edited ${timeAgo(edited)}` : "Never edited"}
          {project.clip_count != null && ` · ${project.clip_count} clip${project.clip_count === 1 ? "" : "s"}`}
        </span>
      </button>

      <div className="project-card-menu" ref={menuRef}>
        <button
          type="button"
          className="project-card-dots"
          aria-label={`More options for ${project.name}`}
          disabled={busy}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          …
        </button>
        {menuOpen && (
          <div className="project-card-popup wood-panel" role="menu">
            {!trashed && <button type="button" role="menuitem" onClick={() => { setMenuOpen(false); onOpen(project); }}>
              Open
            </button>}
            <button type="button" role="menuitem" onClick={() => update({ favorite: !project.favorite })}>
              {project.favorite ? "Unfavorite" : "☆ Favorite"}
            </button>
            <button type="button" role="menuitem" onClick={() => update({ archived: !project.archived })}>
              {project.archived ? "Unarchive" : "Archive"}
            </button>
            <button type="button" role="menuitem" className={trashed ? "" : "danger"}
              onClick={() => update({ trashed: !trashed })}>
              {trashed ? "Restore" : "Move to trash"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ProjectCard;
