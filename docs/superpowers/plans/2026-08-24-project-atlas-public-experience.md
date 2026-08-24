# Project Atlas Public Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stale portfolio front page with a responsive Project Atlas explorer that serves sanitized bundle content through tabs, search, topics, and the reused interactive knowledge graph while preserving the existing admin CMS as an override surface.

**Architecture:** The Node server loads only `public-bundle/` for generated project knowledge and merges a strict allowlist of existing CMS overrides. A new modular browser client renders Home, Projects, Topics, Graph, Changelog, and Search views; project routes render Overview, Build Story, Decisions, Rollbacks, Visual Map, and Artifacts tabs without exposing session or provenance data.

**Tech Stack:** Node.js 22+, CommonJS server, browser ES modules, HTML/CSS, SVG, Lucide, Marked, DOMPurify, Node test runner, Playwright

**Spec:** `docs/superpowers/specs/2026-08-24-project-atlas-design.md`

**Prerequisite:** Complete `docs/superpowers/plans/2026-08-24-project-atlas-local-pipeline.md` and pass its completion gate before Task 1.

## Global Constraints

- The first screen is the working project explorer, not a marketing landing page.
- Primary navigation is Home, Projects, Topics, Graph, Changelog, and Search.
- Project tabs are Overview, Build Story, Decisions, Rollbacks, Visual Map, and Artifacts.
- There is no public Sessions tab, raw transcript route, or provenance payload.
- Existing CMS data can override only allowlisted public presentation fields.
- Manual override wins over curated project memory, which wins over verified inference.
- Existing graph filtering, focus, zoom, drag/pan, and fit-to-view behavior is reused where useful.
- Each project shows at most five similarity neighbors.
- Use Inter and JetBrains Mono with `letter-spacing: 0`; no negative letter spacing is allowed.
- Icon and compact action targets are 40-44 px and use Lucide where a matching icon exists.
- Light/dark theme is applied before first paint.
- `Cmd/Ctrl+K` opens search.
- Desktop and mobile layouts must not overlap, clip long words, or shift when controls change state.

---

## Planned File Structure

```text
portfolio-homepage/
├── lib/
│   ├── atlas-store.js              # bundle loading, caching, CMS merge
│   ├── public-content-policy.js     # runtime CMS override privacy checks
│   └── atlas-routes.js             # public Atlas API routes
├── client/
│   ├── api.js                      # Atlas endpoint client
│   ├── state.js                    # normalized client state
│   ├── router.js                   # URL and project-tab routing
│   ├── render.js                   # page and project rendering
│   ├── markdown.js                 # Marked + DOMPurify boundary
│   ├── graph-view.js               # reused SVG graph interaction
│   ├── search-dialog.js            # Cmd/Ctrl+K search UI
│   ├── theme.js                    # prepaint-compatible theme control
│   ├── progress.js                 # reading progress calculation
│   └── main.js                     # client composition root
├── vendor/                         # generated browser distributions
├── test/
│   ├── fixtures/public-bundle/     # synthetic public-only bundle
│   ├── server/atlas-store.test.js
│   ├── server/atlas-api.test.js
│   └── client/router.test.js
├── e2e/
│   ├── atlas-navigation.spec.js
│   ├── atlas-graph.spec.js
│   ├── atlas-responsive.spec.js
│   └── atlas-privacy.spec.js
├── scripts/vendor_client_assets.mjs
├── playwright.config.js
├── admin.html                      # preserved current CMS/public surface
├── admin.js
├── admin.css
├── index.html                      # new Atlas shell
├── app.js                          # small compatibility bootstrap
└── styles.css                      # new Atlas visual system
```

### Task 1: Atlas Bundle Store and CMS Merge Boundary

