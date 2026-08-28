const test = require("node:test");
const assert = require("node:assert/strict");
const fsp = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const WORKTREE_ROOT = path.join(__dirname, "../..");
const SAFE_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1" /></svg>';

async function importRenderModule(t) {
  const tempRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-render-"));
  t.after(() => fsp.rm(tempRoot, { recursive: true, force: true }));
  const clientRoot = path.join(tempRoot, "client");
  await fsp.mkdir(clientRoot, { recursive: true });

  const files = ["router.js", "markdown.js", "graph-view.js", "render.js"];
  for (const fileName of files) {
    const sourcePath = path.join(WORKTREE_ROOT, "client", fileName);
    let source = await fsp.readFile(sourcePath, "utf8");
    if (fileName === "render.js") {
      source = source
        .replace('./router.js', "./router.mjs")
        .replace('./markdown.js', "./markdown.mjs")
        .replace('./graph-view.js', "./graph-view.mjs");
    }
    await fsp.writeFile(path.join(clientRoot, fileName.replace(/\.js$/, ".mjs")), source, "utf8");
  }

  return import(pathToFileURL(path.join(clientRoot, "render.mjs")).href);
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

function installSanitizers(t) {
  const restore = preserveGlobals();
  t.after(restore);
  globalThis.marked = {
    parse(source) {
      const escaped = String(source ?? "").replace(/[&<>]/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;"
      }[character]));
      return `<p>${escaped}</p><script>unsafe()</script>`;
    }
  };
  globalThis.DOMPurify = {
    sanitize(source, options) {
      if (options?.USE_PROFILES?.svg) {
        return String(source)
          .replace(/<script[\s\S]*?<\/script>/gi, "")
          .replace(/<foreignObject[\s\S]*?<\/foreignObject>/gi, "")
          .replace(/\s(?:onload|onclick|onerror|href|xlink:href)="[^"]*"/gi, "");
      }
      return String(source)
        .replace(/<script[\s\S]*?<\/script>/gi, "")
        .replace(/href="(?:javascript:[^"]*|https?:\/\/(?:10|127|169\.254|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.[^"]*)"/gi, "");
    }
  };
}

function fixtureProject(overrides = {}) {
  return {
    id: "alpha",
    name: "Alpha Project",
    lifecycle: "active",
    summary: "Structured decision reader",
    tags: {
      domain: ["Knowledge Systems"],
      problem: ["Fragmented context"],
      pattern: ["Public decision log"],
      technology: ["Node.js"],
      outcome: ["Decision reader"]
    },
    article: {
      project_id: "alpha",
      title: "Alpha decisions",
      summary: "Public decision summary",
      readiness: "ready",
      prior_context: "이전 단계 요약",
      sections: [],
      decision_index: []
    },
    visuals: {},
    systemMap: undefined,
    timeline: [],
    evidence: [],
    ...overrides
  };
}

test("renders every article section in order and places figures after prose", async (t) => {
  installSanitizers(t);
  const { renderProjectContent } = await importRenderModule(t);
  const project = fixtureProject({
    article: {
      project_id: "alpha",
      title: "Alpha decisions",
      summary: "Public decision summary",
      readiness: "ready",
      prior_context: "이전 단계 요약",
      sections: [
        {
          id: "retention",
          title: "TMAP 데이터 장기 저장 제한 해결",
          section_type: "decision",
          body: "TMAP 데이터는 세션 입력으로만 사용한다.",
          evidence_ids: ["ev-1"],
          diagrams: [{ id: "lifecycle", caption: "두 데이터의 저장 수명", alt: "TMAP과 VWorld 저장 수명 비교" }]
        },
        {
          id: "validation",
          title: "검증 범위 확정",
          section_type: "validation",
          body: "테스트는 공개 contract와 렌더 경계에 집중한다.",
          evidence_ids: ["ev-2"]
        }
      ],
      decision_index: [{ decision_id: "retention-decision", section_id: "retention", status: "adopted", evidence_ids: ["ev-1"] }]
    },
    visuals: { lifecycle: SAFE_SVG }
  });

  const result = renderProjectContent(project, "decisions");

  assert.match(result.html, /data-project-reader/);
  assert.match(result.html, /data-article-section="prior-context"/);
  assert.match(result.html, /data-article-section="retention"/);
  assert.match(result.html, /data-article-section="validation"/);
  assert.ok(result.html.indexOf('data-article-section="retention"') < result.html.indexOf('data-article-section="validation"'));
  assert.ok(result.html.indexOf("세션 입력") < result.html.indexOf("data-article-figure"));
  assert.match(result.html, /<figcaption>두 데이터의 저장 수명<\/figcaption>/);
  assert.deepEqual(result.headings, [
    { id: "prior-context", label: "이전 단계" },
    { id: "retention", label: "TMAP 데이터 장기 저장 제한 해결" },
    { id: "validation", label: "검증 범위 확정" }
  ]);
});

