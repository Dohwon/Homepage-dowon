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
      { id: "project:atlas", kind: "Project", label: "Project Atlas", active: false, dimmed: true },
    ],
    links: [
      { id: "has-focus:atlas", source: "project:atlas", target: "focus:delivery", kind: "HAS_FOCUS", dimmed: true },
    ],
  };
}

function expandedGraph() {
  const graph = fixtureGraph();
  graph.nodes.push({ id: "domain:kg", kind: "KnowledgeDomain", label: "Knowledge Graph", active: true, dimmed: false });
  graph.links.push({ id: "domain:atlas", source: "project:atlas", target: "domain:kg", kind: "PROJECT_IN_DOMAIN", dimmed: false });
  return graph;
}

function container(width = 960, height = 620) {
  const state = { width, height, replacements: 0 };
  const listeners = new Map();
  return {
    state,
    style: {},
    getBoundingClientRect() {
      return { width: state.width, height: state.height };
    },
    replaceChildren() {
      state.replacements += 1;
    },
    addEventListener(type, listener, options) {
      listeners.set(type, { listener, options });
    },
    removeEventListener(type, listener, options) {
      const registered = listeners.get(type);
      if (registered?.listener === listener && registered.options === options) listeners.delete(type);
    },
    emit(type, event = {}) {
      listeners.get(type)?.listener(event);
    },
    hasListener(type) {
      return listeners.has(type);
    },
  };
}

function fakeForceGraph() {
  const calls = {
    graphData: [],
    width: [],
    height: [],
    cameraPosition: [],
    zoomToFit: [],
    pauseAnimation: 0,
    destructor: 0,
    d3AlphaDecay: [],
  };
  const config = {};
  let currentGraph = { nodes: [], links: [] };
  let camera = { x: 0, y: 0, z: 100 };
  const controlListeners = new Map();
  const controls = {
    target: { x: 0, y: 0, z: 0 },
    addEventListener(type, listener) {
      controlListeners.set(type, listener);
    },
    removeEventListener(type, listener) {
      if (controlListeners.get(type) === listener) controlListeners.delete(type);
    },
  };
  const chain = [
    "nodeId",
    "linkSource",
    "linkTarget",
    "nodeLabel",
    "nodeColor",
    "nodeOpacity",
    "linkOpacity",
    "onNodeClick",
    "onNodeDrag",
    "onNodeDragEnd",
    "onEngineStop",
    "cooldownTicks",
    "warmupTicks",
  ];
  const instance = {};
  for (const method of chain) {
    instance[method] = (value) => {
      config[method] = value;
      return instance;
    };
  }
  instance.graphData = function graphData(value) {
    if (arguments.length === 0) return currentGraph;
    currentGraph = value;
    calls.graphData.push(value);
    return instance;
  };
  instance.width = (value) => {
    calls.width.push(value);
    return instance;
  };
  instance.height = (value) => {
    calls.height.push(value);
    return instance;
  };
  instance.cameraPosition = (...args) => {
    if (args.length === 0) return { ...camera };
    camera = { ...camera, ...args[0] };
    calls.cameraPosition.push(args);
    return instance;
  };
  instance.zoomToFit = (...args) => {
    calls.zoomToFit.push(args);
    return instance;
  };
  instance.pauseAnimation = () => {
    calls.pauseAnimation += 1;
    return instance;
  };
  instance._destructor = () => {
    calls.destructor += 1;
  };
  instance.d3AlphaDecay = (value) => {
    calls.d3AlphaDecay.push(value);
    return instance;
  };
  instance.controls = () => controls;
  instance.graph2ScreenCoords = (x, y, z) => ({ x: x + 100, y: y + 50, z });

  return {
    calls,
    config,
    instance,
    controls,
    emitControlChange() {
      controlListeners.get("change")?.();
    },
    hasControlListener(type) {
      return controlListeners.has(type);
    },
    setCamera(value) {
      camera = { ...value };
    },
    factory(element, options) {
      config.element = element;
      config.options = options;
      config.sizeAtConstruction = { width: element.style.width, height: element.style.height };
      return instance;
    },
  };
}

