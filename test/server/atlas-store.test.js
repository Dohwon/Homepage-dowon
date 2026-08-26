const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { createAtlasStore } = require("../../lib/atlas-store");

const fixtureDir = path.join(__dirname, "../fixtures/public-bundle");

function createStore(cms = {}) {
  return createAtlasStore({
    bundleDir: fixtureDir,
    loadCmsContent: async () => cms
  });
}

test("loads the public bundle and optional project sections", async () => {
  const store = createStore();

  const bootstrap = await store.bootstrap();
  const project = await store.project("alpha");

  assert.equal(bootstrap.version, "test-v1");
  assert.deepEqual(bootstrap.projects.map((item) => item.id), ["alpha", "beta"]);
  assert.equal(bootstrap.topics.length, 2);
  assert.equal(bootstrap.changelog.length, 2);
  assert.match(project.buildStory, /## Constraint/);
  assert.equal(project.sessions, undefined);
  assert.equal(project.provenance, undefined);
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
  assert.deepEqual((await store.bootstrap()).topics.map((topic) => topic.label), ["Data Quality"]);
  assert.deepEqual((await store.bootstrap()).changelog.map((entry) => entry.project_id), ["beta"]);
  assert.deepEqual((await store.graph()).nodes.map((node) => node.id), ["project:beta"]);
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

  assert.deepEqual(items.map((item) => item.id), ["alpha-overview"]);
});
