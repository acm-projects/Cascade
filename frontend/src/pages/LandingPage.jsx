import { Link } from "react-router-dom";
import "./LandingPage.css";
import Icon from "../components/ui/Icon";
import IsoWorld from "../features/landing3d/IsoWorld";
import { useLeafNavigate } from "../context/leafTransitionValue";

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
      </main>
    </div>
  );
}

export default LandingPage;
