import { Link } from "react-router-dom";
import "./LandingPage.css";
// The picture is split into layers so parts can move: the scene with the front leaves painted out, plus each corner's leaves.
// (Made from assets/figma/landing-bg-straight.jpg, which is kept as the full original.)
import background from "../assets/landing/landing-plate.webp";
import leavesTopLeft from "../assets/landing/leaves-tl.webp";
import leavesTopRight from "../assets/landing/leaves-tr.webp";
import leavesBottomLeft from "../assets/landing/leaves-bl.webp";
import leavesBottomRight from "../assets/landing/leaves-br.webp";

const leafLayers = [
  { corner: "tl", src: leavesTopLeft },
  { corner: "tr", src: leavesTopRight },
  { corner: "bl", src: leavesBottomLeft },
  { corner: "br", src: leavesBottomRight },
];

// What Cascade does, as 3 small icons under the button. Icons are simple line drawings (stroke = currentColor).
const features = [
  { label: "Find key moments", icon: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5M11 8v6M8 11h6" /></> },
  { label: "Auto edit & caption", icon: <><circle cx="6" cy="7" r="3" /><circle cx="6" cy="17" r="3" /><path d="M8.5 8.5 20 18M8.5 15.5 20 6" /></> },
  { label: "Export everywhere", icon: <><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" /><path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" /></> },
];

// Landing: the words and button on the left, over the lake picture with its swaying leaves
function LandingPage() {
  return (
    <div className="landing">
      <div className="landing-scene" style={{ backgroundImage: `url(${background})` }} aria-hidden="true">
        {leafLayers.map((layer) => (
          <img key={layer.corner} className={`landing-leaves landing-leaves-${layer.corner}`} src={layer.src} alt="" />
        ))}
      </div>
      <main className="landing-copy">
        <h1 className="landing-title">CASCADE</h1>
        <p className="landing-headline">Turn one video into a week of content.</p>
        <p className="landing-sub">AI finds the best moments, edits them for you, and writes captions, all in one place.</p>
        <Link to="/projects" className="btn btn-large landing-start">Get Started →</Link>
        <ul className="landing-features">
          {features.map((feature) => (
            <li key={feature.label}>
              <span className="landing-feature-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
