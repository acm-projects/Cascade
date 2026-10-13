import { Link } from "react-router-dom";
import "./ProjectsPage.css";
import projectsBg from "../assets/projects-page-bg.png";
import plank from "../assets/plank.png";
import vines from "../assets/Vines.png";

// Fake projects for now; real ones (with real thumbnails) will come from the backend
const projects = [
  { id: 1, name: "My first video", thumbnail: null },
  { id: 2, name: "Test", thumbnail: null },
  { id: 3, name: "Yooooo", thumbnail: null },
];

function ProjectsPage() {
  return (
    <div className="projects" style={{ backgroundImage: `url(${projectsBg})` }}>
      <img src={vines} alt="" className="vines" />
      <h1>PROJECTS</h1>

      <Link to="/projects/new" className="page-button">New Project</Link>

      <div className="plank-list">
        {projects.map((project) => (
          <Link
            key={project.id}
            to="/editor"
            className="plank"
            style={{ backgroundImage: `url(${plank})` }}
          >
            <div className="plank-content">
              <div className="plank-thumb">
                {project.thumbnail ? (
                  <img src={project.thumbnail} alt="" />
                ) : (
                  "No thumbnail"
                )}
              </div>
              <span className="plank-name">{project.name}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default ProjectsPage;