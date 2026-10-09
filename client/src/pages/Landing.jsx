import "./Landing.css";
import background from "../assets/landing-bg.png";
import blimp from "../assets/blimp.png";

function Landing() {
  return (
    <div className="landing" style={{ backgroundImage: `url(${background})` }}>
      <img src={blimp} alt="Blimp" className="blimp" />
    </div>
  );
}

export default Landing; 