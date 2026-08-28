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

function preserveGlobals() {
  const windowValue = globalThis.window;
  const requestFrame = globalThis.requestAnimationFrame;
  const cancelFrame = globalThis.cancelAnimationFrame;
  return () => {
    if (windowValue === undefined) delete globalThis.window;
    else globalThis.window = windowValue;
    if (requestFrame === undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame = requestFrame;
    if (cancelFrame === undefined) delete globalThis.cancelAnimationFrame;
    else globalThis.cancelAnimationFrame = cancelFrame;
  };
}

function installBrowserGlobals(t, { scrollY = 0, innerHeight = 800 } = {}) {
  const restore = preserveGlobals();
  const listeners = {
    scroll: new Set(),
    resize: new Set()
  };
  const options = [];
  const pendingFrames = new Map();
  const canceledFrames = [];
  let nextFrameId = 1;
  const windowObject = {
    scrollY,
    innerHeight,
    addEventListener(type, listener, listenerOptions) {
      listeners[type]?.add(listener);
      options.push({ type, listenerOptions });
    },
    removeEventListener(type, listener) {
      listeners[type]?.delete(listener);
    }
  };
  globalThis.window = windowObject;
  globalThis.requestAnimationFrame = (callback) => {
    const id = nextFrameId++;
    pendingFrames.set(id, callback);
    return id;
  };
  globalThis.cancelAnimationFrame = (id) => {
    canceledFrames.push(id);
    pendingFrames.delete(id);
  };
  t.after(restore);
  return {
    windowObject,
    listeners,
    options,
    pendingFrames,
    canceledFrames,
    flushFrame(id) {
      const callback = pendingFrames.get(id);
      assert.ok(callback, `missing animation frame ${id}`);
      pendingFrames.delete(id);
      callback();
    }
  };
}

function createProgressElement() {
  const attributes = new Map();
  return {
    style: { transform: "scaleX(1)" },
    setAttribute(name, value = "") {
      attributes.set(name, String(value));
    },
    removeAttribute(name) {
      attributes.delete(name);
    },
    hasAttribute(name) {
      return attributes.has(name);
    }
  };
}

function createRootWithReader(article) {
  const selectors = [];
  return {
    selectors,
    querySelector(selector) {
      selectors.push(selector);
      return selector === "[data-project-reader]" ? article : null;
    }
  };
}

function createBindingSpy() {
  const calls = [];
  return {
    calls,
    bind(element, article) {
      const call = { element, article, disposed: false };
      calls.push(call);
      return () => {
        call.disposed = true;
      };
    }
  };
}

test("article progress ignores content before and after the reader", async () => {
  const { articleProgress } = await importBrowserModule("client/progress.js");
  const article = { offsetTop: 600, offsetHeight: 1600 };

  assert.equal(articleProgress(article, 0, 800), 0);
  assert.equal(articleProgress(article, 600, 800), 0);
  assert.equal(articleProgress(article, 1000, 800), 0.5);
  assert.equal(articleProgress(article, 1400, 800), 1);
});

test("short articles complete without division by zero", async () => {
  const { articleProgress } = await importBrowserModule("client/progress.js");

  assert.equal(articleProgress({ offsetTop: 100, offsetHeight: 400 }, 99, 800), 0);
  assert.equal(articleProgress({ offsetTop: 100, offsetHeight: 400 }, 100, 800), 1);
});

test("article progress normalizes non-finite inputs into a finite clamped ratio", async () => {
  const { articleProgress } = await importBrowserModule("client/progress.js");
  const cases = [
    [{ offsetTop: Infinity, offsetHeight: 1600 }, Infinity, 800, 0],
    [{ offsetTop: 100, offsetHeight: Infinity }, 100, 800, 1],
    [{ offsetTop: 100, offsetHeight: 1600 }, NaN, NaN, 0],
    [{ offsetTop: -Infinity, offsetHeight: 1600 }, 1200, 800, 1],
    [{ offsetTop: 100, offsetHeight: NaN }, -Infinity, 800, 0]
  ];

  for (const [article, viewportTop, viewportHeight, expected] of cases) {
    const ratio = articleProgress(article, viewportTop, viewportHeight);
    assert.equal(ratio, expected);
    assert.equal(Number.isFinite(ratio), true);
    assert.ok(ratio >= 0 && ratio <= 1, `ratio ${ratio} should stay clamped`);
  }
});

test("missing reader content resets and hides the progress bar without listeners", async t => {
  const browser = installBrowserGlobals(t);
  const { bindReadingProgress } = await importBrowserModule("client/progress.js");
  const element = createProgressElement();

  const dispose = bindReadingProgress(element, null);

  assert.equal(typeof dispose, "function");
  assert.equal(element.style.transform, "scaleX(0)");
  assert.equal(element.hasAttribute("data-active"), false);
  assert.equal(browser.listeners.scroll.size, 0);
  assert.equal(browser.listeners.resize.size, 0);
});

test("reader binding updates article-relative progress and cleans listeners and frames", async t => {
  const browser = installBrowserGlobals(t, { scrollY: 1000, innerHeight: 800 });
  const { bindReadingProgress } = await importBrowserModule("client/progress.js");
  const element = createProgressElement();
  const article = { offsetTop: 600, offsetHeight: 1600 };

  const dispose = bindReadingProgress(element, article);

  assert.equal(element.hasAttribute("data-active"), true);
  assert.equal(element.style.transform, "scaleX(0.5)");
  assert.equal(browser.listeners.scroll.size, 1);
  assert.equal(browser.listeners.resize.size, 1);
  assert.deepEqual(browser.options, [
    { type: "scroll", listenerOptions: { passive: true } },
    { type: "resize", listenerOptions: undefined }
  ]);

  const scrollListener = [...browser.listeners.scroll][0];
  browser.windowObject.scrollY = 1200;
  scrollListener();
  scrollListener();
  assert.equal(browser.pendingFrames.size, 1);

  const scheduledFrameId = [...browser.pendingFrames.keys()][0];
  browser.flushFrame(scheduledFrameId);
  assert.equal(element.style.transform, "scaleX(0.75)");

  const resizeListener = [...browser.listeners.resize][0];
  browser.windowObject.scrollY = 1400;
  resizeListener();
  assert.equal(browser.pendingFrames.size, 1);
  const pendingCleanupFrameId = [...browser.pendingFrames.keys()][0];

  dispose();

  assert.equal(browser.listeners.scroll.size, 0);
  assert.equal(browser.listeners.resize.size, 0);
  assert.deepEqual(browser.canceledFrames, [pendingCleanupFrameId]);
  assert.equal(browser.pendingFrames.size, 0);
});

test("progress lifecycle commits only Decisions readers", async () => {
  const { createProgressLifecycle } = await importBrowserModule("client/progress.js");
  const element = createProgressElement();
  const article = { id: "reader" };
  const root = createRootWithReader(article);
  const spy = createBindingSpy();
  const lifecycle = createProgressLifecycle(element, { bind: spy.bind });

  lifecycle.begin(11);
  const committed = lifecycle.commit(11, { view: "project", tab: "decisions" }, root);

  assert.equal(committed, true);
  assert.equal(spy.calls.length, 1);
  assert.equal(spy.calls[0].article, article);
  assert.deepEqual(root.selectors, ["[data-project-reader]"]);
});

test("progress lifecycle resets non-Decisions and non-project routes without reader lookup", async () => {
  const { createProgressLifecycle } = await importBrowserModule("client/progress.js");
  const element = createProgressElement();
  const root = createRootWithReader({ id: "reader" });
  const spy = createBindingSpy();
  const lifecycle = createProgressLifecycle(element, { bind: spy.bind });

  lifecycle.begin(21);
  lifecycle.commit(21, { view: "project", tab: "build-timeline" }, root);
  lifecycle.begin(22);
  lifecycle.commit(22, { view: "home" }, root);

  assert.equal(spy.calls.length, 2);
  assert.equal(spy.calls[0].article, null);
  assert.equal(spy.calls[1].article, null);
  assert.equal(element.style.transform, "scaleX(0)");
  assert.equal(element.hasAttribute("data-active"), false);
  assert.deepEqual(root.selectors, []);
});

test("progress lifecycle resets after a reader was active and keeps the bar hidden on error", async () => {
  const { createProgressLifecycle } = await importBrowserModule("client/progress.js");
  const element = createProgressElement();
  const root = createRootWithReader({ id: "reader" });
  const spy = createBindingSpy();
  const lifecycle = createProgressLifecycle(element, { bind: spy.bind });

  lifecycle.begin(31);
  lifecycle.commit(31, { view: "project", tab: "decisions" }, root);
  lifecycle.begin(32);
  const reset = lifecycle.reset(32);

  assert.equal(reset, true);
  assert.equal(spy.calls.length, 1);
  assert.equal(spy.calls[0].disposed, true);
  assert.equal(element.style.transform, "scaleX(0)");
  assert.equal(element.hasAttribute("data-active"), false);
});

test("progress lifecycle cancels pending frames and listeners as soon as a new navigation begins", async t => {
  const browser = installBrowserGlobals(t, { scrollY: 1000, innerHeight: 800 });
  const { bindReadingProgress, createProgressLifecycle } = await importBrowserModule("client/progress.js");
  const element = createProgressElement();
  const article = { offsetTop: 600, offsetHeight: 1600 };
  const root = createRootWithReader(article);
  const lifecycle = createProgressLifecycle(element, { bind: bindReadingProgress });

  lifecycle.begin(41);
  lifecycle.commit(41, { view: "project", tab: "decisions" }, root);

  const scrollListener = [...browser.listeners.scroll][0];
  scrollListener();
  assert.equal(browser.pendingFrames.size, 1);
  const pendingCleanupFrameId = [...browser.pendingFrames.keys()][0];

  lifecycle.begin(42);

  assert.equal(browser.listeners.scroll.size, 0);
  assert.equal(browser.listeners.resize.size, 0);
  assert.deepEqual(browser.canceledFrames, [pendingCleanupFrameId]);
  assert.equal(browser.pendingFrames.size, 0);
  assert.equal(element.style.transform, "scaleX(0)");
  assert.equal(element.hasAttribute("data-active"), false);
});

test("stale lifecycle tokens cannot replace or reset the current binding", async () => {
  const { createProgressLifecycle } = await importBrowserModule("client/progress.js");
  const element = createProgressElement();
  const firstRoot = createRootWithReader({ id: "reader-1" });
  const secondRoot = createRootWithReader({ id: "reader-2" });
  const spy = createBindingSpy();
  const lifecycle = createProgressLifecycle(element, { bind: spy.bind });

  lifecycle.begin(51);
  lifecycle.commit(51, { view: "project", tab: "decisions" }, firstRoot);
  lifecycle.begin(52);
  lifecycle.commit(52, { view: "project", tab: "decisions" }, secondRoot);

  const staleCommit = lifecycle.commit(51, { view: "project", tab: "decisions" }, firstRoot);
  const staleReset = lifecycle.reset(51);

  assert.equal(staleCommit, false);
  assert.equal(staleReset, false);
  assert.equal(spy.calls.length, 2);
  assert.equal(spy.calls[0].disposed, true);
  assert.equal(spy.calls[1].disposed, false);
  assert.equal(spy.calls[1].article.id, "reader-2");
});