function installResizeObserver() {
  const observers = [];
  const previous = globalThis.ResizeObserver;
  globalThis.ResizeObserver = class {
    constructor(callback) {
      this.callback = callback;
      this.observed = [];
      this.disconnectCalls = 0;
      observers.push(this);
    }

    observe(target) {
      this.observed.push(target);
    }

    disconnect() {
      this.disconnectCalls += 1;
    }
  };
  return {
    observers,
    restore() {
      if (previous === undefined) delete globalThis.ResizeObserver;
      else globalThis.ResizeObserver = previous;
    },
  };
}

function fakeDocument({ contexts = [], throws = false, missingGetContext = false } = {}) {
  return {
    createElement(name) {
      assert.equal(name, "canvas");
      if (missingGetContext) return {};
      return {
        getContext(type) {
          if (throws) throw new Error("context unavailable");
          return contexts.includes(type) ? {} : null;
        },
      };
    },
  };
}

function fakeLabelDocument() {
  return {
    createElement(name) {
      return { nodeName: String(name).toUpperCase(), textContent: "", children: [] };
    },
  };
}

test("3D adapter uses the injected orbit renderer and updates without recreation", async () => {
  const resize = installResizeObserver();
  try {
    const { createGraphView } = await importGraphModule();
    const fake = fakeForceGraph();
    const element = container();
    const selected = [];
    const initial = fixtureGraph();
    const view = createGraphView(element, initial, {
      forceGraphFactory: fake.factory,
      onSelect: node => selected.push(node.id),
      reducedMotion: false,
      documentRef: fakeLabelDocument(),
    });

    assert.strictEqual(fake.config.element, element);
    assert.deepEqual(fake.config.options, {
      controlType: "orbit",
      rendererConfig: { antialias: true, alpha: true },
    });
    assert.deepEqual(fake.config.sizeAtConstruction, { width: "960px", height: "620px" });
    assert.equal(fake.config.nodeId, "id");
    assert.equal(fake.config.linkSource, "source");
    assert.equal(fake.config.linkTarget, "target");
    assert.equal(fake.config.cooldownTicks, 80);
    assert.equal(fake.config.warmupTicks, 0);
    assert.equal(fake.calls.graphData.length, 1);
    assert.notStrictEqual(fake.calls.graphData[0].nodes[0], initial.nodes[0]);
    assert.notStrictEqual(fake.calls.graphData[0].links[0], initial.links[0]);
    assert.equal(fake.config.nodeLabel(initial.nodes[0]).textContent, "Delivery · KnowledgeFocus");
    assert.equal(fake.config.nodeLabel(initial.nodes[1]), "");
    assert.equal(fake.config.nodeOpacity({ dimmed: true }), 0.18);
    assert.equal(fake.config.linkOpacity({ dimmed: true }), 0.05);
    assert.notEqual(fake.config.nodeColor(initial.nodes[0]), fake.config.nodeColor(initial.nodes[1]));

    fake.config.onNodeClick(initial.nodes[0]);
    assert.deepEqual(selected, ["focus:delivery"]);
    const dragged = { x: 4, y: -2, z: 9 };
    fake.config.onNodeDragEnd(dragged);
    assert.deepEqual(dragged, { x: 4, y: -2, z: 9, fx: 4, fy: -2, fz: 9 });

    view.update(expandedGraph());
    assert.equal(fake.calls.graphData.length, 2);
    assert.equal(fake.calls.graphData[1].nodes.length, 3);

    assert.equal(resize.observers.length, 1);
    assert.deepEqual(resize.observers[0].observed, [element]);
    resize.observers[0].callback([{ target: element, contentRect: { width: 720.4, height: 480.6 } }]);
    assert.deepEqual(fake.calls.width, [720]);
    assert.deepEqual(fake.calls.height, [481]);
    assert.strictEqual(fake.config.element, element);

    const focused = { id: "project:atlas", x: 3, y: 4, z: 12 };
    view.focus(focused);
    assert.equal(fake.calls.cameraPosition.length, 1);
    assert.strictEqual(fake.calls.cameraPosition[0][1], focused);
    assert.equal(fake.calls.cameraPosition[0][2], 700);
    view.fit();
    assert.deepEqual(fake.calls.zoomToFit.at(-1), [500, 70]);
    view.reset();
    assert.equal(fake.calls.graphData.length, 3);
    assert.deepEqual(fake.calls.zoomToFit.at(-1), [0, 70]);

    view.destroy();
    assert.equal(resize.observers[0].disconnectCalls, 1);
    assert.equal(fake.calls.pauseAnimation, 1);
    assert.equal(fake.calls.destructor, 1);
    assert.equal(element.state.replacements, 1);
  } finally {
    resize.restore();
  }
});

