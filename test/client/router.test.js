const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function importBrowserModule(relativePath) {
  const absolutePath = path.join(__dirname, "../..", relativePath);
  const source = await fs.readFile(absolutePath, "utf8");
  const encoded = Buffer.from(`${source}\n//# sourceURL=${pathToFileURL(absolutePath).href}`).toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: name => name.toLowerCase() === "content-type" ? "application/json" : null },
    json: async () => structuredClone(payload)
  };
}

test("project routes expose four decision-reader tabs", async () => {
  const { parseRoute, PROJECT_TABS } = await importBrowserModule("client/router.js");
  const publicTabs = ["decisions", "system-map", "build-timeline", "evidence"];

  assert.deepEqual([...PROJECT_TABS], publicTabs);
  assert.deepEqual(
    parseRoute(new URL("https://atlas.test/projects/alpha")),
    { view: "project", projectId: "alpha", tab: "decisions" }
  );
  for (const tab of publicTabs) {
    assert.deepEqual(
      parseRoute(new URL(`https://atlas.test/projects/alpha?tab=${tab}`)),
      { view: "project", projectId: "alpha", tab }
    );
  }
});

test("legacy project tabs normalize without exposing removed tabs", async () => {
  const { normalizeTab, parseRoute, PROJECT_TABS } = await importBrowserModule("client/router.js");

  assert.equal(PROJECT_TABS.has("sessions"), false);
  assert.equal(PROJECT_TABS.has("provenance"), false);
  assert.equal(normalizeTab("overview"), "decisions");
  assert.equal(normalizeTab("build-story"), "build-timeline");
  assert.equal(normalizeTab("visual-map"), "system-map");
  assert.equal(normalizeTab("rollbacks"), "evidence");
  assert.equal(normalizeTab("artifacts"), "evidence");
  for (const tab of ["sessions", "provenance", "unknown", "", null]) {
    assert.equal(normalizeTab(tab), "decisions");
  }
  assert.deepEqual(
    parseRoute(new URL("https://atlas.test/projects/alpha?tab=sessions")),
    { view: "project", projectId: "alpha", tab: "decisions" }
  );
  assert.deepEqual(
    parseRoute(new URL("https://atlas.test/projects/alpha?tab=provenance")),
    { view: "project", projectId: "alpha", tab: "decisions" }
  );
});

test("prototype keys and non-string tab values always normalize to decisions", async () => {
  const { normalizeTab, parseRoute, toRouteHref } = await importBrowserModule("client/router.js");
  const prototypeKeys = ["constructor", "toString", "hasOwnProperty", "__proto__"];

  for (const value of prototypeKeys) {
    assert.equal(normalizeTab(value), "decisions");
    assert.deepEqual(
      parseRoute(new URL(`https://atlas.test/projects/alpha?tab=${encodeURIComponent(value)}`)),
      { view: "project", projectId: "alpha", tab: "decisions" }
    );
    assert.equal(
      toRouteHref({ view: "project", projectId: "alpha", tab: value }),
      "/projects/alpha"
    );
  }

  for (const value of [undefined, null, 0, false, Symbol("tab"), { tab: "overview" }, ["overview"]]) {
    assert.equal(normalizeTab(value), "decisions");
  }
});

test("public route allowlists cannot be extended at runtime", async () => {
  const { PROJECT_TABS, VIEWS } = await importBrowserModule("client/router.js");

  assert.throws(() => PROJECT_TABS.add("sessions"), /readonly_route_allowlist/);
  assert.throws(() => VIEWS.add("provenance"), /readonly_route_allowlist/);
  assert.equal(PROJECT_TABS.has("sessions"), false);
  assert.equal(VIEWS.has("provenance"), false);
});

test("top-level routes use an explicit public allowlist", async () => {
  const { parseRoute, toRouteHref, VIEWS } = await importBrowserModule("client/router.js");

  assert.deepEqual([...VIEWS], ["home", "projects", "topics", "graph", "changelog", "search"]);
  assert.deepEqual(parseRoute(new URL("https://atlas.test/")), { view: "home" });
  assert.deepEqual(parseRoute(new URL("https://atlas.test/graph")), { view: "graph" });
  assert.deepEqual(parseRoute(new URL("https://atlas.test/sessions")), { view: "home" });
  assert.deepEqual(parseRoute(new URL("https://atlas.test/provenance")), { view: "home" });
  assert.equal(toRouteHref({ view: "graph" }), "/graph");
  assert.equal(toRouteHref({ view: "home" }), "/");
});

