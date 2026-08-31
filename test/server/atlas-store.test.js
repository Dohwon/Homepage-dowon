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

  assert.equal(bootstrap.version, "a3470656b7815d31fd5a1f75de9bb0e67137c9d0b75e68bbf01e00912b7efeb2");
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

test("loads reviewed cover metadata separately from image bytes", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-cover-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), Buffer.from("fixture")]);
  await fsp.writeFile(path.join(temporaryRoot, "projects", "alpha", "cover.json"), JSON.stringify({
    alt: "Alpha implementation screen",
    caption: "Actual implementation",
    content_type: "image/png",
    content_hex: png.toString("hex")
  }));
  const store = createAtlasStore({ bundleDir: temporaryRoot });

  const project = await store.project("alpha");
  const cover = await store.cover("alpha");

  assert.deepEqual(project.cover, {
    src: "/api/atlas/projects/alpha/cover",
    alt: "Alpha implementation screen",
    caption: "Actual implementation"
  });
  assert.equal(project.coverData, undefined);
  assert.equal(cover.contentType, "image/png");
  assert.deepEqual(cover.bytes, png);
});

test("loads paired system map metadata and SVG with validated decision references", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-system-map-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const projectDir = path.join(temporaryRoot, "projects", "alpha");
  await fsp.writeFile(path.join(projectDir, "system-map.json"), JSON.stringify({
    project_id: "alpha",
    title: "Routing contract map",
    summary: "The request crosses a deterministic routing boundary.",
    nodes: [
      { id: "request", label: "Request", kind: "input", description: "The public input." },
      { id: "router", label: "Router", kind: "process", description: "The routing decision." }
    ],
    flows: [{ id: "route", from: "request", to: "router", label: "validate" }],
    decision_links: [{ node_ids: ["request", "router"], section_id: "routing", label: "Keep routing deterministic" }]
  }));
  await fsp.writeFile(path.join(projectDir, "system-map.svg"), '<svg xmlns="http://www.w3.org/2000/svg"><title>Map</title></svg>');

  const project = await createAtlasStore({ bundleDir: temporaryRoot }).project("alpha");

  assert.equal(project.systemMapData.title, "Routing contract map");
  assert.equal(project.systemMapData.decision_links[0].section_id, "routing");
  assert.match(project.systemMap, /<svg/);
});

test("rejects non-public evidence URLs in the v2 store loader", async (t) => {
  const cases = [
    "http://example.com/doc",
    "https://user:pass@example.com/doc",
    "https://localhost/doc",
    "https://foo.localhost/doc",
    "https://foo.local/doc",
    "https://foo.internal/doc",
    "https://127.0.0.1/doc",
    "https://10.0.0.5/doc",
    "https://169.254.1.2/doc",
    "https://192.168.1.5/doc",
    "https://172.16.0.1/doc",
    "https://[::1]/doc",
    "https://[fc00::1]/doc",
    "https://[fe80::1]/doc",
    "https://[::ffff:192.168.0.1]/doc",
    "javascript:alert(1)",
    "javascript&#58;alert(1)",
    "%6a%61%76%61%73%63%72%69%70%74:alert(1)",
    "https://example.com/&#x110000;",
    "https://example.com/&#xD800;",
    "https://example.com/&#x;"
  ];

  for (const url of cases) {
    const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-invalid-evidence-url-"));
    t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
    await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
    const evidencePath = path.join(temporaryRoot, "projects", "alpha", "evidence.json");
    const evidence = JSON.parse(await fsp.readFile(evidencePath, "utf8"));
    evidence[0].url = url;
    await fsp.writeFile(evidencePath, JSON.stringify(evidence));

    await assert.rejects(
      () => createAtlasStore({ bundleDir: temporaryRoot }).project("alpha"),
      /invalid_atlas_evidence/,
      url
    );
  }
});

