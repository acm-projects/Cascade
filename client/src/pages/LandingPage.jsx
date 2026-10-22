import { Link } from "react-router-dom";
import "./LandingPage.css";
import leafIcon from "../assets/icons/leaf.svg";
import arrowIcon from "../assets/icons/arrow-right.svg";

// Built from the Figma "Landing Page" wireframe (Wireframe section, node 471:136)
function LandingPage() {
  return (
    <div className="landing-page">
      {/* Top bar: logo pill on the left, account buttons on the right */}
      <header className="landing-nav">
        <div className="landing-logo">
          <img src={leafIcon} alt="" className="landing-logo-icon" />
          <span className="landing-logo-name">Cascade</span>
        </div>

        <div className="landing-nav-buttons">
          {/* Log in / Sign up go to Projects until the team's login (Clerk) is hooked up */}
          <Link to="/projects" className="btn">Log in</Link>
          <Link to="/projects" className="btn">Sign up</Link>
        </div>
      </header>

      {/* Main area: Get Started sits in the lower left */}
      <main className="landing-hero">
        <Link to="/projects" className="btn btn-large landing-start">
          Get Started
          <img src={arrowIcon} alt="" className="landing-start-arrow" />
        </Link>
      </main>
    </div>
  );
}

export default LandingPage;