**Files:**
- Create: `lib/atlas-store.js`
- Create: `lib/public-content-policy.js`
- Create: `test/server/atlas-store.test.js`
- Create: `test/fixtures/public-bundle/manifest.json`
- Create: `test/fixtures/public-bundle/projects/alpha/project.json`
- Create: `test/fixtures/public-bundle/projects/alpha/build-story.md`
- Create: `test/fixtures/public-bundle/projects/beta/project.json`
- Create: `test/fixtures/public-bundle/graph/nodes.json`
- Create: `test/fixtures/public-bundle/graph/edges.json`
- Create: `test/fixtures/public-bundle/topics.json`
- Create: `test/fixtures/public-bundle/changelog.json`
- Create: `test/fixtures/public-bundle/search-index.json`
- Modify: `package.json`

**Interfaces:**
- Consumes: `bundleDir`, `loadCmsContent() -> Promise<object>`, and sanitized bundle files.
- Produces: `createAtlasStore({ bundleDir, loadCmsContent })`, with `bootstrap()`, `project(id)`, `graph()`, and `search(query)` async methods.
- Private functions: `readJson(path)`, `loadBundle(bundleDir, manifest)`, `mergeCms(bundle, cms)`, `projectList(bundle)`, `projectById(bundle, id)`, and `searchBundle(bundle, query)`; all return plain sanitized objects and stable ordering.

- [ ] **Step 1: Write failing store tests for bundle loading, override precedence, and hidden projects**

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { createAtlasStore } = require("../../lib/atlas-store");

test("manual public fields override generated values", async () => {
  const store = createAtlasStore({
    bundleDir: path.join(__dirname, "../fixtures/public-bundle"),
    loadCmsContent: async () => ({
      meta: { hiddenProjectIds: [] },
      projects: [{ id: "alpha", summary: "Curated CMS summary", path: "/home/dowon/private" }]
    })
  });
  const project = await store.project("alpha");
  assert.equal(project.summary, "Curated CMS summary");
  assert.equal(project.path, undefined);
});

test("hidden generated projects are omitted", async () => {
  const store = createAtlasStore({
    bundleDir: path.join(__dirname, "../fixtures/public-bundle"),
    loadCmsContent: async () => ({ meta: { hiddenProjectIds: ["alpha"] }, projects: [] })
  });
  assert.deepEqual((await store.bootstrap()).projects.map(project => project.id), ["beta"]);
});

test("unsafe CMS presentation fields cannot override a public project", async () => {
  const store = createAtlasStore({
    bundleDir: path.join(__dirname, "../fixtures/public-bundle"),
    loadCmsContent: async () => ({
      meta: { hiddenProjectIds: [] },
      projects: [{ id: "alpha", summary: "read /home/dowon/private" }]
    })
  });
  await assert.rejects(() => store.project("alpha"), /unsafe_public_content: absolute_path/);
});
```

- [ ] **Step 2: Add the Node test script and verify failure**

Add to `package.json`:

```json
{
  "scripts": {
    "test": "node --test",
    "test:ui": "playwright test"
  }
}
```

Run: `npm test`

Expected: FAIL with `Cannot find module '../../lib/atlas-store'`.

- [ ] **Step 3: Implement strict allowlisted merging and manifest-aware caching**

```javascript
const PUBLIC_OVERRIDE_FIELDS = new Set([
  "name", "summary", "highlights", "links", "manualOrder", "pinned", "preview"
]);

function applyCmsOverride(project, override = {}) {
  const merged = structuredClone(project);
  for (const field of PUBLIC_OVERRIDE_FIELDS) {
    if (Object.hasOwn(override, field)) {
      assertSafePublicValue(override[field]);
      merged[field] = structuredClone(override[field]);
    }
  }
  return merged;
}

