import "./ProjectCard.css";

// Demo branch only: one of the earlier projects on the Projects page (utils/demoProjects.js). Nothing to click.
export default function DemoProjectCard({ project }) {
  return (
    <div className="project-card project-card-demo">
      <div className="project-card-open" aria-label={project.name}>
        <div className="project-card-thumb">
          <img src={project.thumb} alt="" />
        </div>
        <span className="project-card-name">{project.name}</span>
        <span className="project-card-meta">{project.meta}</span>
      </div>
    </div>
  );
}
