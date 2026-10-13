import { Link } from "react-router-dom";
import "./EditorPage.css";

function EditorPage() {
    return (
        <div className="editor">
            <h1>EDITOR</h1>
            <p>Timeline, effects, captions will go here.</p>
            <Link to="/export" className="page-button">
                Export
            </Link>
        </div>
    );
}

export default EditorPage;