test("project hrefs encode ids and cannot serialize private tabs", async () => {
  const { parseRoute, toRouteHref } = await importBrowserModule("client/router.js");

  assert.equal(
    toRouteHref({ view: "project", projectId: "alpha beta", tab: "decisions" }),
    "/projects/alpha%20beta"
  );
  assert.equal(
    toRouteHref({ view: "project", projectId: "alpha", tab: "sessions" }),
    "/projects/alpha"
  );
  assert.deepEqual(
    parseRoute(new URL("https://atlas.test/projects/%E0%A4%A?tab=decisions")),
    { view: "home" }
  );
});

test("Atlas API uses encoded public endpoints and JSON requests", async () => {
  const { createAtlasApi } = await importBrowserModule("client/api.js");
  const requests = [];
  const fetchImpl = async (url, options) => {
    requests.push({ url, options });
    return jsonResponse({ ok: true });
  };
  const api = createAtlasApi({ baseUrl: "/api/atlas/", fetchImpl });

  assert.deepEqual(await api.bootstrap(), { ok: true });
  assert.deepEqual(await api.project("alpha beta"), { ok: true });
  assert.deepEqual(await api.graph(), { ok: true });
  assert.deepEqual(await api.search("routing & tabs"), { ok: true });
  assert.deepEqual(
    requests.map(request => request.url),
    [
      "/api/atlas/bootstrap",
      "/api/atlas/projects/alpha%20beta",
      "/api/atlas/graph",
      "/api/atlas/search?q=routing+%26+tabs"
    ]
  );
  for (const request of requests) {
    assert.equal(request.options.method, "GET");
    assert.equal(request.options.headers.Accept, "application/json");
  }
});

test("Atlas API reports bounded errors and rejects empty project ids", async () => {
  const { AtlasApiError, createAtlasApi } = await importBrowserModule("client/api.js");
  const api = createAtlasApi({
    fetchImpl: async () => jsonResponse(
      { error: "project_not_found", privateDetail: "/home/dowon/private" },
      404
    )
  });

  await assert.rejects(() => api.project(""), /project_id_required/);
  await assert.rejects(
    () => api.project("missing"),
    error => error instanceof AtlasApiError
      && error.status === 404
      && error.code === "project_not_found"
      && !error.message.includes("/home/dowon")
  );
});

test("client store normalizes defaults and strips private data recursively", async () => {
  const { createStore } = await importBrowserModule("client/state.js");
  const store = createStore({
    route: { view: "project", projectId: "alpha", tab: "overview" },
    project: {
      id: "alpha",
      sessions: [{ id: "session-1" }],
      Sessions: [{ id: "session-2" }],
      source_locator: "/home/dowon/.codex/sessions/private.jsonl",
      locatorLabel: "Public badge",
      ui_locator: { label: "Visible marker" },
      nested: {
        provenance: { source: "local" },
        PROVENANCE: { source: "local-variant" },
        sourceLocator: "session:private",
        title: "Public"
      }
    }
  });

  assert.deepEqual(store.getState(), {
    route: { view: "project", projectId: "alpha", tab: "overview" },
    bootstrap: null,
    project: {
      id: "alpha",
      locatorLabel: "Public badge",
      ui_locator: { label: "Visible marker" },
      nested: { title: "Public" }
    },
    loading: false,
    error: null
  });
});

test("client store publishes normalized partial updates and supports unsubscribe", async () => {
  const { createStore } = await importBrowserModule("client/state.js");
  const store = createStore();
  const events = [];
  const unsubscribe = store.subscribe((state, previous) => {
    events.push({ state, previous });
  });

  store.setState({ loading: true, provenance: { source: "private" } });
  store.setState(state => ({ loading: !state.loading, project: { id: "alpha", sessions: [] } }));
  unsubscribe();
  store.setState({ error: "late" });

  assert.equal(events.length, 2);
  assert.equal(events[0].previous.loading, false);
  assert.equal(events[0].state.loading, true);
  assert.equal(events[0].state.provenance, undefined);
  assert.deepEqual(events[1].state.project, { id: "alpha" });
  assert.equal(store.getState().error, "late");
});
