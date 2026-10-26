import { Link } from "react-router-dom";
import "./LandingPage.css";
import background from "../assets/figma/landing-bg.jpg";

// Built from the Figma "Landing Page" (node 660:1760)
function LandingPage() {
  return (
    <div className="landing" style={{ backgroundImage: `url(${background})` }}>
      <h1 className="landing-title">CASCADE</h1>
      <Link to="/projects" className="btn btn-large landing-start">
        Get Started
      </Link>
    </div>
  );
}

export default LandingPage;
