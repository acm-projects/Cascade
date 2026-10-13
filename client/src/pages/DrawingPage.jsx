import "./DrawingPage.css";
import { Link } from "react-router-dom";
import drawingBg from "../assets/drawing-page-pg.png";

function DrawingPage() {
  return (
    <div className="drawing-page" style={{ backgroundImage: `url(${drawingBg})` }}>
      <h1>NEW PROJECT</h1>
      <p>Drop a clip, write a prompt, pick from 4 generated clips (coming soon).</p>

      <Link to="/editor" className="wood-button">Continue to Editor</Link>
    </div>
  );
}

export default DrawingPage;

