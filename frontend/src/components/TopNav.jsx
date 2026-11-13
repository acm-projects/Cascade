import { Link, NavLink, useParams } from "react-router-dom";
import { useLeafNavigate } from "../context/leafTransitionValue";
import UserAvatar from "./UserAvatar";
import "./TopNav.css";
import logo from "../assets/icons/cascade-logo.svg";

const steps = [
  { id: "studio", label: "Studio Island" },
  { id: "editor", label: "Editor" },
  { id: "export", label: "Export" },
];


// /projects/<id>/studio|editor|export. While you're in an AI Studio session, the AI Studio link keeps it.
function stepPath(projectId, stepId, sessionId) {
  const path = `/projects/${projectId}/${stepId}`;
  return stepId === "studio" && sessionId ? `${path}/${sessionId}` : path;
}

// The green bar across the top of AI Studio, Editor and Export (Figma Page 7, 1728 x 119).
//   projectTitle   - shown next to the logo
//   projectId      - used to build the step links (defaults to the one in the URL)
//   active         - "studio" | "editor" | "export": the step that's filled in
//   canOpenEditor  - false = the Editor step is locked (Figma: "Not clickable until clips are selected")
//   canOpenExport  - same for Export
function TopNav({ projectTitle, projectId, active, canOpenEditor = false, canOpenExport = false }) {
  const params = useParams();
  const leafNavigate = useLeafNavigate();
  const id = projectId ?? params.projectId;
  const unlocked = { studio: true, editor: canOpenEditor, export: canOpenExport };

  return (
    <header className="topnav">
      <Link to="/projects" className="topnav-brand" title="Back to your projects">
        <img src={logo} alt="" className="topnav-leaf" />
        <span className="topnav-name">Cascade</span>
      </Link>

      <span className="topnav-divider" />
      <span className="topnav-title" title={projectTitle}>{projectTitle ?? "Untitled project"}</span>

      <nav className="topnav-steps" aria-label="Project steps">
        {steps.map((step) => {
          const className = `topnav-step${step.id === active ? " active" : ""}`;
          const content = (
            <>
              {step.label}
            </>
          );

          // Locked: a button that does nothing. aria-disabled (not "disabled") keeps it reachable with Tab
          // and lets the tooltip show, but screen readers still announce it as unavailable.
          if (!unlocked[step.id]) {
            return (
              <button key={step.id} type="button" className={`${className} locked`}
                aria-disabled="true" title="Select at least one clip first">
                {content}
              </button>
            );
          }

          return (
            <NavLink key={step.id} to={stepPath(id, step.id, params.sessionId)} className={className}
              onClick={(event) => {
                if (step.id === active || !leafNavigate) return;
                event.preventDefault();   // a waterfall covers the change while the next step loads
                leafNavigate(stepPath(id, step.id, params.sessionId), { style: "falls" });
              }}>
              {content}
            </NavLink>
          );
        })}
      </nav>

      <UserAvatar className="topnav-avatar" />
    </header>
  );
}

export default TopNav;
