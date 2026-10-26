import { Link } from "react-router-dom";
import "./TopBar.css";
import leafIcon from "../assets/icons/leaf.svg";
import avatar from "../assets/figma/avatar.png";

const steps = [
  { id: "studio", number: 1, label: "AI Studio", path: "/studio" },
  { id: "editor", number: 2, label: "Editor", path: "/editor" },
  { id: "export", number: 3, label: "Export", path: "/export" },
];

// The gray bar across the top of AI Studio, Editor, and Export (Figma: 1728 x 119).
//   title         - the project's name, next to the logo
//   activeStep    - "studio", "editor", or "export": which tab is highlighted
//   stepsUnlocked - false = Editor and Export can't be clicked yet (no clips picked)
function TopBar({ title = "Untitled project", activeStep, stepsUnlocked = false }) {
  return (
    <header className="topbar">
      <Link to="/projects" className="topbar-brand" title="Back to your projects">
        <img src={leafIcon} alt="" className="topbar-leaf" />
        <span className="topbar-name">Cascade</span>
      </Link>

      <span className="topbar-divider" />
      <span className="topbar-title">{title}</span>

      <nav className="topbar-steps">
        {steps.map((step) => {
          const isActive = step.id === activeStep;
          const isLocked = step.id !== "studio" && !stepsUnlocked;
          const className = `topbar-step${isActive ? " active" : ""}${isLocked ? " locked" : ""}`;
          const content = (
            <>
              <span className="topbar-step-number">{step.number}</span>
              {step.label}
            </>
          );

          // A locked step is plain text, so it can't be clicked
          return isLocked ? (
            <span key={step.id} className={className} title="Pick clips in AI Studio first">
              {content}
            </span>
          ) : (
            <Link key={step.id} to={step.path} className={className}>
              {content}
            </Link>
          );
        })}
      </nav>

      <img src={avatar} alt="Your account" className="topbar-avatar" />
    </header>
  );
}

export default TopBar;
