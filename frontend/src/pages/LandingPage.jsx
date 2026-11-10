import { Link } from "react-router-dom";
import "./LandingPage.css";
import Icon from "../components/ui/Icon";
import IsoWorld from "../features/landing3d/IsoWorld";
import { useLeafNavigate } from "../context/leafTransitionValue";

// What Cascade does, as 3 small blocks under the button
const features = [
  { label: "Find key moments", icon: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5M11 8v6M8 11h6" /></> },
  { label: "Auto edit & caption", icon: <><circle cx="6" cy="7" r="3" /><circle cx="6" cy="17" r="3" /><path d="M8.5 8.5 20 18M8.5 15.5 20 6" /></> },
  { label: "Export everywhere", icon: <><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" /><path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" /></> },
];

// Landing: the words and button on the left, the 3D rainforest island on the right
function LandingPage() {
  const leafNavigate = useLeafNavigate();

  // Get Started dives down into the sea, to the projects underwater.
  // (Cmd/Ctrl-click and middle-click still open it the normal way, e.g. in a new tab.)
  function diveToProjects(event) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    leafNavigate("/projects", { style: "dive", ready: import("../features/landing3d/underwaterScene") });
  }

  return (
    <div className="landing">
      <IsoWorld framing="hero" />
      <main className="landing-copy">
        <h1 className="landing-title">CASCADE</h1>
        <p className="landing-headline">Turn one video into a week of content.</p>
        <p className="landing-sub">AI finds the best moments, edits them for you, and writes captions, all in one place.</p>
        <Link to="/projects" className="landing-start" onClick={diveToProjects}>
          <span className="landing-start-top">Get Started <Icon name="arrowRight" /></span>
        </Link>
        <ul className="landing-features">
          {features.map((feature) => (
            <li key={feature.label}>
              <span className="landing-feature-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  {feature.icon}
                </svg>
              </span>
              {feature.label}
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}

export default LandingPage;
