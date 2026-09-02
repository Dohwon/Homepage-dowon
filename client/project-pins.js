const STORAGE_KEY = "project-atlas-pinned-projects";

function normalizeIds(value) {
  if (!Array.isArray(value)) return new Set();
  return new Set(value.filter((id) => typeof id === "string" && id.trim()).map((id) => id.trim()));
}

export function loadPinnedProjectIds(storage = globalThis.localStorage) {
  if (!storage || typeof storage.getItem !== "function") return new Set();
  try {
    return normalizeIds(JSON.parse(storage.getItem(STORAGE_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

export function savePinnedProjectIds(ids, storage = globalThis.localStorage) {
  const normalized = [...normalizeIds([...ids])].sort();
  if (storage && typeof storage.setItem === "function") {
    try { storage.setItem(STORAGE_KEY, JSON.stringify(normalized)); } catch {}
  }
  return new Set(normalized);
}

export function toggleProjectPinned(projectId, pinned, storage = globalThis.localStorage) {
  const ids = loadPinnedProjectIds(storage);
  if (pinned) ids.add(String(projectId));
  else ids.delete(String(projectId));
  return savePinnedProjectIds(ids, storage);
}

export function isProjectPinned(project, pinnedIds = loadPinnedProjectIds()) {
  return Boolean(project?.pinned) || Boolean(project?.id && pinnedIds.has(project.id));
}

export function sortPinnedProjects(projects, pinnedIds = loadPinnedProjectIds()) {
  return [...projects].sort((left, right) => {
    const pinnedDifference = Number(isProjectPinned(right, pinnedIds)) - Number(isProjectPinned(left, pinnedIds));
    return pinnedDifference || 0;
  });
}
