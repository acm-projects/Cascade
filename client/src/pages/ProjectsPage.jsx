import { Link } from "react-router-dom";
import "./ProjectsPage.css";

const projects = [
    { id: 1, name: "My first video" },
    { id: 2, name: "Test" },
];

function ProjectsPage() {
    return (
        <div className="projects">
            <h1>PROJECTS</h1>

            <ul>
                {projects.map((project) => (
                    <li key={project.id}>{project.name}</li>
                ))}
            </ul>

            <Link to="/projects/new" className="page-button">New Project</Link>
        </div>
    );
}

export default ProjectsPage;