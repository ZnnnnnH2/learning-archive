import type { Project, Shell } from "./types";

type ActivityTimestamp = number | null | undefined;

export function normalizeActivityTimestamp(
  updatedAt: ActivityTimestamp
): number | undefined {
  if (typeof updatedAt !== "number" || !Number.isFinite(updatedAt)) {
    return undefined;
  }
  return updatedAt >= 0 ? updatedAt : undefined;
}

export function getLocalActivityDay(
  updatedAt: ActivityTimestamp
): number | undefined {
  const timestamp = normalizeActivityTimestamp(updatedAt);
  if (timestamp === undefined) return undefined;

  const date = new Date(timestamp);
  const dayStart = new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate()
  ).getTime();
  return Number.isFinite(dayStart) ? dayStart : undefined;
}

export function sortIdsByActivityDay<T extends string>(
  ids: readonly T[],
  getUpdatedAt: (id: T) => ActivityTimestamp
): T[] {
  return ids
    .map((id, index) => ({
      id,
      index,
      day: getLocalActivityDay(getUpdatedAt(id)),
    }))
    .sort((a, b) => {
      if (a.day === b.day) return a.index - b.index;
      if (a.day === undefined) return 1;
      if (b.day === undefined) return -1;
      return b.day - a.day;
    })
    .map((entry) => entry.id);
}

export function getProjectActivityTimestamp(
  project: Pick<Project, "updatedAt" | "shellIds"> | undefined,
  shells: Record<string, Pick<Shell, "updatedAt"> | undefined>
): number | undefined {
  if (!project) return undefined;

  let latest = normalizeActivityTimestamp(project.updatedAt);
  for (const shellId of project.shellIds) {
    const shellUpdatedAt = normalizeActivityTimestamp(shells[shellId]?.updatedAt);
    if (
      shellUpdatedAt !== undefined &&
      (latest === undefined || shellUpdatedAt > latest)
    ) {
      latest = shellUpdatedAt;
    }
  }
  return latest;
}

export function sortShellIdsByActivityDay(
  shellIds: readonly string[],
  shells: Record<string, Pick<Shell, "updatedAt"> | undefined>
): string[] {
  return sortIdsByActivityDay(shellIds, (shellId) => shells[shellId]?.updatedAt);
}

export function sortProjectsByActivityDay(
  projectOrder: readonly string[],
  projects: Record<string, Pick<Project, "updatedAt" | "shellIds"> | undefined>,
  shells: Record<string, Pick<Shell, "updatedAt"> | undefined>
): string[] {
  return sortIdsByActivityDay(projectOrder, (projectId) =>
    getProjectActivityTimestamp(projects[projectId], shells)
  );
}
