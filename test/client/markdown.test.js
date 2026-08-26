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
  const marked = globalThis.marked;
  const DOMPurify = globalThis.DOMPurify;
  return () => {
    if (marked === undefined) delete globalThis.marked;
    else globalThis.marked = marked;
    if (DOMPurify === undefined) delete globalThis.DOMPurify;
    else globalThis.DOMPurify = DOMPurify;
  };
}

test("markdown output always passes through the strict DOMPurify boundary", async t => {
  const restore = preserveGlobals();
  t.after(restore);
  let receivedSource;
  let receivedHtml;
  let receivedOptions;
  globalThis.marked = {
    parse(source, options) {
      receivedSource = source;
      assert.deepEqual(options, { gfm: true, breaks: false });
      return `<h2>${source}</h2><script data-injected>unsafe()</script>`;
    }
  };
  globalThis.DOMPurify = {
    sanitize(html, options) {
      receivedHtml = html;
      receivedOptions = options;
      return html.replace(/<script[\s\S]*?<\/script>/g, "");
    }
  };
  const { renderMarkdown } = await importBrowserModule("client/markdown.js");

  const result = renderMarkdown("Constraint");

  assert.equal(receivedSource, "Constraint");
  assert.match(receivedHtml, /data-injected/);
  assert.equal(result, "<h2>Constraint</h2>");
  assert.deepEqual(receivedOptions.USE_PROFILES, { html: true });
  assert.deepEqual(receivedOptions.FORBID_TAGS, ["script", "style", "iframe", "object", "embed"]);
  assert.deepEqual(receivedOptions.FORBID_ATTR, ["style", "onerror", "onclick"]);
});

test("markdown rendering fails closed when a browser dependency is unavailable", async t => {
  const restore = preserveGlobals();
  t.after(restore);
  delete globalThis.marked;
  delete globalThis.DOMPurify;
  const { renderMarkdown } = await importBrowserModule("client/markdown.js");

  assert.throws(() => renderMarkdown("<script>unsafe()</script>"), /markdown_renderer_unavailable/);
});

test("markdown rendering coerces missing content to an empty string", async t => {
  const restore = preserveGlobals();
  t.after(restore);
  let receivedSource = "not-called";
  globalThis.marked = {
    parse(source) {
      receivedSource = source;
      return "";
    }
  };
  globalThis.DOMPurify = { sanitize: html => html };
  const { renderMarkdown } = await importBrowserModule("client/markdown.js");

  assert.equal(renderMarkdown(null), "");
  assert.equal(receivedSource, "");
  assert.equal(renderMarkdown(0), "");
  assert.equal(receivedSource, "0");
});
