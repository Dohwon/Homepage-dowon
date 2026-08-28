const test = require("node:test");
const assert = require("node:assert/strict");
const fsp = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { createAtlasStore } = require("../../lib/atlas-store");

const fixtureDir = path.join(__dirname, "../fixtures/public-bundle");

function createStore(cms = {}) {
  return createAtlasStore({
    bundleDir: fixtureDir,
    loadCmsContent: async () => cms
  });
}

test("loads the v2 public bundle and omits heavy content from bootstrap", async () => {
  const store = createStore();

  const bootstrap = await store.bootstrap();
  const project = await store.project("alpha");

  assert.equal(bootstrap.version, "31dab58058afafc3a2f772323754250837287090dce78b56deb7c8f4c40d72e0");
  assert.deepEqual(bootstrap.projects.map((item) => item.id), ["alpha", "beta"]);
  assert.equal(bootstrap.topics.length, 10);
  assert.equal(bootstrap.changelog.length, 2);
  assert.equal(bootstrap.projects[0].article, undefined);
  assert.equal(project.article.sections[0].id, "routing");
  assert.equal(project.sessions, undefined);
  assert.equal(project.provenance, undefined);
});

test("loads structured v2 public project content without legacy fields", async () => {
  const project = await createStore().project("alpha");

  assert.equal(project.article.sections[0].id, "routing");
  assert.equal(project.timeline[0].event_id, "alpha-1");
  assert.match(project.visuals["routing-flow"], /<svg/);
  assert.equal(project.buildStory, undefined);
  assert.equal(project.decisions, undefined);
  assert.equal(project.visualMap, undefined);
});

test("loads legacy sections only from an explicit v1 manifest", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-v1-bundle-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const manifestPath = path.join(temporaryRoot, "manifest.json");
  const manifest = JSON.parse(await fsp.readFile(manifestPath, "utf8"));
  manifest.format_version = 1;
  await fsp.writeFile(manifestPath, JSON.stringify(manifest));
  await fsp.writeFile(path.join(temporaryRoot, "projects", "alpha", "decisions.md"), "# Decisions\n");

  const project = await createAtlasStore({ bundleDir: temporaryRoot }).project("alpha");

  assert.equal(project.decisions, "# Decisions\n");
  assert.equal(project.article, undefined);
});

test("rejects a manifest without an explicit migration version", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-no-format-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const manifestPath = path.join(temporaryRoot, "manifest.json");
  const manifest = JSON.parse(await fsp.readFile(manifestPath, "utf8"));
  delete manifest.format_version;
  await fsp.writeFile(manifestPath, JSON.stringify(manifest));

  await assert.rejects(
    () => createAtlasStore({ bundleDir: temporaryRoot }).project("alpha"),
    /invalid_atlas_manifest/
  );
});

test("fails closed when a generated project contains fields outside the public schema", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-unknown-field-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const projectPath = path.join(temporaryRoot, "projects", "alpha", "project.json");
  const project = JSON.parse(await fsp.readFile(projectPath, "utf8"));
  project.sessions = [{ transcript: "not public" }];
  await fsp.writeFile(projectPath, JSON.stringify(project));

  const store = createAtlasStore({ bundleDir: temporaryRoot });

  await assert.rejects(() => store.project("alpha"), /invalid_atlas_project_field/);
});

test("rejects graph kinds that are not part of the public graph schema", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-invalid-graph-kind-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const nodesPath = path.join(temporaryRoot, "graph", "nodes.json");
  const nodes = JSON.parse(await fsp.readFile(nodesPath, "utf8"));
  nodes[0].kind = "x);background-image:url(https://evil.example/pixel";
  await fsp.writeFile(nodesPath, JSON.stringify(nodes));

  const store = createAtlasStore({ bundleDir: temporaryRoot });

  await assert.rejects(() => store.graph(), /invalid_atlas_graph_node/);
});

test("returns an explicit empty Atlas state when no promoted bundle exists", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-missing-bundle-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  const store = createAtlasStore({ bundleDir: path.join(temporaryRoot, "public-bundle") });

  assert.deepEqual(await store.bootstrap(), {
    version: "unavailable",
    projects: [],
    topics: [],
    changelog: []
  });
  assert.deepEqual(await store.graph(), { nodes: [], edges: [] });
  assert.deepEqual(await store.search("anything"), []);
});

test("manual public fields override generated values", async () => {
  const store = createStore({
    meta: { hiddenProjectIds: [] },
    projects: [{
      id: "alpha",
      summary: "Curated CMS summary",
      highlights: ["Curated highlight"],
      path: "/home/dowon/private",
      arbitrary: "must not publish"
    }]
  });

  const project = await store.project("alpha");

  assert.equal(project.summary, "Curated CMS summary");
  assert.deepEqual(project.highlights, ["Curated highlight"]);
  assert.equal(project.path, undefined);
  assert.equal(project.arbitrary, undefined);
});

test("hidden generated projects are omitted from every public collection", async () => {
  const store = createStore({
    meta: { hiddenProjectIds: ["alpha"] },
    projects: []
  });

  assert.deepEqual((await store.bootstrap()).projects.map((project) => project.id), ["beta"]);
  assert.deepEqual((await store.bootstrap()).topics.map((topic) => topic.label), ["Data Quality", "Verified report", "Reproducible evaluation", "Unclear evidence", "Python"]);
  assert.deepEqual((await store.bootstrap()).changelog.map((entry) => entry.project_id), ["beta"]);
  assert.deepEqual((await store.graph()).nodes.map((node) => node.id), ["domain:data%20quality", "outcome:verified%20report", "pattern:reproducible%20evaluation", "problem:unclear%20evidence", "project:beta", "technology:python"]);
  assert.deepEqual(await store.search("routing"), []);
});

test("unsafe CMS presentation fields cannot override a public project", async () => {
  const store = createStore({
    meta: { hiddenProjectIds: [] },
    projects: [{ id: "alpha", summary: "read /home/dowon/private" }]
  });

  await assert.rejects(() => store.project("alpha"), /unsafe_public_content: absolute_path/);
});

test("privacy checks recurse through allowlisted CMS values", async () => {
  const store = createStore({
    projects: [{
      id: "alpha",
      links: { docs: "http://192.168.0.5/internal" }
    }]
  });

  await assert.rejects(() => store.project("alpha"), /unsafe_public_content: private_ip/);
});

test("search is case-insensitive, stable, and excludes hidden projects", async () => {
  const store = createStore({ meta: { hiddenProjectIds: ["beta"] } });

  const items = await store.search("ROUTING");

  assert.deepEqual(items.map((item) => item.id), ["alpha-overview", "article:alpha:routing"]);
});