function createAtlasStore({ bundleDir, loadCmsContent }) {
  let cachedVersion = null;
  let cachedBundle = null;
  async function load() {
    const manifest = await readJson(path.join(bundleDir, "manifest.json"));
    if (cachedVersion !== manifest.version) {
      cachedBundle = await loadBundle(bundleDir, manifest);
      cachedVersion = manifest.version;
    }
    return mergeCms(cachedBundle, await loadCmsContent());
  }
  return { bootstrap: async () => projectList(await load()), project: async id => projectById(await load(), id), graph: async () => (await load()).graph, search: async query => searchBundle(await load(), query) };
}
```

Never merge `path`, `readme`, `provenance`, `session`, or arbitrary unknown fields from CMS content.

`lib/public-content-policy.js` recursively inspects override strings for absolute home paths, API/private-key patterns, private IPs, HTML comments, source-map references, and non-allowlisted contact identifiers. It throws only category names, never matching values. Reuse it from `sanitizeProjectInput` in `server.js` so unsafe presentation fields are rejected with HTTP `400 {"error":"unsafe_public_content","category":"absolute_path"}` before storage.

- [ ] **Step 4: Run store tests**

Run: `npm test`

Expected: store tests PASS.

- [ ] **Step 5: Commit the public data boundary**

```bash
git add lib/atlas-store.js lib/public-content-policy.js test/fixtures test/server/atlas-store.test.js package.json
git commit -m "feat: load sanitized atlas bundle"
```

### Task 2: Public Atlas API Routes

**Files:**
- Create: `lib/atlas-routes.js`
- Create: `test/server/helpers.js`
- Create: `test/server/atlas-api.test.js`
- Modify: `server.js`

**Interfaces:**
- Consumes: `AtlasStore` from Task 1 and existing `sendJson`/`notFound` behavior.
- Produces: `handleAtlasApi(req, res, url, store) -> Promise<boolean>` and routes `/api/atlas/bootstrap`, `/api/atlas/projects/:id`, `/api/atlas/graph`, `/api/atlas/search?q=`.

`test/server/helpers.js` exports `fixtureDir` and `startTestServer({ atlasBundleDir })`; the latter calls the exported `createApplicationServer` with port `0`, waits for `listening`, and returns `{ url, close }`.

Tests set `PORTFOLIO_DATA_DIR` to a temporary directory populated from `seed-data/`. `server.js` resolves `DATA_DIR` from `process.env.PORTFOLIO_DATA_DIR` when present and otherwise keeps the current `data/` default, so tests never seed-sync or write comments/analytics into production-local data.

- [ ] **Step 1: Write failing route tests with an ephemeral server**

```javascript
test("atlas API exposes project tabs but no sessions or provenance", async () => {
  const server = await startTestServer({ atlasBundleDir: fixtureDir });
  const response = await fetch(`${server.url}/api/atlas/projects/alpha`);
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.id, "alpha");
  assert.equal(payload.sessions, undefined);
  assert.equal(payload.provenance, undefined);
  await server.close();
});

test("unknown project returns 404", async () => {
  const server = await startTestServer({ atlasBundleDir: fixtureDir });
  assert.equal((await fetch(`${server.url}/api/atlas/projects/missing`)).status, 404);
  await server.close();
});
```

- [ ] **Step 2: Run the API tests and verify failure**

Run: `node --test test/server/atlas-api.test.js`

Expected: FAIL because Atlas routes and exported test server do not exist.

- [ ] **Step 3: Implement route dispatch and make server startup testable**

```javascript
async function handleAtlasApi(req, res, url, store) {
  if (req.method === "GET" && url.pathname === "/api/atlas/bootstrap") {
    sendJson(res, 200, await store.bootstrap());
    return true;
  }
  if (req.method === "GET" && url.pathname.startsWith("/api/atlas/projects/")) {
    const id = decodeURIComponent(url.pathname.slice("/api/atlas/projects/".length));
    const project = await store.project(id);
    if (!project) sendJson(res, 404, { error: "project_not_found" });
    else sendJson(res, 200, project);
    return true;
  }
  if (req.method === "GET" && url.pathname === "/api/atlas/graph") {
    sendJson(res, 200, await store.graph());
    return true;
  }
  if (req.method === "GET" && url.pathname === "/api/atlas/search") {
    sendJson(res, 200, { items: await store.search(url.searchParams.get("q") || "") });
    return true;
  }
  return false;
}
```

Add `createApplicationServer({ port, host, atlasBundleDir })` to `server.js`; call `main()` only under `if (require.main === module)`. Preserve every existing auth, comments, analytics, project CMS, and blog endpoint.

- [ ] **Step 4: Run server tests and health smoke**

Run: `npm test`

Run: `PORT=4181 ATLAS_BUNDLE_DIR=test/fixtures/public-bundle node server.js`

In a second terminal, run: `curl -sS http://127.0.0.1:4181/api/atlas/bootstrap`

