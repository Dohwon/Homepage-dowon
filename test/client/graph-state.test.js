const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function importGraphStateModule() {
  const absolutePath = path.join(__dirname, "../..", "client/graph-state.js");
  const source = await fs.readFile(absolutePath, "utf8");
  const encoded = Buffer.from(`${source}\n//# sourceURL=${pathToFileURL(absolutePath).href}`).toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

function node(id, kind) {
  return { id, label: id, kind, url: "", summary: "" };
}

function edge(id, source, target, kind) {
  return { id, source, target, kind, weight: 1, evidence_links: [] };
}

function fixtureGraph() {
  return {
    nodes: [
      node("focus:delivery", "KnowledgeFocus"),
      node("project:alpha", "Project"),
      node("project:beta", "Project"),
      node("domain:routing", "KnowledgeDomain"),
      node("tag:routing", "KnowledgeTag"),
      node("technology:python", "Technology"),
      node("artifact:alpha:report", "Artifact"),
      node("domain:disallowed", "KnowledgeDomain"),
    ],
    edges: [
      edge("has-focus:beta", "project:beta", "focus:delivery", "HAS_FOCUS"),
      edge("produces:beta", "project:beta", "artifact:alpha:report", "PRODUCES_ARTIFACT"),
      edge("uses:alpha", "project:alpha", "technology:python", "USES_TECH"),
      edge("focus-domain", "focus:delivery", "domain:routing", "FOCUS_HAS_TAG"),
      edge("has-tag:alpha", "project:alpha", "tag:routing", "HAS_TAG"),
      edge("has-focus:alpha", "project:alpha", "focus:delivery", "HAS_FOCUS"),
      edge("focus-subtag", "focus:delivery", "tag:routing", "HAS_SUBTAG"),
      edge("produces:alpha", "project:alpha", "artifact:alpha:report", "PRODUCES_ARTIFACT"),
      edge("disallowed-project-edge", "project:alpha", "domain:disallowed", "FOCUS_HAS_TAG"),
    ],
  };
}

test("initial graph shows only focuses and connected projects", async () => {
  const { createGraphIndex, initialGraphState, visibleGraph } = await importGraphStateModule();
  const index = createGraphIndex(fixtureGraph());
  const visible = visibleGraph(initialGraphState(index), index);

  assert.deepEqual(
    visible.nodes.map((item) => item.id).sort(),
    ["focus:delivery", "project:alpha", "project:beta"],
  );
  assert.deepEqual(new Set(visible.links.map((link) => link.kind)), new Set(["HAS_FOCUS"]));
});

test("initial graph hides direct relations between visible projects until expansion", async () => {
  const { createGraphIndex, initialGraphState, expandNode, visibleGraph } = await importGraphStateModule();
  const graph = fixtureGraph();
  graph.edges.push(edge("evolved:alpha-beta", "project:alpha", "project:beta", "EVOLVED_FROM"));
  const index = createGraphIndex(graph);
  const initial = initialGraphState(index);

  assert.deepEqual(
    visibleGraph(initial, index).links.map((link) => link.id).sort(),
    ["has-focus:alpha", "has-focus:beta"],
  );

  const expanded = expandNode(initial, "project:alpha", index);
  assert.equal(visibleGraph(expanded, index).links.some((link) => link.id === "evolved:alpha-beta"), true);
  assert.equal(visibleGraph(expanded, index).links.some((link) => link.id === "produces:beta"), false);
});

test("project expansion adds only its exact allowed one-hop neighbors", async () => {
  const { createGraphIndex, initialGraphState, expandNode, visibleGraph } = await importGraphStateModule();
  const index = createGraphIndex(fixtureGraph());
  const initial = initialGraphState(index);
  const state = expandNode(initial, "project:alpha", index);

  assert.deepEqual(
    visibleGraph(state, index).nodes.map((item) => item.id).sort(),
    [
      "artifact:alpha:report",
      "focus:delivery",
      "project:alpha",
      "project:beta",
      "tag:routing",
      "technology:python",
    ],
  );
  assert.deepEqual([...initial.expandedIds], []);
  assert.equal(initial.selectedId, null);
  assert.deepEqual([...state.expandedIds], ["project:alpha"]);
  assert.equal(state.selectedId, "project:alpha");
});

test("focus expansion adds only focus tag and subtag neighbors", async () => {
  const { createGraphIndex, initialGraphState, expandNode, visibleGraph } = await importGraphStateModule();
  const index = createGraphIndex(fixtureGraph());
  const state = expandNode(initialGraphState(index), "focus:delivery", index);

  assert.deepEqual(
    visibleGraph(state, index).nodes.map((item) => item.id).sort(),
    ["domain:routing", "focus:delivery", "project:alpha", "project:beta", "tag:routing"],
  );
});

test("project expansion supports every exact project relation and no others", async () => {
  const { createGraphIndex, initialGraphState, expandNode, visibleGraph } = await importGraphStateModule();
  const allowedKinds = [
    ["HAS_TAG", "tag:allowed", "KnowledgeTag"],
    ["USES_TECH", "technology:allowed", "Technology"],
    ["PRODUCES_ARTIFACT", "artifact:allowed", "Artifact"],
    ["EVOLVED_FROM", "project:evolved", "Project"],
    ["VALIDATES", "project:validated", "Project"],
    ["DEPLOYS", "project:deployed", "Project"],
    ["REUSES_COMPONENT", "project:reused", "Project"],
  ];
  const graph = {
    nodes: [
      node("focus:root", "KnowledgeFocus"),
      node("project:root", "Project"),
      ...allowedKinds.map(([, id, kind]) => node(id, kind)),
      node("tag:disallowed", "KnowledgeTag"),
    ],
    edges: [
      edge("has-focus", "project:root", "focus:root", "HAS_FOCUS"),
      ...allowedKinds.map(([kind, id]) => edge(`allowed:${kind}`, "project:root", id, kind)),
      edge("disallowed", "project:root", "tag:disallowed", "ARTIFACT_HAS_TAG"),
    ],
  };
  const index = createGraphIndex(graph);
  const state = expandNode(initialGraphState(index), "project:root", index);

  assert.deepEqual(
    visibleGraph(state, index).nodes.map((item) => item.id).sort(),
    ["focus:root", "project:root", ...allowedKinds.map(([, id]) => id)].sort(),
  );
});

test("search reveals the deterministic shortest path through a cyclic graph", async () => {
  const { createGraphIndex, initialGraphState, revealPath, visibleGraph } = await importGraphStateModule();
  const graph = {
    nodes: [
      node("focus:root", "KnowledgeFocus"),
      node("domain:z", "KnowledgeDomain"),
      node("project:a", "Project"),
      node("tag:target", "KnowledgeTag"),
    ],
    edges: [
      edge("cycle", "project:a", "domain:z", "VALIDATES"),
      edge("project-target", "project:a", "tag:target", "HAS_TAG"),
      edge("focus-project", "focus:root", "project:a", "HAS_FOCUS"),
      edge("domain-target", "domain:z", "tag:target", "HAS_SUBTAG"),
      edge("focus-domain", "focus:root", "domain:z", "FOCUS_HAS_TAG"),
    ],
  };
  const index = createGraphIndex(graph);
  const state = revealPath(initialGraphState(index), "tag:target", index);

  assert.deepEqual(state.revealedPath, ["focus:root", "domain:z", "tag:target"]);
  assert.deepEqual(
    [...state.visibleNodeIds].sort(),
    ["domain:z", "focus:root", "project:a", "tag:target"],
  );
  assert.equal(state.selectedId, "tag:target");
  assert.deepEqual(
    visibleGraph(state, index).links.map((link) => link.id).sort(),
    ["domain-target", "focus-domain", "focus-project"],
  );
});

test("search for a missing target leaves state unchanged", async () => {
  const { createGraphIndex, initialGraphState, revealPath } = await importGraphStateModule();
  const index = createGraphIndex(fixtureGraph());
  const initial = initialGraphState(index);
  const state = revealPath(initial, "artifact:missing", index);

  assert.deepEqual([...state.visibleNodeIds], [...initial.visibleNodeIds]);
  assert.deepEqual(state.revealedPath, []);
  assert.equal(state.selectedId, null);
  assert.deepEqual([...state.expandedIds], []);
});

test("relation filter returns only existing visible edges of selected kinds", async () => {
  const { createGraphIndex, initialGraphState, expandNode, setRelationFilters, visibleGraph } = await importGraphStateModule();
  const index = createGraphIndex(fixtureGraph());
  const expanded = expandNode(initialGraphState(index), "project:alpha", index);
  const requestedKinds = new Set(["USES_TECH"]);
  const state = setRelationFilters(expanded, requestedKinds);
  requestedKinds.add("HAS_FOCUS");
  const visible = visibleGraph(state, index);

  assert.deepEqual(visible.links.map((link) => link.id), ["uses:alpha"]);
  assert.equal(visible.links.every((link) => link.kind === "USES_TECH"), true);
  assert.deepEqual([...state.relationKinds], ["USES_TECH"]);
  assert.deepEqual([...state.visibleNodeIds], [...expanded.visibleNodeIds]);
});

test("relation filter dims selected neighbors connected only by hidden relations", async () => {
  const { createGraphIndex, initialGraphState, expandNode, setRelationFilters, visibleGraph } = await importGraphStateModule();
  const index = createGraphIndex(fixtureGraph());
  const expanded = expandNode(initialGraphState(index), "project:alpha", index);
  const state = setRelationFilters(expanded, new Set(["USES_TECH"]));
  const projectedNodes = new Map(visibleGraph(state, index).nodes.map((item) => [item.id, item]));

  assert.equal(projectedNodes.get("project:alpha").active, true);
  assert.equal(projectedNodes.get("technology:python").active, true);
  assert.equal(projectedNodes.get("tag:routing").dimmed, true);
  assert.equal(projectedNodes.get("artifact:alpha:report").dimmed, true);
  assert.equal(projectedNodes.get("focus:delivery").dimmed, true);
});

test("visible projection marks the selected neighborhood active and leaves source records unchanged", async () => {
  const { createGraphIndex, initialGraphState, expandNode, visibleGraph } = await importGraphStateModule();
  const graph = fixtureGraph();
  const sourceSnapshot = structuredClone(graph);
  const index = createGraphIndex(graph);
  const initial = initialGraphState(index);
  const state = expandNode(initial, "project:alpha", index);
  const visible = visibleGraph(state, index);
  const projectedNodes = new Map(visible.nodes.map((item) => [item.id, item]));
  const projectedLinks = new Map(visible.links.map((item) => [item.id, item]));

  assert.equal(projectedNodes.get("project:alpha").active, true);
  assert.equal(projectedNodes.get("focus:delivery").active, true);
  assert.equal(projectedNodes.get("technology:python").active, true);
  assert.equal(projectedNodes.get("project:beta").dimmed, true);
  assert.equal(projectedLinks.get("has-focus:alpha").active, true);
  assert.equal(projectedLinks.get("has-focus:beta").dimmed, true);
  assert.deepEqual(graph, sourceSnapshot);
  assert.equal("active" in graph.nodes[0], false);
  assert.equal("dimmed" in graph.edges[0], false);
  assert.notStrictEqual(visible.nodes[0], graph.nodes.find((item) => item.id === visible.nodes[0].id));
  assert.notStrictEqual(visible.links[0], graph.edges.find((item) => item.id === visible.links[0].id));
  assert.equal(Object.isFrozen(initial), true);
  assert.deepEqual([...initial.visibleNodeIds].sort(), ["focus:delivery", "project:alpha", "project:beta"]);
});

test("public state collections reject mutation without changing earlier snapshots", async () => {
  const { createGraphIndex, initialGraphState, visibleGraph } = await importGraphStateModule();
  const index = createGraphIndex(fixtureGraph());
  const state = initialGraphState(index);
  const before = visibleGraph(state, index);

  assert.equal(state.visibleNodeIds instanceof Set, true);
  assert.throws(() => state.visibleNodeIds.clear(), /read-only/i);
  assert.throws(() => state.visibleEdgeIds.clear(), /read-only/i);
  assert.throws(() => state.expandedIds.add("project:injected"), /read-only/i);
  assert.throws(() => state.relationKinds.delete("HAS_FOCUS"), /read-only/i);

  assert.deepEqual(visibleGraph(state, index), before);
  assert.deepEqual([...state.expandedIds], []);
  assert.equal(state.relationKinds.has("HAS_FOCUS"), true);
});

test("public index collections reject mutation without changing graph behavior", async () => {
  const { createGraphIndex, initialGraphState, expandNode, revealPath, visibleGraph } = await importGraphStateModule();
  const graph = fixtureGraph();
  const index = createGraphIndex(graph);
  let exposedNodes;
  index.nodes.forEach((_value, _key, collection) => {
    exposedNodes = collection;
  });

  assert.equal(index.nodes instanceof Map, true);
  assert.equal(index.edgeKinds instanceof Set, true);
  assert.strictEqual(index.nodes.valueOf(), index.nodes);
  assert.strictEqual(exposedNodes, index.nodes);
  assert.throws(() => index.nodes.clear(), /read-only/i);
  assert.throws(() => index.nodesByKind.set("Project", []), /read-only/i);
  assert.throws(() => index.adjacency.delete("project:alpha"), /read-only/i);
  assert.throws(() => index.edgeKinds.add("INJECTED"), /read-only/i);
  assert.throws(() => exposedNodes.clear(), /read-only/i);
  assert.equal(Reflect.set(index.nodes.get("project:alpha"), "kind", "Injected"), false);
  assert.equal(graph.nodes.find((item) => item.id === "project:alpha").kind, "Project");

  const expanded = expandNode(initialGraphState(index), "project:alpha", index);
  assert.equal(visibleGraph(expanded, index).nodes.some((item) => item.id === "technology:python"), true);
  assert.deepEqual(
    revealPath(initialGraphState(index), "artifact:alpha:report", index).revealedPath,
    ["focus:delivery", "project:alpha", "artifact:alpha:report"],
  );
});
