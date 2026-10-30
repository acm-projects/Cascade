const WEEK_SECONDS = 7 * 24 * 60 * 60;

export function isTrashed(project) {
  return project.trashed_at != null;
}

export function projectMatchesView(project, view, now = Date.now() / 1000) {
  if (view === "trash") return isTrashed(project);
  if (isTrashed(project)) return false;
  if (view === "favorites") return Boolean(project.favorite);
  if (view === "archives") return Boolean(project.archived);
  if (project.archived) return false;
  return view !== "recent" || now - (project.updated_at ?? project.created_at) < WEEK_SECONDS;
}

// A failed delete must leave that project visible and must not stop the others.
export async function deleteTrashedProjects(projects, deleteProject) {
  const removed = new Set();
  const failures = [];
  for (const project of projects.filter(isTrashed)) {
    try {
      await deleteProject(project.id);
      removed.add(project.id);
    } catch (error) {
      failures.push(`${project.name}: ${error.message}`);
    }
  }
  return { removed, failures };
}