Expected: tests PASS and bootstrap JSON reports manifest version `test-v1`.

- [ ] **Step 5: Commit the Atlas API**

```bash
git add lib/atlas-routes.js server.js test/server/atlas-api.test.js
git commit -m "feat: expose project atlas API"
```

### Task 3: Preserve the Existing CMS and Create the Atlas Shell

**Files:**
- Create by move: `admin.html` from `index.html`
- Create by move: `admin.js` from `app.js`
- Create by move: `admin.css` from `styles.css`
- Create: `index.html`
- Create: `app.js`
- Create: `styles.css`
- Create: `scripts/vendor_client_assets.mjs`
- Modify: `package.json`
- Modify: `server.js`

**Interfaces:**
- Consumes: existing CMS APIs and browser vendor bundles.
- Produces: `/admin.html` with preserved CMS behavior and `/` with stable semantic containers for the new Atlas client.

- [ ] **Step 1: Add a failing static-surface test**

```javascript
test("root serves Atlas shell and admin surface remains reachable", async () => {
  const server = await startTestServer({ atlasBundleDir: fixtureDir });
  const root = await (await fetch(`${server.url}/`)).text();
  const admin = await (await fetch(`${server.url}/admin.html`)).text();
  assert.match(root, /id="atlas-main"/);
  assert.match(root, /data-view="graph"/);
  assert.match(admin, /id="project-editor-form"/);
  await server.close();
});
```

- [ ] **Step 2: Run the test and verify the Atlas shell is absent**

Run: `node --test test/server/atlas-api.test.js`

Expected: FAIL because `/` still serves the old portfolio shell.

- [ ] **Step 3: Move the old surface and create the semantic Atlas document**

Use `git mv index.html admin.html`, `git mv app.js admin.js`, and `git mv styles.css admin.css`. Update `admin.html` to load `admin.css` and `admin.js`.

Create `index.html` with:

```html
<!doctype html>
<html lang="ko" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script>document.documentElement.dataset.theme = localStorage.getItem("atlas-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");</script>
  <title>Dowon Project Atlas</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div id="reading-progress" class="reading-progress" aria-hidden="true"></div>
  <header id="atlas-header"></header>
  <main id="atlas-main" tabindex="-1"></main>
  <nav id="mobile-nav" aria-label="모바일 탐색"></nav>
  <dialog id="search-dialog" aria-labelledby="search-title"></dialog>
  <script src="vendor/lucide.min.js"></script>
  <script src="vendor/marked.umd.js"></script>
  <script src="vendor/purify.min.js"></script>
  <script type="module" src="client/main.js"></script>
</body>
</html>
```

Create `app.js` as a compatibility redirect that dynamically imports `./client/main.js`. Add `.json` to static MIME/allowed extensions only for assets under `vendor/` if required; public bundle remains API-only.

- [ ] **Step 4: Vendor exact browser distributions and verify both surfaces**

Add dependencies and scripts:

```json
{
  "dependencies": {
    "dompurify": ">=3.1 <4",
    "lucide": ">=0.468 <1",
    "marked": ">=15 <18"
  },
  "devDependencies": {
    "@playwright/test": ">=1.50 <2",
    "pngjs": ">=7 <8"
  },
  "scripts": {
    "vendor": "node scripts/vendor_client_assets.mjs",
    "postinstall": "npm run vendor"
  }
}
```

The vendor script uses `fs.copyFile` with this exact map and fails when a source is absent:

