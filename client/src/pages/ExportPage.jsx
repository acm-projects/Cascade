import { Link } from "react-router-dom";
import "./ExportPage.css";

function ExportPage() {
    return (
        <div className="export">
            <h1>EXPORT</h1>
            <p>Dowload or publish to Youtube / Instagram
            </p>

            <Link to ="/projects" className="page-button">Back to Projects</Link>

        </div>
    );
}

export default ExportPage;