import "./Landing.css";
import { Link } from "react-router-dom";
import letterC from "../assets/letter_c1.png";
import letterA from "../assets/letter_a1.png";
import letterS from "../assets/letter_s.png";
import letterD from "../assets/letter_d.png";
import letterE from "../assets/letter_e.png";

// C A S C A D E, in order
const letters = [letterC, letterA, letterS, letterC, letterA, letterD, letterE];

function Landing() {
  return (
    <div className="landing">
      <div className="landing-title" role="img" aria-label="Cascade">
        {letters.map((src, index) => (
          <img
            key={index}
            src={src}
            alt=""
            className="landing-letter"
            style={{ animationDelay: index % 2 === 0 ? "0s" : "0.5s" }}
          />
        ))}
      </div>

      <Link to="/projects" className="wood-button landing-start">
        Get Started
      </Link>
    </div>
  );
}

export default Landing;