test("insufficient and review-required articles render factual empty states without legacy filler", async (t) => {
  installSanitizers(t);
  const { renderProjectContent } = await importRenderModule(t);

  const insufficient = renderProjectContent(
    fixtureProject({ article: { project_id: "alpha", title: "Alpha decisions", summary: "Summary", readiness: "insufficient-evidence", sections: [] } }),
    "decisions"
  );
  const review = renderProjectContent(
    fixtureProject({ article: { project_id: "alpha", title: "Alpha decisions", summary: "Summary", readiness: "review-required", sections: [] } }),
    "decisions"
  );

  assert.match(insufficient.html, /확인 가능한 공개 근거가 부족합니다/);
  assert.doesNotMatch(insufficient.html, /Overview|Rollbacks|Visual Map|Artifacts|문제 해결 지도/);
  assert.match(review.html, /공개 전 검토가 필요합니다/);
  assert.equal(review.headings.length, 0);
});

test("system map sanitizes svg independently and omits unsafe markup", async (t) => {
  installSanitizers(t);
  const { renderProjectContent } = await importRenderModule(t);
  const project = fixtureProject({
    systemMap: '<svg xmlns="http://www.w3.org/2000/svg" onload="unsafe()"><script>alert(1)</script><foreignObject>unsafe</foreignObject><g><path d="M0 0h1" /></g></svg>'
  });

  const result = renderProjectContent(project, "system-map");

  assert.match(result.html, /data-system-map/);
  assert.match(result.html, /<svg/);
  assert.doesNotMatch(result.html, /script|foreignObject|onload/);
  assert.equal(result.headings.length, 0);
});

test("timeline stays in stable date order without manufacturing missing dates", async (t) => {
  installSanitizers(t);
  const { renderProjectContent } = await importRenderModule(t);
  const project = fixtureProject({
    timeline: [
      { event_id: "late", date: "2026-08-26", title: "Late", context: "", decision: "", outcome: "", stage: "validation" },
      { event_id: "same-a", date: "2026-08-25", title: "Same A", context: "", decision: "", outcome: "", stage: "decision" },
      { event_id: "same-b", date: "2026-08-25", title: "Same B", context: "", decision: "", outcome: "", stage: "implementation" },
      { event_id: "missing", title: "Missing date", context: "", decision: "", outcome: "", stage: "result" }
    ]
  });

  const result = renderProjectContent(project, "build-timeline");

  assert.ok(result.html.indexOf("Same A") < result.html.indexOf("Same B"));
  assert.ok(result.html.indexOf("Same B") < result.html.indexOf("Late"));
  assert.ok(result.html.indexOf("Late") < result.html.indexOf("Missing date"));
  assert.match(result.html, /날짜 미확인/);
  assert.doesNotMatch(result.html, /1970-01-01|Invalid Date/);
});

test("evidence groups public records and drops unsafe urls and private locator fields", async (t) => {
  installSanitizers(t);
  const { renderProjectContent } = await importRenderModule(t);
  const project = fixtureProject({
    evidence: [
      {
        id: "safe-test",
        label: "Focused test result",
        source_type: "test",
        observed_at: "2026-08-28T09:00:00Z",
        url: "https://example.com/report"
      },
      {
        id: "unsafe-session",
        label: "Private session note",
        source_type: "session",
        observed_at: "2026-08-28T09:30:00Z",
        url: "javascript:alert(1)",
        source_locator: "/home/dowon/.codex/sessions/private.jsonl",
        session_id: "session-123"
      }
    ]
  });

  const result = renderProjectContent(project, "evidence");

  assert.match(result.html, /Focused test result/);
  assert.match(result.html, /https:\/\/example\.com\/report/);
  assert.match(result.html, /Private session note/);
  assert.doesNotMatch(result.html, /javascript:|source_locator|session-123|\/home\/dowon\/\.codex\/sessions/);
});
