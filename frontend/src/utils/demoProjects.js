// Demo branch only: three earlier projects shown on the Projects page for the presentation.
// They're pictures of past work (a thumbnail from each demo video), not real projects, so clicking does nothing.
export const DEMO_PROJECTS = [
  { id: "demo-teddy", name: "Teddy", thumb: "/demo-projects/teddy.jpg", meta: "Edited 2 days ago · 5 clips" },
  { id: "demo-lazy-girl", name: "Lazy Girl", thumb: "/demo-projects/lazy-girl.jpg", meta: "Edited 4 days ago · 4 clips" },
  { id: "demo-family-guy", name: "Family Guy", thumb: "/demo-projects/family-guy.jpg", meta: "Edited 1 week ago · 6 clips" },
];

export function demoProjectsFor(viewId, query) {
  if (viewId !== "all" && viewId !== "recents") return [];
  return DEMO_PROJECTS.filter((project) => project.name.toLowerCase().includes(query));
}