```javascript
const vendorFiles = [
  ["node_modules/lucide/dist/umd/lucide.min.js", "vendor/lucide.min.js"],
  ["node_modules/marked/lib/marked.umd.js", "vendor/marked.umd.js"],
  ["node_modules/dompurify/dist/purify.min.js", "vendor/purify.min.js"]
];
```

Run: `npm install`

Run: `npm test`

Expected: the static-surface test PASSes and vendor files exist.

- [ ] **Step 5: Commit the split surfaces**

```bash
git add admin.html admin.js admin.css index.html app.js styles.css scripts/vendor_client_assets.mjs package.json package-lock.json vendor server.js test/server/atlas-api.test.js
git commit -m "feat: establish project atlas public shell"
```

### Task 4: Client State, Routing, and Project Tabs

**Files:**
- Create: `client/api.js`
- Create: `client/state.js`
- Create: `client/router.js`
- Create: `client/render.js`
- Create: `client/main.js`
- Create: `test/client/router.test.js`

**Interfaces:**
- Consumes: `/api/atlas/bootstrap` and `/api/atlas/projects/:id`.
- Produces: `parseRoute(url) -> Route`, `toRouteHref(route) -> string`, `createStore(initial)`, and `renderRoute(state, root)`.

- [ ] **Step 1: Write failing route and tab-normalization tests**

```javascript
test("project routes preserve valid tabs and reject sessions", () => {
  assert.deepEqual(parseRoute(new URL("https://atlas.test/projects/alpha?tab=decisions")), { view: "project", projectId: "alpha", tab: "decisions" });
  assert.deepEqual(parseRoute(new URL("https://atlas.test/projects/alpha?tab=sessions")), { view: "project", projectId: "alpha", tab: "overview" });
});

test("top-level graph route is stable", () => {
  assert.equal(toRouteHref({ view: "graph" }), "/graph");
});
```

- [ ] **Step 2: Run router tests and verify failure**

Run: `node --test test/client/router.test.js`

Expected: FAIL because `client/router.js` does not exist.

- [ ] **Step 3: Implement explicit route and tab allowlists**

```javascript
export const VIEWS = new Set(["home", "projects", "topics", "graph", "changelog", "search"]);
export const PROJECT_TABS = new Set(["overview", "build-story", "decisions", "rollbacks", "visual-map", "artifacts"]);

export function normalizeTab(value) {
  return PROJECT_TABS.has(value) ? value : "overview";
}

export function parseRoute(url) {
  const parts = url.pathname.split("/").filter(Boolean);
  if (parts[0] === "projects" && parts[1]) return { view: "project", projectId: decodeURIComponent(parts[1]), tab: normalizeTab(url.searchParams.get("tab")) };
  const view = parts[0] || "home";
  return { view: VIEWS.has(view) ? view : "home" };
}
```

`client/main.js` loads bootstrap once, binds click/popstate handlers, fetches a project only when its route opens, and focuses `#atlas-main` after navigation.

`client/render.js` builds a heading-derived table of contents for long Markdown, project previous/next links from bootstrap ordering, and all six project tabs. Missing optional sections render an empty-state sentence without creating a disabled tab or exposing source provenance.

- [ ] **Step 4: Run router tests and a browser smoke**

Run: `npm test`

Run the server and open `/projects/alpha?tab=decisions`; confirm the Decisions tab receives `aria-selected="true"` and the URL survives refresh.

Expected: unit tests PASS and refresh renders the same project tab.

- [ ] **Step 5: Commit state and routing**

```bash
git add client/api.js client/state.js client/router.js client/render.js client/main.js test/client/router.test.js
git commit -m "feat: add atlas navigation and project tabs"
```

### Task 5: Safe Markdown, Search, Theme, and Reading Progress

**Files:**
- Create: `client/markdown.js`
- Create: `client/search-dialog.js`
- Create: `client/theme.js`
- Create: `client/progress.js`
- Modify: `client/render.js`
- Modify: `client/main.js`
- Modify: `.gitignore`
- Create: `e2e/atlas-navigation.spec.js`

