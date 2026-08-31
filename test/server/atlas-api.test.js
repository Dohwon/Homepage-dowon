const test = require("node:test");
const assert = require("node:assert/strict");
const fsp = require("node:fs/promises");
const path = require("node:path");
const { handleAtlasApi } = require("../../lib/atlas-routes");
const { fixtureDir, request, startTestServer } = require("./helpers");

async function useServer(t) {
  const server = await startTestServer({ atlasBundleDir: fixtureDir });
  t.after(() => server.close());
  return server;
}

async function loginAsAdmin(server) {
  const response = await request(server.url, "/api/auth/dev", {
    method: "POST",
    body: { email: "admin@example.com" }
  });
  assert.equal(response.status, 200);
  return (response.headers["set-cookie"] || []).map((cookie) => cookie.split(";", 1)[0]).join("; ");
}

test("atlas dispatcher leaves non-Atlas routes to the existing API", async () => {
  const handled = await handleAtlasApi(
    { method: "GET" },
    {},
    new URL("http://atlas.test/api/health"),
    {}
  );

  assert.equal(handled, false);
});

test("atlas API exposes project tabs but no sessions or provenance", async (t) => {
  const server = await useServer(t);
  const response = await request(server.url, "/api/atlas/projects/alpha");
  const payload = response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.id, "alpha");
  assert.equal(payload.article.sections[0].id, "routing");
  assert.equal(payload.buildStory, undefined);
  assert.equal(payload.sessions, undefined);
  assert.equal(payload.provenance, undefined);
});

test("unknown project returns 404", async (t) => {
  const server = await useServer(t);

  assert.equal((await request(server.url, "/api/atlas/projects/missing")).status, 404);
});

test("root and Atlas deep links serve the public shell while admin remains reachable", async (t) => {
  const server = await useServer(t);
  const root = (await request(server.url, "/")).text;
  const deepLink = (await request(server.url, "/projects/alpha?tab=decisions")).text;
  const admin = (await request(server.url, "/admin.html")).text;

  assert.match(root, /id="atlas-main"/);
  assert.match(root, /data-view="graph"/);
  assert.match(deepLink, /id="atlas-main"/);
  assert.match(admin, /id="project-editor-form"/);
  assert.match(admin, /admin\.css/);
  assert.match(admin, /admin\.js/);
});

test("public bundle artifacts remain API-only", async (t) => {
  const server = await useServer(t);

  assert.equal((await request(server.url, "/public-bundle/manifest.json")).status, 404);
  assert.equal((await request(server.url, "/public-bundle/projects/alpha/visuals/problem-solving.svg")).status, 404);
});

test("reviewed project covers are served through the bounded Atlas image route", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(require("node:os").tmpdir(), "atlas-cover-route-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), Buffer.from("fixture")]);
  await fsp.writeFile(path.join(temporaryRoot, "projects", "alpha", "cover.json"), JSON.stringify({
    alt: "Alpha implementation screen",
    caption: "Actual implementation",
    content_type: "image/png",
    content_hex: png.toString("hex")
  }));
  const server = await startTestServer({ atlasBundleDir: temporaryRoot });
  t.after(() => server.close());

  const response = await request(server.url, "/api/atlas/projects/alpha/cover");

  assert.equal(response.status, 200);
  assert.equal(response.headers["content-type"], "image/png");
  assert.equal(Number(response.headers["content-length"]), png.length);
  assert.equal((await request(server.url, "/api/atlas/projects/beta/cover")).status, 404);
});

test("server implementation and library source are never static assets", async (t) => {
  const server = await useServer(t);

  assert.equal((await request(server.url, "/server.js")).status, 404);
  assert.equal((await request(server.url, "/lib/atlas-store.js")).status, 404);
  assert.equal((await request(server.url, "/package.json")).status, 404);
});

test("CMS previews remain reachable when portfolio data lives outside the service root", async (t) => {
  const server = await startTestServer({
    atlasBundleDir: fixtureDir,
    async prepareDataDir(dataDir) {
      const previewDir = path.join(dataDir, "previews");
      await fsp.mkdir(previewDir, { recursive: true });
      await fsp.writeFile(path.join(previewDir, "keyboard-piano.mp4"), "preview-fixture");
    }
  });
  t.after(() => server.close());

  const bootstrap = (await request(server.url, "/api/bootstrap")).json();
  const project = bootstrap.projects.find((item) => item.id === "keyboard-piano");
  const preview = await request(server.url, project.preview.video);

  assert.equal(project.preview.video, "/media/previews/keyboard-piano.mp4");
  assert.equal(preview.status, 200);
  assert.equal(preview.text, "preview-fixture");
});

test("bootstrap, graph, and search routes expose stable bundle data", async (t) => {
  const server = await useServer(t);
  const bootstrap = (await request(server.url, "/api/atlas/bootstrap")).json();
  const graph = (await request(server.url, "/api/atlas/graph")).json();
  const search = (await request(server.url, "/api/atlas/search?q=ROUTING")).json();

  assert.equal(bootstrap.version, "a3470656b7815d31fd5a1f75de9bb0e67137c9d0b75e68bbf01e00912b7efeb2");
  assert.deepEqual(bootstrap.projects.map((project) => project.id), ["alpha", "beta"]);
  assert.equal(graph.nodes.length, 12);
  assert.deepEqual(search.items.map((item) => item.id), ["alpha-overview", "article:alpha:routing"]);
});

test("existing API families remain reachable with isolated test data", async (t) => {
  const server = await useServer(t);
  const bootstrapResponse = await request(server.url, "/api/bootstrap");
  const healthResponse = await request(server.url, "/api/health");
  const analyticsResponse = await request(server.url, "/api/analytics/visit", {
    method: "POST",
    body: { surface: "atlas-test" }
  });
  const cookie = await loginAsAdmin(server);
  const cmsResponse = await request(server.url, "/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: cookie },
    body: { project: { id: "api-regression", name: "API Regression", summary: "Safe summary" } }
  });
  const blogResponse = await request(server.url, "/api/blog", {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: cookie },
    body: { blogPost: { id: "api-regression", title: "API Regression", excerpt: "Safe excerpt", markdown: "Safe body" } }
  });

  assert.equal(bootstrapResponse.status, 200);
  assert.equal(healthResponse.status, 200);
  assert.equal(analyticsResponse.status, 201);
  assert.equal(cmsResponse.status, 200);
  assert.equal(blogResponse.status, 200);
});

test("CMS rejects unsafe public presentation content before storage", async (t) => {
  const server = await useServer(t);
  const cookie = await loginAsAdmin(server);
  const response = await request(server.url, "/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: cookie },
    body: {
      project: {
        id: "alpha",
        name: "Alpha Project",
        summary: "read /home/dowon/private"
      }
    }
  });

  assert.equal(response.status, 400);
  assert.deepEqual(response.json(), {
    error: "unsafe_public_content",
    category: "absolute_path"
  });
});
