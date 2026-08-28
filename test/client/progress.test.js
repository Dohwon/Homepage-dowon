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