**Interfaces:**
- Consumes: sanitized Markdown strings and search endpoint results.
- Produces: `renderMarkdown(source) -> TrustedHTML|string`, `bindSearchDialog(dialog, api)`, `bindTheme(button)`, and `bindReadingProgress(element)`.

- [ ] **Step 1: Write a failing Playwright navigation and safety test**

```javascript
test("keyboard search, theme, progress, and sanitized markdown work", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("[data-project-card]")).toHaveCount(2);
  for (const view of ["projects", "topics", "graph", "changelog"]) {
    await page.locator(`[data-view="${view}"]`).first().click();
    await expect(page).toHaveURL(new RegExp(`/${view}$`));
  }
  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await expect(page.locator("#search-dialog")).toBeVisible();
  await page.locator("#atlas-search-input").fill("routing");
  await expect(page.locator("[data-search-result]")).toHaveCount(1);
  await page.locator("[data-theme-toggle]").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.goto("/projects/alpha?tab=build-story");
  await expect(page.locator("script[data-injected]")).toHaveCount(0);
  await expect(page.locator("[data-project-next]")).toBeVisible();
  await expect(page.locator("[data-project-toc]")).toContainText("Constraint");
});
```

- [ ] **Step 2: Add Playwright configuration and verify failure**

`playwright.config.js` starts `node server.js` with `ATLAS_BUNDLE_DIR=test/fixtures/public-bundle` and `PORTFOLIO_DATA_DIR=.atlas-test-data`, uses port `4182`, and tests Chromium at desktop and mobile projects. A setup hook recreates `.atlas-test-data` from `seed-data/`, and `.gitignore` excludes `.atlas-test-data/`.

Run: `npm run test:ui -- e2e/atlas-navigation.spec.js`

Expected: FAIL because search, theme control, and project rendering are not implemented.

- [ ] **Step 3: Implement sanitization and interaction modules**

```javascript
export function renderMarkdown(source) {
  const raw = window.marked.parse(String(source || ""), { gfm: true, breaks: false });
  return window.DOMPurify.sanitize(raw, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed"],
    FORBID_ATTR: ["style", "onerror", "onclick"]
  });
}
```

Search opens on `Cmd/Ctrl+K`, closes on Escape, traps focus while open, and renders result links. Theme writes `atlas-theme` to local storage and calls `lucide.createIcons()`. Reading progress computes `scrollTop / (scrollHeight - clientHeight)` and writes `transform: scaleX(ratio)` without changing layout.

- [ ] **Step 4: Run navigation tests in desktop and mobile projects**

Run: `npm run test:ui -- e2e/atlas-navigation.spec.js`

Expected: both Playwright projects PASS.

- [ ] **Step 5: Commit content interactions**

```bash
git add client/markdown.js client/search-dialog.js client/theme.js client/progress.js client/render.js client/main.js playwright.config.js e2e/atlas-navigation.spec.js .gitignore
git commit -m "feat: add safe atlas reading interactions"
```

### Task 6: Reuse and Bound the Knowledge Graph

**Files:**
- Create: `client/graph-view.js`
- Modify: `client/render.js`
- Create: `e2e/atlas-graph.spec.js`
- Reference only: `/home/dowon/securedir/git/codex/projects/scripts/generate_llm_wiki.py:4568`

**Interfaces:**
- Consumes: `{ nodes, edges }` from `/api/atlas/graph`.
- Produces: `createGraphView(svg, graph, options) -> { fit(), focus(id), destroy() }`.
- Private functions: `layoutNodes(nodes, width, height)`, `renderEdges(viewport, edges, nodes)`, `renderNodes(viewport, nodes, onSelect)`, `bindPanZoom(svg, viewport, state)`, `fitGraph(svg, viewport, state)`, `focusNode(id, svg, viewport, state)`, and `teardown(svg)`.

- [ ] **Step 1: Write failing graph interaction and nonblank-pixel tests**