test("reduced motion shortens simulation and removes camera animation", async () => {
  const resize = installResizeObserver();
  try {
    const { createGraphView } = await importGraphModule();
    const fake = fakeForceGraph();
    const view = createGraphView(container(), fixtureGraph(), {
      forceGraphFactory: fake.factory,
      reducedMotion: true,
    });

    assert.equal(fake.config.cooldownTicks, 18);
    assert.equal(fake.config.warmupTicks, 12);
    assert.deepEqual(fake.calls.d3AlphaDecay, [0.3]);
    view.focus({ x: 1, y: 2, z: 3 });
    assert.equal(fake.calls.cameraPosition[0][2], 0);
    view.fit();
    assert.deepEqual(fake.calls.zoomToFit.at(-1), [0, 70]);
    view.destroy();
  } finally {
    resize.restore();
  }
});

test("node labels use textContent instead of an HTML-capable string", async () => {
  const resize = installResizeObserver();
  try {
    const { createGraphView } = await importGraphModule();
    const fake = fakeForceGraph();
    const view = createGraphView(container(), fixtureGraph(), {
      forceGraphFactory: fake.factory,
      documentRef: fakeLabelDocument(),
      reducedMotion: false,
    });
    const unsafeLabel = '<img src=x onerror="globalThis.pwned=true">';
    const tooltip = fake.config.nodeLabel({
      id: "project:unsafe",
      kind: "Project",
      label: unsafeLabel,
      active: true,
    });

    assert.equal(typeof tooltip, "object");
    assert.equal(tooltip.nodeName, "SPAN");
    assert.equal(tooltip.textContent, `${unsafeLabel} · Project`);
    assert.deepEqual(tooltip.children, []);
    view.destroy();
  } finally {
    resize.restore();
  }
});

test("live reduced motion updates disable subsequent focus and Fit animation", async () => {
  const resize = installResizeObserver();
  try {
    const { createGraphView } = await importGraphModule();
    const fake = fakeForceGraph();
    const view = createGraphView(container(), fixtureGraph(), {
      forceGraphFactory: fake.factory,
      reducedMotion: false,
    });

    view.setReducedMotion(true);
    view.focus({ x: 1, y: 2, z: 3 });
    view.fit();

    assert.equal(fake.config.cooldownTicks, 18);
    assert.equal(fake.config.warmupTicks, 12);
    assert.deepEqual(fake.calls.d3AlphaDecay, [0.3]);
    assert.equal(fake.calls.cameraPosition.at(-1)[2], 0);
    assert.deepEqual(fake.calls.zoomToFit.at(-1), [0, 70]);
    view.destroy();
  } finally {
    resize.restore();
  }
});

test("inspection snapshot exposes settled camera, control, drag, and motion command state", async () => {
  const resize = installResizeObserver();
  try {
    const { createGraphView } = await importGraphModule();
    const fake = fakeForceGraph();
    const view = createGraphView(container(), fixtureGraph(), {
      forceGraphFactory: fake.factory,
      reducedMotion: false,
    });

    fake.config.onEngineStop();
    fake.setCamera({ x: 4, y: 5, z: 110 });
    fake.controls.target = { x: 1, y: 2, z: 3 };
    fake.emitControlChange();
    const rendererNode = fake.instance.graphData().nodes.find(node => node.id === "project:atlas");
    Object.assign(rendererNode, { x: 10, y: 20, z: 30 });
    fake.config.onNodeDrag(rendererNode);
    Object.assign(rendererNode, { x: 14, y: 26, z: 34 });
    fake.config.onNodeDragEnd(rendererNode);
    fake.config.onEngineStop();

    const active = view.inspect();
    assert.equal(active.engineSettled, true);
    assert.equal(active.reducedMotion, false);
    assert.deepEqual(active.camera, { x: 4, y: 5, z: 110 });
    assert.deepEqual(active.target, { x: 1, y: 2, z: 3 });
    assert.equal(active.controlRevision, 1);
    assert.deepEqual(active.lastDrag, {
      id: "project:atlas",
      from: { x: 10, y: 20, z: 30 },
      to: { x: 14, y: 26, z: 34 },
      pinned: true,
      revision: 1,
    });
    assert.equal(active.lastCameraCommand, null);
    assert.deepEqual(active.nodes.find(node => node.id === "project:atlas"), {
      id: "project:atlas",
      kind: "Project",
      position: { x: 14, y: 26, z: 34 },
      screen: { x: 114, y: 76 },
      pinned: true,
    });

    view.focus(rendererNode);
    assert.deepEqual(view.inspect().lastCameraCommand, {
      operation: "focus",
      duration: 700,
      revision: 1,
    });

    view.setReducedMotion(true);
    view.fit();
    const reduced = view.inspect();
    assert.equal(reduced.reducedMotion, true);
    assert.deepEqual(reduced.lastCameraCommand, { operation: "fit", duration: 0, revision: 2 });

    view.update(expandedGraph());
    assert.equal(view.inspect().engineSettled, false);
    view.destroy();
    assert.equal(fake.hasControlListener("change"), false);
  } finally {
    resize.restore();
  }
});

