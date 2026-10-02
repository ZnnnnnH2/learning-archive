import type { Project } from "./types";

export const DEFAULT_EXPANDED_PROJECT_LIMIT = 6;

export function applyDefaultProjectExpansion(
  projects: Record<string, Project>,
  projectOrder: readonly string[],
  expandedLimit = DEFAULT_EXPANDED_PROJECT_LIMIT
): Record<string, Project> {
  const expandedProjectIds = new Set(projectOrder.slice(0, expandedLimit));
  let changed = false;
  const nextProjects: Record<string, Project> = {};

  for (const [id, project] of Object.entries(projects)) {
    const expanded = expandedProjectIds.has(id);
    nextProjects[id] = { ...project, expanded };
    if (project.expanded !== expanded) {
      changed = true;
    }
  }

  return changed ? nextProjects : projects;
}