test("accepts safe public HTTPS evidence URLs in the v2 store loader", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-safe-evidence-url-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const evidencePath = path.join(temporaryRoot, "projects", "alpha", "evidence.json");
  const evidence = JSON.parse(await fsp.readFile(evidencePath, "utf8"));
  evidence[0].url = "https://example.com/report";
  await fsp.writeFile(evidencePath, JSON.stringify(evidence));

  const project = await createAtlasStore({ bundleDir: temporaryRoot }).project("alpha");

  assert.equal(project.evidence[0].url, "https://example.com/report");
});

test("loads actual legacy graph records and sections only from an explicit v1 manifest", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-v1-bundle-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const manifestPath = path.join(temporaryRoot, "manifest.json");
  const manifest = JSON.parse(await fsp.readFile(manifestPath, "utf8"));
  manifest.format_version = 1;
  await fsp.writeFile(manifestPath, JSON.stringify(manifest));
  await fsp.writeFile(path.join(temporaryRoot, "graph", "nodes.json"), JSON.stringify([
    { id: "project:alpha", label: "Alpha Project", kind: "project" },
    { id: "project:beta", label: "Beta Project", kind: "project" },
    { id: "domain:data%20quality", label: "Data Quality", kind: "domain" }
  ]));
  await fsp.writeFile(path.join(temporaryRoot, "graph", "edges.json"), JSON.stringify([
    { source: "project:beta", target: "domain:data%20quality", kind: "tag-membership", weight: 1, reasons: [] },
    { source: "project:alpha", target: "project:beta", kind: "project-similarity", weight: 4, reasons: ["domain:Data Quality"] }
  ]));
  await fsp.writeFile(path.join(temporaryRoot, "projects", "alpha", "decisions.md"), "# Decisions\n");

  const project = await createAtlasStore({ bundleDir: temporaryRoot }).project("alpha");
  const graph = await createAtlasStore({ bundleDir: temporaryRoot }).graph();

  assert.equal(project.decisions, "# Decisions\n");
  assert.equal(project.article, undefined);
  assert.deepEqual(graph.nodes.map((node) => node.kind), ["project", "project", "domain"]);
  assert.equal(graph.edges[0].kind, "tag-membership");
  assert.equal(graph.edges[1].kind, "project-similarity");
});

