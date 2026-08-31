const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function importGraphModule() {
  const absolutePath = path.join(__dirname, "../..", "client/graph-view.js");
  const source = await fs.readFile(absolutePath, "utf8");
  const encoded = Buffer.from(`${source}\n//# sourceURL=${pathToFileURL(absolutePath).href}`).toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

function fixtureGraph() {
  return {
    nodes: [
      { id: "focus:delivery", kind: "KnowledgeFocus", label: "Delivery", active: true, dimmed: false },
      { id: "domain:kg", kind: "KnowledgeDomain", label: "Knowledge Graph", active: true, dimmed: false },
      { id: "tag:routing", kind: "KnowledgeTag", label: "Routing Policy", active: true, dimmed: false, projectCount: 3 },
    ],
    links: [
      { id: "focus-domain", source: "focus:delivery", target: "domain:kg", kind: "FOCUS_HAS_TAG", dimmed: false },
      { id: "domain-tag", source: "domain:kg", target: "tag:routing", kind: "HAS_SUBTAG", dimmed: false },
    ],
  };
}

function expandedGraph() {
  const graph = fixtureGraph();
  graph.nodes.push({ id: "project:atlas", kind: "Project", label: "Project Atlas", active: true, dimmed: false });
  graph.links.push({ id: "tag-project", source: "project:atlas", target: "tag:routing", kind: "HAS_TAG", dimmed: false });
  return graph;
}

function container({ width = 960, height = 620 } = {}) {
  const listeners = new Map();
  const state = {
    html: "",
    replacements: 0,
    scrollCalls: 0,
    nodeScrollCalls: 0,
    scrollOptions: [],
    width,
    height,
  };
  const nodeElement = {
    getBoundingClientRect() { return { left: 542, top: 82, width: 208, height: 52 }; },
    scrollIntoView() { state.nodeScrollCalls += 1; },
  };
  return {
    state,
    dataset: {},
    clientWidth: width,
    clientHeight: height,
    scrollWidth: 1292,
    scrollHeight: 620,
    get innerHTML() { return state.html; },
    set innerHTML(value) { state.html = value; },
    getBoundingClientRect() { return { left: 0, top: 0, width, height }; },
    addEventListener(type, listener) { listeners.set(type, listener); },
    removeEventListener(type, listener) { if (listeners.get(type) === listener) listeners.delete(type); },
    replaceChildren() { state.replacements += 1; state.html = ""; },
    querySelector(selector) { return selector.includes("data-node-id") ? nodeElement : null; },
    scrollTo(options) { state.scrollCalls += 1; state.scrollOptions.push(options); },
    emit(type, event) { listeners.get(type)?.(event); },
    hasListener(type) { return listeners.has(type); },
  };
}

function nodeTarget(nodeId) {
  return {
    closest(selector) {
      if (!selector.includes("data-graph-node")) return null;
      return { dataset: { graphNode: nodeId } };
    },
  };
}

test("2D SVG renderer keeps focus, domain, and tag labels visible", async () => {
  const { createGraphView } = await importGraphModule();
  const element = container();
  const view = createGraphView(element, fixtureGraph());

  assert.match(element.state.html, /<svg[^>]+data-knowledge-graph/);
  assert.match(element.state.html, />Delivery</);
  assert.match(element.state.html, />Knowledge Graph</);
  assert.match(element.state.html, />Routing Policy</);
  assert.match(element.state.html, />3 projects</);
  assert.doesNotMatch(element.state.html, /canvas|#000000|ForceGraph3D/);
  assert.equal(element.hasListener("click"), true);
  assert.equal(element.hasListener("keydown"), true);
  view.destroy();
});

test("renderer escapes labels and updates the same container", async () => {
  const { createGraphView } = await importGraphModule();
  const element = container();
  const graph = fixtureGraph();
  graph.nodes[2].label = '<img src=x onerror="unsafe()">';
  const view = createGraphView(element, graph);

  assert.match(element.state.html, /&lt;img src=x onerror=&quot;unsafe\(\)&quot;&gt;/);
  assert.doesNotMatch(element.state.html, /<img/);
  view.update(expandedGraph());
  assert.match(element.state.html, />Project Atlas</);
  assert.equal(view.inspect().nodes.length, 4);
  view.destroy();
});

test("click and keyboard activation select nodes", async () => {
  const { createGraphView } = await importGraphModule();
  const selected = [];
  const element = container();
  const view = createGraphView(element, fixtureGraph(), { onSelect: node => selected.push(node.id) });

  element.emit("click", { target: nodeTarget("tag:routing") });
  element.emit("keydown", { key: "Enter", preventDefault() {}, target: nodeTarget("domain:kg") });
  element.emit("keydown", { key: " ", preventDefault() {}, target: nodeTarget("focus:delivery") });

  assert.deepEqual(selected, ["tag:routing", "domain:kg", "focus:delivery"]);
  view.destroy();
});

test("fit, focus, reset, motion, and inspection remain available to the route binder", async () => {
  const { createGraphView } = await importGraphModule();
  const element = container();
  const view = createGraphView(element, fixtureGraph(), { reducedMotion: false });

  assert.equal(view.focus({ id: "tag:routing" }), true);
  view.fit();
  view.setReducedMotion(true);
  view.reset();
  const snapshot = view.inspect();

  assert.equal(element.state.scrollCalls, 3);
  assert.equal(element.state.nodeScrollCalls, 0);
  assert.deepEqual(element.state.scrollOptions[0], { left: 166, top: 0, behavior: "smooth" });
  assert.equal(snapshot.reducedMotion, true);
  assert.equal(snapshot.layout, "layered-2d");
  assert.deepEqual(snapshot.visibleKinds, ["KnowledgeDomain", "KnowledgeFocus", "KnowledgeTag"]);
  assert.equal(snapshot.lastCommand.operation, "reset");
  view.destroy();
  assert.equal(element.hasListener("click"), false);
  assert.equal(element.hasListener("keydown"), false);
  assert.equal(element.state.replacements, 1);
});

test("runtime render failures close the view and request the list fallback", async () => {
  const { createGraphView } = await importGraphModule();
  const element = container();
  const failures = [];
  const view = createGraphView(element, fixtureGraph(), { onFailure: error => failures.push(error.message) });
  Object.defineProperty(element, "innerHTML", { set() { throw new Error("runtime render failed"); } });

  view.update(expandedGraph());

  assert.deepEqual(failures, ["runtime render failed"]);
  assert.equal(element.hasListener("click"), false);
  view.destroy();
});

test("SVG capability check fails closed without namespace element creation", async () => {
  const { supportsSvg } = await importGraphModule();
  const good = { createElementNS(namespace, name) { return { namespaceURI: namespace, nodeName: name }; } };

  assert.equal(supportsSvg(good), true);
  assert.equal(supportsSvg({}), false);
  assert.equal(supportsSvg({ createElementNS() { throw new Error("no DOM"); } }), false);
  assert.equal(supportsSvg(null), false);
});
