import { Link } from "react-router-dom";
import "./ExportPage.css";
import exportBg from "../assets/export page-bg.png";

function ExportPage() {
  return (
    <div className="export">
      <div className="export-stage" style={{ backgroundImage: `url(${exportBg})` }}>
        {/* Later: 4 project windows with select boxes */}
      </div>

      <Link to="/projects" className="page-button export-back">Back to Projects</Link>
    </div>
  );
}

export default ExportPage;