```javascript
test("graph renders, filters, zooms, and fits", async ({ page }) => {
  await page.goto("/graph");
  const graph = page.locator("#knowledge-graph");
  await expect(graph.locator("[data-node-type=Project]")).toHaveCount(2);
  const before = await graph.locator("#graph-viewport").getAttribute("transform");
  await graph.hover();
  await page.mouse.wheel(0, -500);
  const zoomed = await graph.locator("#graph-viewport").getAttribute("transform");
  expect(zoomed).not.toBe(before);
  await page.locator("[data-graph-fit]").click();
  await expect(page.locator("[data-graph-status]")).toContainText("전체 보기");
  const png = PNG.sync.read(await graph.screenshot());
  const colors = new Set();
  for (let index = 0; index < png.data.length; index += 4) {
    colors.add(`${png.data[index]}:${png.data[index + 1]}:${png.data[index + 2]}:${png.data[index + 3]}`);
  }
  expect(colors.size).toBeGreaterThan(10);
});
```

Import `PNG` from `pngjs` at the top of the test. Also assert every visible Project node's bounding box is fully inside the SVG bounding box after fit-to-view.

- [ ] **Step 2: Run the graph test and verify failure**

Run: `npm run test:ui -- e2e/atlas-graph.spec.js`

Expected: FAIL because the graph view is absent.

- [ ] **Step 3: Port the useful graph viewport behavior into a focused module**

```javascript
export function createGraphView(svg, graph, { onSelect = () => {} } = {}) {
  const nodes = graph.nodes.map(node => ({ ...node }));
  const nodeIds = new Set(nodes.map(node => node.id));
  const edges = graph.edges.filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target));
  const viewport = document.createElementNS("http://www.w3.org/2000/svg", "g");
  viewport.id = "graph-viewport";
  svg.replaceChildren(viewport);
  const state = { scale: 1, x: 0, y: 0 };
  renderEdges(viewport, edges, nodes);
  renderNodes(viewport, nodes, onSelect);
  bindPanZoom(svg, viewport, state);
  return { fit: () => fitGraph(svg, viewport, state), focus: id => focusNode(id, svg, viewport, state), destroy: () => teardown(svg) };
}
```

Reuse the prior fit, pointer pan, wheel zoom, focus, and type-filter behavior, but consume the new typed graph data and render all validated edges rather than slicing an arbitrary global first 260. Use Lucide icons for fit/reset/filter controls and tooltips for unfamiliar controls.

- [ ] **Step 4: Run graph tests and visual pixel checks**

Run: `npm run test:ui -- e2e/atlas-graph.spec.js`

Expected: graph tests PASS on desktop and mobile; screenshots contain non-background pixels inside the graph bounds.

- [ ] **Step 5: Commit the graph view**

```bash
git add client/graph-view.js client/render.js e2e/atlas-graph.spec.js
git commit -m "feat: restore interactive atlas graph"
```

### Task 7: Responsive Visual System and Accessibility QA

**Files:**
- Modify: `styles.css`
- Modify: `index.html`
- Modify: `client/render.js`
- Create: `e2e/atlas-responsive.spec.js`
- Create: `e2e/atlas-privacy.spec.js`

**Interfaces:**
- Consumes: all rendered Atlas views.
- Produces: stable desktop/mobile layouts, visible focus states, skip navigation, responsive SVGs, and no public leakage.

- [ ] **Step 1: Write failing responsive, theme-flash, overlap, and privacy tests**

```javascript
for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`layout is bounded at ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => localStorage.setItem("atlas-theme", "dark"));
    await page.goto("/projects/alpha?tab=visual-map");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.locator("[role=tab]")).toHaveCSS("letter-spacing", "0px");
  });
}

