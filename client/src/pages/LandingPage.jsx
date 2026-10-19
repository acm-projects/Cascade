import { Link } from "react-router-dom";
import "./LandingPage.css";
import background from "../assets/finalwleavestop1.jpg";

function LeafIcon() {
  return (
    <svg className="lp-leaf" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
      <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg className="lp-arrow" viewBox="0 0 60 12" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 6h56M52 1l5 5-5 5" />
    </svg>
  );
}

function LandingPage() {
  return (
    <div className="lp" style={{ backgroundImage: `url(${background})` }}>
      <header className="lp-nav">
        <Link to="/" className="lp-pill lp-brand">
          <LeafIcon />
          <span>Cascade</span>
        </Link>

        <nav className="lp-auth">
          {/* No login/signup pages yet, so both go to /projects for now */}
          <Link to="/projects" className="lp-pill lp-auth-btn">Log in</Link>
          <Link to="/projects" className="lp-pill lp-auth-btn">Sign up</Link>
        </nav>
      </header>

      <Link to="/projects" className="lp-pill lp-start">
        <span>Get Started</span>
        <ArrowIcon />
      </Link>
    </div>
  );
}

export default LandingPage;
