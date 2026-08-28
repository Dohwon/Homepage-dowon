const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function importBrowserModule(t, relativePath) {
  const absolutePath = path.join(__dirname, "../..", relativePath);
  const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "atlas-markdown-"));
  t.after(() => fs.rm(tempRoot, { recursive: true, force: true }));
  const clientRoot = path.join(tempRoot, "client");
  await fs.mkdir(clientRoot, { recursive: true });

  const files = ["public-url.js", "markdown.js"];
  for (const fileName of files) {
    const sourcePath = path.join(path.dirname(absolutePath), fileName);
    let source = await fs.readFile(sourcePath, "utf8");
    if (fileName === "markdown.js") {
      source = source.replace('./public-url.js', "./public-url.mjs");
    }
    await fs.writeFile(path.join(clientRoot, fileName.replace(/\.js$/, ".mjs")), source, "utf8");
  }

  return import(pathToFileURL(path.join(clientRoot, path.basename(relativePath).replace(/\.js$/, ".mjs"))).href);
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
  const { renderMarkdown } = await importBrowserModule(t, "client/markdown.js");

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
  const { renderMarkdown } = await importBrowserModule(t, "client/markdown.js");

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
  const { renderMarkdown } = await importBrowserModule(t, "client/markdown.js");

  assert.equal(renderMarkdown(null), "");
  assert.equal(receivedSource, "");
  assert.equal(renderMarkdown(0), "");
  assert.equal(receivedSource, "0");
});

test("markdown rendering keeps safe public links after DOMPurify sanitization", async t => {
  const restore = preserveGlobals();
  t.after(restore);
  globalThis.marked = {
    parse() {
      return '<p><a href="https://example.com/doc">good</a><a href="/projects/beta">relative</a><a href="#routing">fragment</a></p>';
    }
  };
  globalThis.DOMPurify = {
    sanitize(html) { return html; }
  };
  const { renderMarkdown } = await importBrowserModule(t, "client/markdown.js");

  const result = renderMarkdown("[good](https://example.com/doc)");

  assert.match(result, /https:\/\/example\.com\/doc/);
  assert.match(result, /href="\/projects\/beta"/);
  assert.match(result, /href="#routing"/);
});

test("svg sanitization uses an independent strict svg policy", async t => {
  const restore = preserveGlobals();
  t.after(restore);
  let receivedOptions;
  globalThis.marked = { parse: () => "" };
  globalThis.DOMPurify = {
    sanitize(svg, options) {
      receivedOptions = options;
      return svg
        .replace(/<script[\s\S]*?<\/script>/g, "")
        .replace(/<foreignObject[\s\S]*?<\/foreignObject>/g, "")
        .replace(/\s(?:onload|onclick|onerror|href|xlink:href)="[^"]*"/g, "");
    }
  };
  const { sanitizeSvg } = await importBrowserModule(t, "client/markdown.js");

  const result = sanitizeSvg('<svg xmlns="http://www.w3.org/2000/svg" onload="unsafe()"><script>bad()</script><foreignObject>bad</foreignObject><g href="https://evil.example/track"><path d="M0 0h1" /></g></svg>');

  assert.match(result, /<svg/);
  assert.doesNotMatch(result, /script|foreignObject|onload|href=/);
  assert.deepEqual(receivedOptions.USE_PROFILES, { svg: true, svgFilters: true });
  assert.deepEqual(receivedOptions.FORBID_TAGS, ["script", "foreignObject", "iframe", "object", "embed"]);
  assert.deepEqual(receivedOptions.FORBID_ATTR, ["style", "onload", "onclick", "onerror", "href", "xlink:href"]);
});