test("public responses contain no local paths or session fields", async ({ request }) => {
  for (const path of ["/api/atlas/bootstrap", "/api/atlas/projects/alpha", "/api/atlas/graph"]) {
    const text = await (await request.get(path)).text();
    expect(text).not.toContain("/home/dowon");
    expect(text).not.toMatch(/sessions|provenance|\.jsonl/);
  }
});
```

- [ ] **Step 2: Run responsive and privacy tests to establish failures**

Run: `npm run test:ui -- e2e/atlas-responsive.spec.js e2e/atlas-privacy.spec.js`

Expected: FAIL on incomplete layout and accessibility rules.

- [ ] **Step 3: Implement restrained multi-color tokens and responsive constraints**

```css
:root {
  color-scheme: light;
  --bg: #f7f8fa;
  --surface: #ffffff;
  --text: #15171a;
  --muted: #626971;
  --line: #d8dde3;
  --accent: #176b5b;
  --signal: #b14e34;
  --focus: #2c61c9;
  --control-size: 42px;
  font-family: Inter, "IBM Plex Sans KR", sans-serif;
  letter-spacing: 0;
}
[data-theme="dark"] {
  color-scheme: dark;
  --bg: #101214;
  --surface: #181b1e;
  --text: #f2f4f5;
  --muted: #a9b0b7;
  --line: #343a40;
  --accent: #58b79f;
  --signal: #e18162;
  --focus: #78a5ff;
}
.icon-button { inline-size: var(--control-size); block-size: var(--control-size); }
.project-tabs { display: flex; min-width: 0; overflow-x: auto; }
.project-map { inline-size: 100%; aspect-ratio: 15 / 8; }
```

Add a skip link, `aria-current` navigation, `role="tablist"`, roving tab focus, visible `:focus-visible`, a mobile hamburger menu, a fixed mobile bottom nav, and `overflow-wrap: anywhere` only for unbreakable technical identifiers.

- [ ] **Step 4: Run full browser QA and capture screenshots**

Run: `npm run test:ui`

Expected: all desktop/mobile tests PASS; Playwright artifacts show no overlap, blank graph, theme flash, or clipped controls.

- [ ] **Step 5: Commit the completed public experience**

```bash
git add index.html styles.css client e2e
git commit -m "feat: complete responsive project atlas experience"
```

### Task 8: Public Experience Integration Gate

**Files:**
- Modify: `README.md`
- Modify: `deploy/DEPLOY.md`

**Interfaces:**
- Consumes: local worker output plus public server/client.
- Produces: documented local startup and a verified end-to-end service using a generated bundle.

- [ ] **Step 1: Generate a sanitized local bundle**

Run: `.venv/bin/python scripts/project_atlas.py run --workspace /home/dowon/securedir/git/codex`

Expected: `public-bundle/manifest.json` exists and the privacy gate reports zero findings.

- [ ] **Step 2: Run all unit and browser tests against the generated bundle**

Run: `.venv/bin/python -m pytest tests/worker -v`

Run: `npm test`

Run: `npm run test:ui`

Expected: every suite PASSes.

- [ ] **Step 3: Start the service and verify public routes**

Run: `PORT=4183 node server.js`

Run: `curl -sS http://127.0.0.1:4183/api/health`

Run: `curl -sS http://127.0.0.1:4183/api/atlas/bootstrap`

Expected: health returns `ok: true`; Atlas bootstrap returns the generated manifest version and no local paths.

- [ ] **Step 4: Document public and admin entry points**

Update docs with `/` for Project Atlas, `/admin.html` for the preserved CMS, worker commands, test commands, and `ATLAS_BUNDLE_DIR` behavior. Do not document any local secret value or HMAC key path as a public URL.

- [ ] **Step 5: Commit integration documentation**

```bash
git add README.md deploy/DEPLOY.md public-bundle
git commit -m "docs: document project atlas service"
```

## Plan Completion Gate

```bash
.venv/bin/python -m pytest tests/worker -v
npm test
npm run test:ui
node --check server.js
node --check admin.js
git status --short
```

Expected: worker, server, client, graph, privacy, desktop, and mobile checks pass; the only public data tracked is the validated `public-bundle/`; the current CMS remains reachable at `/admin.html`.
