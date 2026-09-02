const test = require("node:test");
const assert = require("node:assert/strict");
const fsp = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function importRenderModule(t) {
  const tempRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-render-captures-"));
  t.after(() => fsp.rm(tempRoot, { recursive: true, force: true }));
  const clientRoot = path.join(tempRoot, "client");
  await fsp.mkdir(clientRoot, { recursive: true });
  for (const fileName of ["router.js", "public-url.js", "markdown.js", "graph-state.js", "graph-view.js", "project-pins.js", "render.js"]) {
    let source = await fsp.readFile(path.join(__dirname, "../..", "client", fileName), "utf8");
    if (fileName === "render.js") {
      source = source
        .replaceAll("./router.js", "./router.mjs")
        .replaceAll("./markdown.js", "./markdown.mjs")
        .replaceAll("./public-url.js", "./public-url.mjs")
        .replaceAll("./graph-state.js", "./graph-state.mjs")
        .replaceAll("./graph-view.js", "./graph-view.mjs")
        .replaceAll("./project-pins.js", "./project-pins.mjs");
    }
    if (fileName === "markdown.js") source = source.replaceAll("./public-url.js", "./public-url.mjs");
    await fsp.writeFile(path.join(clientRoot, fileName.replace(".js", ".mjs")), source, "utf8");
  }
  return import(pathToFileURL(path.join(clientRoot, "render.mjs")).href);
}

function projectWithCapture() {
  return {
    id: "alpha",
    captures: [{ id: "home", src: "/api/atlas/projects/alpha/captures/home", alt: "Alpha home", caption: "Home screen", role: "overview" }],
    article: {
      readiness: "ready",
      summary: "A public project.",
      sections: [{ id: "decision", title: "Decision", section_type: "decision", body: "A decision." }]
    }
  };
}

function projectWithExplicitlyEmptyCaptures() {
  return {
    id: "chat-friends",
    captures: [],
    cover: { src: "/legacy-cover.png", alt: "Legacy cover", caption: "Legacy screen" },
    article: {
      readiness: "ready",
      summary: "A project without a verified fresh capture.",
      sections: [{ id: "decision", title: "Decision", section_type: "decision", body: "A decision." }]
    }
  };
}

function installSanitizers(t) {
  const previousMarked = globalThis.marked;
  const previousPurifier = globalThis.DOMPurify;
  t.after(() => {
    if (previousMarked === undefined) delete globalThis.marked;
    else globalThis.marked = previousMarked;
    if (previousPurifier === undefined) delete globalThis.DOMPurify;
    else globalThis.DOMPurify = previousPurifier;
  });
  globalThis.marked = { parse: source => `<p>${String(source ?? "")}</p>` };
  globalThis.DOMPurify = { sanitize: source => String(source ?? "") };
}

test("renders captures below decisions content only", async (t) => {
  installSanitizers(t);
  const { renderProjectContent } = await importRenderModule(t);
  const result = renderProjectContent(projectWithCapture(), "decisions");

  assert.match(result.html, /data-project-captures/);
  assert.ok(result.html.indexOf("data-project-captures") > result.html.indexOf('data-project-reader'));
  assert.deepEqual(result.headings.at(-1), { id: "project-captures", label: "구현 화면" });
});

test("does not render a capture section for other project tabs", async (t) => {
  const { renderProjectContent } = await importRenderModule(t);
  const result = renderProjectContent(projectWithCapture(), "system-map");

  assert.doesNotMatch(result.html, /data-project-captures/);
});

test("does not fall back to a legacy cover when captures are explicitly empty", async (t) => {
  installSanitizers(t);
  const { renderProjectCaptures } = await importRenderModule(t);

  assert.equal(renderProjectCaptures(projectWithExplicitlyEmptyCaptures()), "");
});
