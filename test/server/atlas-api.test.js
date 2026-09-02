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

test("root and Atlas deep links serve the public shell while the unrelated admin surface is unavailable", async (t) => {
  const server = await useServer(t);
  const root = (await request(server.url, "/")).text;
  const deepLink = (await request(server.url, "/projects/alpha?tab=decisions")).text;
  const admin = await request(server.url, "/admin.html");
  const adminCss = await request(server.url, "/admin.css");
  const adminJs = await request(server.url, "/admin.js");

  assert.match(root, /id="atlas-main"/);
  assert.match(root, /data-view="graph"/);
  assert.match(deepLink, /id="atlas-main"/);
  assert.equal(admin.status, 404);
  assert.equal(adminCss.status, 404);
  assert.equal(adminJs.status, 404);
});

test("public API is read-only and has no comment surface", async (t) => {
  const server = await useServer(t);

  const projectWrite = await request(server.url, "/api/projects", {
    method: "POST",
    body: {}
  });
  const blogWrite = await request(server.url, "/api/blog", {
    method: "POST",
    body: {}
  });
  const comments = await request(server.url, "/api/comments?projectId=alpha");
  const blogComments = await request(server.url, "/api/blog-comments?blogId=alpha");

  assert.equal(projectWrite.status, 405);
  assert.equal(blogWrite.status, 405);
  assert.equal(comments.status, 404);
  assert.equal(blogComments.status, 404);
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

test("reviewed project captures are served through the bounded capture route", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(require("node:os").tmpdir(), "atlas-capture-route-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), Buffer.from("fixture")]);
  await fsp.writeFile(path.join(temporaryRoot, "projects", "alpha", "captures.json"), JSON.stringify([{
    id: "home",
    alt: "Alpha home screen",
    caption: "The primary implementation screen",
    role: "overview",
    content_type: "image/png",
    content_hex: png.toString("hex")
  }]));
  const server = await startTestServer({ atlasBundleDir: temporaryRoot });
  t.after(() => server.close());

  const response = await request(server.url, "/api/atlas/projects/alpha/captures/home");

  assert.equal(response.status, 200);
  assert.equal(response.headers["content-type"], "image/png");
  assert.equal(Number(response.headers["content-length"]), png.length);
  assert.equal((await request(server.url, "/api/atlas/projects/alpha/captures/missing")).status, 404);
});

test("server implementation and library source are never static assets", async (t) => {
  const server = await useServer(t);

  assert.equal((await request(server.url, "/server.js")).status, 404);
  assert.equal((await request(server.url, "/lib/atlas-store.js")).status, 404);
  assert.equal((await request(server.url, "/package.json")).status, 404);
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

test("owner pin manifest controls the public project order", async (t) => {
  const ownerPinsPath = path.join(await fsp.mkdtemp(path.join(require("node:os").tmpdir(), "atlas-owner-pins-")), "owner-pins.json");
  t.after(() => fsp.rm(path.dirname(ownerPinsPath), { recursive: true, force: true }));
  await fsp.writeFile(ownerPinsPath, JSON.stringify({ projectIds: ["alpha"] }));
  const server = await startTestServer({ ownerPinsPath });
  t.after(() => server.close());

  const bootstrap = (await request(server.url, "/api/atlas/bootstrap")).json();

  assert.equal(bootstrap.projects[0].id, "alpha");
  assert.equal(bootstrap.projects[0].pinned, true);
});

test("legacy CMS API is unavailable from the public deployment", async (t) => {
  const server = await useServer(t);
  const bootstrapResponse = await request(server.url, "/api/bootstrap");
  const healthResponse = await request(server.url, "/api/health");
  const analyticsResponse = await request(server.url, "/api/analytics/visit", {
    method: "POST",
    body: { surface: "atlas-test" }
  });
  const authResponse = await request(server.url, "/api/auth/dev", {
    method: "POST",
    body: { email: "admin@example.com" }
  });
  const cmsResponse = await request(server.url, "/api/projects", {
    method: "POST",
    body: { project: { id: "api-regression", name: "API Regression", summary: "Safe summary" } }
  });
  const blogResponse = await request(server.url, "/api/blog", {
    method: "POST",
    body: { blogPost: { id: "api-regression", title: "API Regression", excerpt: "Safe excerpt", markdown: "Safe body" } }
  });

  assert.equal(bootstrapResponse.status, 404);
  assert.equal(healthResponse.status, 200);
  assert.equal(analyticsResponse.status, 405);
  assert.equal(authResponse.status, 405);
  assert.equal(cmsResponse.status, 405);
  assert.equal(blogResponse.status, 405);
});
