import { Link, NavLink, useParams } from "react-router-dom";
import UserAvatar from "./UserAvatar";
import "./TopNav.css";
import leafIcon from "../assets/icons/leaf.svg";

const steps = [
  { id: "studio", number: 1, label: "AI Studio" },
  { id: "editor", number: 2, label: "Editor" },
  { id: "export", number: 3, label: "Export" },
];

// The wooden bar across the top of AI Studio, Editor and Export (Figma Page 7, 1728 x 119).
//   projectTitle   - shown next to the logo
//   projectId      - used to build the step links (defaults to the one in the URL)
//   active         - "studio" | "editor" | "export": the step that's filled in
//   canOpenEditor  - false = the Editor step is locked (Figma: "Not clickable until clips are selected")
//   canOpenExport  - same for Export
function TopNav({ projectTitle, projectId, active, canOpenEditor = false, canOpenExport = false }) {
  const params = useParams();
  const id = projectId ?? params.projectId;
  const unlocked = { studio: true, editor: canOpenEditor, export: canOpenExport };

  return (
    <header className="topnav">
      <Link to="/projects" className="topnav-brand" title="Back to your projects">
        <img src={leafIcon} alt="" className="topnav-leaf" />
        <span className="topnav-name">Cascade</span>
      </Link>

      <span className="topnav-divider" />
      <span className="topnav-title" title={projectTitle}>{projectTitle ?? "Untitled project"}</span>

      <nav className="topnav-steps" aria-label="Project steps">
        {steps.map((step) => {
          const className = `topnav-step${step.id === active ? " active" : ""}`;
          const content = (
            <>
              <span className="topnav-step-number">{step.number}</span>
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
            <NavLink key={step.id} to={`/projects/${id}/${step.id}`} className={className}>
              {content}
            </NavLink>
          );
        })}
      </nav>

      {/* Only while running `npm run dev`: shows the ids read from the URL, so you can see routing work */}
      {import.meta.env.DEV && (
        <span className="topnav-route" title="From the URL (useParams)">
          project: {id}
          {params.sessionId && <> · session: {params.sessionId}</>}
        </span>
      )}

      <UserAvatar className="topnav-avatar" />
    </header>
  );
}

export default TopNav;