test("force graph factory injection fails with a closed adapter error", async () => {
  const { createGraphView } = await importGraphModule();

  assert.throws(
    () => createGraphView(container(), fixtureGraph(), { forceGraphFactory: null, reducedMotion: false }),
    /force_graph_3d_unavailable/,
  );
});

test("partial renderer construction tears down the allocated instance", async () => {
  const { createGraphView } = await importGraphModule();
  const fake = fakeForceGraph();
  const element = container();
  fake.instance.linkTarget = () => { throw new Error("configuration failed"); };

  assert.throws(
    () => createGraphView(element, fixtureGraph(), { forceGraphFactory: fake.factory }),
    /configuration failed/,
  );
  assert.equal(fake.calls.pauseAnimation, 1);
  assert.equal(fake.calls.destructor, 1);
  assert.equal(element.state.replacements, 1);
  assert.equal(element.hasListener("webglcontextlost"), false);
});

test("runtime update failure tears down once and requests accessible fallback", async () => {
  const resize = installResizeObserver();
  try {
    const { createGraphView } = await importGraphModule();
    const fake = fakeForceGraph();
    const element = container();
    const failures = [];
    const view = createGraphView(element, fixtureGraph(), {
      forceGraphFactory: fake.factory,
      onFailure: error => failures.push(error.message),
    });
    fake.instance.graphData = () => { throw new Error("runtime graph update failed"); };

    view.update(expandedGraph());

    assert.deepEqual(failures, ["runtime graph update failed"]);
    assert.equal(fake.calls.pauseAnimation, 1);
    assert.equal(fake.calls.destructor, 1);
    assert.equal(resize.observers[0].disconnectCalls, 1);
    assert.equal(fake.hasControlListener("change"), false);
    assert.equal(element.hasListener("webglcontextlost"), false);
    view.destroy();
    assert.equal(fake.calls.destructor, 1);
  } finally {
    resize.restore();
  }
});

test("WebGL context loss prevents default and cleans every renderer listener", async () => {
  const resize = installResizeObserver();
  try {
    const { createGraphView } = await importGraphModule();
    const fake = fakeForceGraph();
    const element = container();
    const failures = [];
    let prevented = 0;
    createGraphView(element, fixtureGraph(), {
      forceGraphFactory: fake.factory,
      onFailure: error => failures.push(error.message),
    });

    assert.equal(element.hasListener("webglcontextlost"), true);
    element.emit("webglcontextlost", { preventDefault() { prevented += 1; } });

    assert.equal(prevented, 1);
    assert.deepEqual(failures, ["webgl_context_lost"]);
    assert.equal(fake.calls.destructor, 1);
    assert.equal(fake.hasControlListener("change"), false);
    assert.equal(element.hasListener("webglcontextlost"), false);
  } finally {
    resize.restore();
  }
});

test("WebGL capability check fails closed", async () => {
  const { supportsWebGL } = await importGraphModule();

  assert.equal(supportsWebGL(fakeDocument({ contexts: ["webgl2"] })), true);
  assert.equal(supportsWebGL(fakeDocument({ contexts: ["webgl", "experimental-webgl"] })), false);
  assert.equal(supportsWebGL(fakeDocument()), false);
  assert.equal(supportsWebGL({}), false);
  assert.equal(supportsWebGL(fakeDocument({ missingGetContext: true })), false);
  assert.equal(supportsWebGL(fakeDocument({ throws: true })), false);
  assert.equal(supportsWebGL(null), false);
});
