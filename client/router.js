function readonlySet(values) {
  const set = new Set(values);
  const rejectMutation = () => {
    throw new TypeError("readonly_route_allowlist");
  };
  Object.defineProperties(set, {
    add: { value: rejectMutation },
    delete: { value: rejectMutation },
    clear: { value: rejectMutation }
  });
  return Object.freeze(set);
}

export const VIEWS = readonlySet([
  "home",
  "projects",
  "topics",
  "graph",
  "changelog",
  "search"
]);

export const PROJECT_TABS = readonlySet([
  "decisions",
  "system-map",
  "build-timeline",
  "evidence"
]);

const LEGACY_TABS = Object.freeze({
  overview: "decisions",
  "build-story": "build-timeline",
  rollbacks: "evidence",
  "visual-map": "system-map",
  artifacts: "evidence"
});

export function normalizeTab(value) {
  if (PROJECT_TABS.has(value)) return value;
  return LEGACY_TABS[value] || "decisions";
}

export function parseRoute(input) {
  const url = input instanceof URL ? input : new URL(String(input), globalThis.location?.origin || "http://localhost");
  const parts = url.pathname.split("/").filter(Boolean);

  if (parts[0] === "projects" && parts[1]) {
    try {
      return {
        view: "project",
        projectId: decodeURIComponent(parts[1]),
        tab: normalizeTab(url.searchParams.get("tab"))
      };
    } catch {
      return { view: "home" };
    }
  }

  const view = parts[0] || "home";
  return { view: VIEWS.has(view) ? view : "home" };
}

export function toRouteHref(route = {}) {
  if (route.view === "project") {
    const projectId = String(route.projectId || "");
    if (!projectId) return "/projects";
    const tab = normalizeTab(route.tab);
    const query = tab === "decisions" ? "" : `?tab=${encodeURIComponent(tab)}`;
    return `/projects/${encodeURIComponent(projectId)}${query}`;
  }

  if (route.view === "home") return "/";
  return VIEWS.has(route.view) ? `/${route.view}` : "/";
}
