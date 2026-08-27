import { createAtlasApi } from "./api.js";
import { createStore } from "./state.js";
import { parseRoute, toRouteHref } from "./router.js";
import { renderError, renderRoute } from "./render.js";
import { bindSearchDialog } from "./search-dialog.js";
import { bindTheme } from "./theme.js";
import { bindReadingProgress } from "./progress.js";

const api = createAtlasApi();
const root = document.querySelector("#atlas-main");
const store = createStore({ route: parseRoute(new URL(window.location.href)) });
let navigationId = 0;

function normalizeDestination(destination) {
  if (destination instanceof URL) return destination;
  if (typeof destination === "string") return new URL(destination, window.location.origin);
  return new URL(toRouteHref(destination), window.location.origin);
}

async function navigate(destination, { replace = false, focus = true } = {}) {
  const url = normalizeDestination(destination);
  const route = parseRoute(url);
  const currentId = ++navigationId;
  if (replace) history.replaceState({}, "", `${url.pathname}${url.search}`);
  else if (`${location.pathname}${location.search}` !== `${url.pathname}${url.search}`) history.pushState({}, "", `${url.pathname}${url.search}`);

  const patch = { route, loading: true, error: null };
  if (route.view !== "project") patch.project = null;
  store.setState(patch);

  try {
    if (!store.getState().bootstrap) patch.bootstrap = await api.bootstrap();
    if (route.view === "project") patch.project = await api.project(route.projectId);
    if (route.view === "graph" && !store.getState().graph) patch.graph = await api.graph();
    if (currentId !== navigationId) return;
    store.setState({ ...patch, loading: false });
    renderRoute(store.getState(), root, { navigate });
    if (focus) {
      window.scrollTo({ top: 0, behavior: "instant" });
      root.focus({ preventScroll: true });
    }
  } catch (error) {
    if (currentId !== navigationId) return;
    store.setState({ loading: false, error });
    renderError(root, error);
  }
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-route-link]");
  if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const url = new URL(link.href, location.origin);
  if (url.origin !== location.origin) return;
  event.preventDefault();
  navigate(url);
});

window.addEventListener("popstate", () => navigate(new URL(window.location.href), { replace: true }));
bindTheme(document.querySelector("[data-theme-toggle]"));
bindReadingProgress(document.querySelector("#reading-progress"));
bindSearchDialog(document.querySelector("#search-dialog"), api);
window.lucide?.createIcons();
navigate(new URL(window.location.href), { replace: true, focus: false });