test("v2 rejects legacy graph record shapes", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-v2-legacy-graph-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  await fsp.writeFile(path.join(temporaryRoot, "graph", "nodes.json"), JSON.stringify([
    { id: "project:alpha", label: "Alpha Project", kind: "project" }
  ]));
  await fsp.writeFile(path.join(temporaryRoot, "graph", "edges.json"), "[]");

  await assert.rejects(
    () => createAtlasStore({ bundleDir: temporaryRoot }).graph(),
    /invalid_atlas_graph_node/
  );
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

test("rejects invalid v2 article identity and reference lists", async (t) => {
  const cases = [
    ["duplicate section", (article) => { article.sections.push({ ...article.sections[0], diagrams: [] }); }],
    ["duplicate decision", (article) => {
      article.decision_index = [
        { decision_id: "routing-decision", section_id: "routing", status: "adopted", evidence_ids: ["routing-proof"] },
        { decision_id: "routing-decision", section_id: "routing", status: "adopted", evidence_ids: ["routing-proof"] }
      ];
    }],
    ["duplicate section evidence", (article) => { article.sections[0].evidence_ids = ["routing-proof", "routing-proof"]; }],
    ["duplicate decision evidence", (article) => {
      article.decision_index = [{ decision_id: "routing-decision", section_id: "routing", status: "adopted", evidence_ids: ["routing-proof", "routing-proof"] }];
    }],
    ["missing decision section", (article) => {
      article.decision_index = [{ decision_id: "routing-decision", section_id: "missing-section", status: "adopted", evidence_ids: ["routing-proof"] }];
    }]
  ];

  for (const [label, mutate] of cases) {
    const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-invalid-article-"));
    t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
    await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
    const articlePath = path.join(temporaryRoot, "projects", "alpha", "article.json");
    const article = JSON.parse(await fsp.readFile(articlePath, "utf8"));
    mutate(article);
    await fsp.writeFile(articlePath, JSON.stringify(article));

    await assert.rejects(
      () => createAtlasStore({ bundleDir: temporaryRoot }).project("alpha"),
      /invalid_atlas_article/,
      label
    );
  }
});

test("rejects duplicate public search document IDs", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-duplicate-search-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const searchPath = path.join(temporaryRoot, "search-index.json");
  const records = JSON.parse(await fsp.readFile(searchPath, "utf8"));
  records.push({ ...records[0] });
  await fsp.writeFile(searchPath, JSON.stringify(records));

  await assert.rejects(
    () => createAtlasStore({ bundleDir: temporaryRoot }).search("routing"),
    /invalid_atlas_search_record/
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

test("server accepts KG records and strips no allowed relation evidence", async () => {
  const graph = await createStore().graph();

  assert.deepEqual(
    new Set(graph.nodes.map((node) => node.kind)),
    new Set(["KnowledgeFocus", "Project", "KnowledgeDomain"])
  );
  assert.equal(graph.edges.some((edge) => edge.kind === "project-similarity"), false);
  assert.deepEqual(graph.edges[0].evidence_links, [
    { label: "Routing spec", url: "/projects/alpha?tab=evidence" }
  ]);
});

test("rejects unsafe KG evidence links and labels", async (t) => {
  const cases = [
    ["evidence link", "edges.json", (records) => {
      records[0].evidence_links[0].url = "javascript:alert(1)";
    }, /invalid_atlas_graph_edge/],
    ["evidence label absolute path", "edges.json", (records) => {
      records[0].evidence_links[0].label = "/etc/atlas/private.txt";
    }, /invalid_atlas_graph_edge/],
    ["evidence label Windows drive path", "edges.json", (records) => {
      records[0].evidence_links[0].label = "C:\\atlas\\private.txt";
    }, /invalid_atlas_graph_edge/],
    ["node label", "nodes.json", (records) => {
      records[0].label = "/home/dowon/private";
    }, /unsafe_public_content/]
  ];

  for (const [label, filename, mutate, expected] of cases) {
    const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-unsafe-graph-"));
    t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
    await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
    const graphPath = path.join(temporaryRoot, "graph", filename);
    const records = JSON.parse(await fsp.readFile(graphPath, "utf8"));
    mutate(records);
    await fsp.writeFile(graphPath, JSON.stringify(records));

    await assert.rejects(
      () => createAtlasStore({ bundleDir: temporaryRoot }).graph(),
      expected,
      label
    );
  }
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
  const graph = await store.graph();
  assert.equal(graph.nodes.some((node) => node.id === "project:alpha"), false);
  assert.deepEqual(
    new Set(graph.nodes.filter((node) => node.kind === "KnowledgeFocus").map((node) => node.id)),
    new Set(["focus:ai-quality", "focus:product-delivery"])
  );
  assert.equal(graph.nodes.filter((node) => node.kind === "KnowledgeDomain").length, 8);
  assert.equal(graph.edges.some((edge) => edge.source === "project:alpha" || edge.target === "project:alpha"), false);
  assert.deepEqual(await store.search("routing"), []);
});

test("hidden project artifacts require a visible owner even through a shared tag", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-hidden-graph-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const nodesPath = path.join(temporaryRoot, "graph", "nodes.json");
  const edgesPath = path.join(temporaryRoot, "graph", "edges.json");
  const nodes = JSON.parse(await fsp.readFile(nodesPath, "utf8"));
  const edges = JSON.parse(await fsp.readFile(edgesPath, "utf8"));
  nodes.push(
    { id: "technology:node", label: "Node.js", kind: "Technology", url: "", summary: "" },
    { id: "artifact:alpha:routing", label: "Routing proof", kind: "Artifact", url: "/projects/alpha?tab=evidence", summary: "Routing proof" },
    { id: "tag:routing", label: "Routing", kind: "KnowledgeTag", url: "", summary: "" },
    { id: "tag:artifact-parent", label: "Artifact Parent", kind: "KnowledgeTag", url: "", summary: "" },
    { id: "tag:artifact-only", label: "Artifact Only", kind: "KnowledgeTag", url: "", summary: "" }
  );
  edges.push(
    { id: "uses_tech:project%3Aalpha:technology%3Anode", source: "project:alpha", target: "technology:node", kind: "USES_TECH", weight: 1, evidence_links: [] },
    { id: "produces_artifact:project%3Aalpha:artifact%3Aalpha%3Arouting", source: "project:alpha", target: "artifact:alpha:routing", kind: "PRODUCES_ARTIFACT", weight: 1, evidence_links: [] },
    { id: "artifact_has_tag:artifact%3Aalpha%3Arouting:tag%3Arouting", source: "artifact:alpha:routing", target: "tag:routing", kind: "ARTIFACT_HAS_TAG", weight: 1, evidence_links: [] },
    { id: "has_tag:project%3Abeta:tag%3Arouting", source: "project:beta", target: "tag:routing", kind: "HAS_TAG", weight: 1, evidence_links: [] },
    { id: "has_subtag:domain%3Arouting:tag%3Aartifact-parent", source: "domain:routing", target: "tag:artifact-parent", kind: "HAS_SUBTAG", weight: 1, evidence_links: [] },
    { id: "has_subtag:tag%3Aartifact-parent:tag%3Aartifact-only", source: "tag:artifact-parent", target: "tag:artifact-only", kind: "HAS_SUBTAG", weight: 1, evidence_links: [] },
    { id: "artifact_has_tag:artifact%3Aalpha%3Arouting:tag%3Aartifact-only", source: "artifact:alpha:routing", target: "tag:artifact-only", kind: "ARTIFACT_HAS_TAG", weight: 1, evidence_links: [] }
  );
  await fsp.writeFile(nodesPath, JSON.stringify(nodes));
  await fsp.writeFile(edgesPath, JSON.stringify(edges));

  const graph = await createAtlasStore({
    bundleDir: temporaryRoot,
    loadCmsContent: async () => ({ meta: { hiddenProjectIds: ["alpha"] } })
  }).graph();

  assert.equal(graph.nodes.some((node) => node.kind === "Artifact"), false);
  assert.equal(graph.nodes.some((node) => node.kind === "Technology"), false);
  assert.equal(graph.nodes.some((node) => node.id === "tag:routing"), true);
  assert.equal(graph.nodes.some((node) => node.id === "tag:artifact-parent"), false);
  assert.equal(graph.nodes.some((node) => node.id === "tag:artifact-only"), false);
  assert.equal(graph.edges.some((edge) => edge.source === "artifact:alpha:routing"), false);
  assert.equal(graph.edges.some((edge) => edge.source.includes("alpha") || edge.target.includes("alpha")), false);
});

test("hidden evidence owners cannot remain on relations between visible projects", async (t) => {
  const temporaryRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-hidden-evidence-owner-"));
  t.after(() => fsp.rm(temporaryRoot, { recursive: true, force: true }));
  await fsp.cp(fixtureDir, temporaryRoot, { recursive: true });
  const edgesPath = path.join(temporaryRoot, "graph", "edges.json");
  const edges = JSON.parse(await fsp.readFile(edgesPath, "utf8"));
  edges[0].evidence_links = [
    { label: "Third private project proof", url: "/projects/third?tab=evidence" }
  ];
  await fsp.writeFile(edgesPath, JSON.stringify(edges));
  const store = createAtlasStore({
    bundleDir: temporaryRoot,
    loadCmsContent: async () => ({ meta: { hiddenProjectIds: ["third"] } })
  });

  const graph = await store.graph();

  assert.equal(graph.edges.some((edge) => edge.id === edges[0].id), false);
  assert.equal(JSON.stringify(graph).includes("third"), false);
  assert.equal(JSON.stringify(graph).includes("Third private project proof"), false);
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
