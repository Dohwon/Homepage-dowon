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
  return {
    state,
    style: {},
    getBoundingClientRect() {
      return { width: state.width, height: state.height };
    },
    replaceChildren() {
      state.replacements += 1;
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
  const chain = [
    "nodeId",
    "linkSource",
    "linkTarget",
    "nodeLabel",
    "nodeColor",
    "nodeOpacity",
    "linkOpacity",
    "onNodeClick",
    "onNodeDragEnd",
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
  instance.graphData = (value) => {
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

  return {
    calls,
    config,
    instance,
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

function fakeDocument({ webgl = false, throws = false } = {}) {
  return {
    createElement(name) {
      assert.equal(name, "canvas");
      return {
        getContext(type) {
          if (throws) throw new Error("context unavailable");
          return webgl && ["webgl2", "webgl", "experimental-webgl"].includes(type) ? {} : null;
        },
      };
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
    assert.equal(fake.config.nodeLabel(initial.nodes[0]), "Delivery · KnowledgeFocus");
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

test("force graph factory injection fails with a closed adapter error", async () => {
  const { createGraphView } = await importGraphModule();

  assert.throws(
    () => createGraphView(container(), fixtureGraph(), { forceGraphFactory: null, reducedMotion: false }),
    /force_graph_3d_unavailable/,
  );
});

test("WebGL capability check fails closed", async () => {
  const { supportsWebGL } = await importGraphModule();

  assert.equal(supportsWebGL(fakeDocument({ webgl: true })), true);
  assert.equal(supportsWebGL(fakeDocument({ webgl: false })), false);
  assert.equal(supportsWebGL(fakeDocument({ throws: true })), false);
  assert.equal(supportsWebGL(null), false);
});
