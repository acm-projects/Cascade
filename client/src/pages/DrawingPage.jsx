import "./DrawingPage.css";
import drawingBg from "../assets/drawing-page-pg.png";

function DrawingPage() {
  return (
    <div className="drawing-page" style={{ backgroundImage: `url(${drawingBg})` }}>
      {/* "How it works" sign, frog, etc. go here later */}
    </div>
  );
}

export default DrawingPage;
