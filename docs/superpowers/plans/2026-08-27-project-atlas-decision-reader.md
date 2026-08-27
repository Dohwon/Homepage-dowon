# Project Atlas Decision Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the existing Atlas shell while turning each project detail into a decision-first reader with neutral long-form content, a sticky left table of contents, article-relative progress, inline explanatory SVGs, and four stable tabs.

**Architecture:** The server returns the structured article contract from the knowledge-content plan. The client renders article sections directly instead of reconstructing them from one Markdown file, sanitizes each section and SVG independently, and binds route-scoped reader behavior after every render. URL hashes are first-class navigation state so section links survive reload, back, and forward navigation.

**Tech Stack:** Vanilla ES modules, marked, DOMPurify, Lucide, CSS Grid and sticky positioning, IntersectionObserver, Playwright, Node test runner

**Spec:** `docs/superpowers/specs/2026-08-27-project-atlas-content-graph-redesign.md`

**Prerequisite:** Complete `2026-08-27-project-atlas-knowledge-content-foundation.md` first so the server exposes `article`, `timeline`, `evidence`, `systemMap`, and `visuals`.

## Global Constraints

- Preserve the Home, Projects, Topics, Graph, and Changelog navigation and the current Atlas visual identity.
- Do not convert the whole service into a blog theme.
- Project tabs are exactly `Decisions`, `System Map`, `Build Timeline`, and `Evidence`; `Decisions` is the default.
- Remove the repetitive Overview tab while keeping summary and metadata in the shared project header.
- Desktop TOC stays on the left and follows the article without overlapping sticky headers.
- Mobile TOC is compact and never covers article text or project tabs.
- The horizontal progress bar measures only the active project article, not the whole document.
- Long Korean titles, tabs, buttons, diagrams, and code blocks must not overflow at 320px width.
- SVGs explain a nearby paragraph, include a caption and text alternative, and remain optional.
- Headings use plain factual wording; the UI must not add dramatic copy around curated titles.

---

## Planned File Structure

```text
client/
├── router.js             # four-tab route contract and legacy tab normalization
├── render.js             # structured article and tab rendering
├── project-reader.js     # TOC active state, mobile menu, hash restoration
├── progress.js           # article-relative progress calculation and binding
├── markdown.js           # sanitized Markdown fragments
└── main.js               # route-scoped reader lifecycle
styles.css                # sticky tab rail, left TOC, reader, figures, responsive states
test/client/
├── router.test.js
├── project-reader.test.js
└── progress.test.js
e2e/
├── atlas-navigation.spec.js
├── atlas-responsive.spec.js
└── atlas-reader.spec.js
```

### Task 1: Four-Tab Route Contract and Legacy URL Compatibility

**Files:**
- Modify: `client/router.js`
- Modify: `test/client/router.test.js`

**Interfaces:**
- Consumes: project URLs and optional `tab` query parameters.
- Produces: `PROJECT_TABS`, `normalizeTab(value) -> ProjectTab`, `parseRoute(input)`, and `toRouteHref(route)` with `decisions` as the default.

- [ ] **Step 1: Replace old expectations with failing four-tab tests**

```javascript
test("project routes expose four decision-reader tabs", async () => {
  const { PROJECT_TABS, parseRoute } = await importBrowserModule("client/router.js");
  assert.deepEqual([...PROJECT_TABS], ["decisions", "system-map", "build-timeline", "evidence"]);
  assert.deepEqual(
    parseRoute(new URL("https://atlas.test/projects/alpha")),
    { view: "project", projectId: "alpha", tab: "decisions" }
  );
});

test("legacy project tabs normalize without exposing removed tabs", async () => {
  const { normalizeTab, toRouteHref } = await importBrowserModule("client/router.js");
  assert.equal(normalizeTab("overview"), "decisions");
  assert.equal(normalizeTab("build-story"), "build-timeline");
  assert.equal(normalizeTab("visual-map"), "system-map");
  assert.equal(normalizeTab("rollbacks"), "evidence");
  assert.equal(toRouteHref({ view: "project", projectId: "alpha", tab: "decisions" }), "/projects/alpha");
});
```

- [ ] **Step 2: Run router tests and verify failure**

Run: `node --test test/client/router.test.js`

Expected: FAIL because `overview` is still the default and six old tabs remain.

- [ ] **Step 3: Implement the exact public and legacy maps**

```javascript
export const PROJECT_TABS = readonlySet([
  "decisions",
  "system-map",
  "build-timeline",
  "evidence"
]);

const LEGACY_TABS = Object.freeze({
  overview: "decisions",
  "build-story": "build-timeline",
  rollbacks: "evidence",
  "visual-map": "system-map",
  artifacts: "evidence"
});

export function normalizeTab(value) {
  if (PROJECT_TABS.has(value)) return value;
  return LEGACY_TABS[value] || "decisions";
}
```

Serialize no `tab` query for the default `decisions` route. Unknown and private names still normalize to `decisions`.

- [ ] **Step 4: Run router and API tests**

Run: `node --test test/client/router.test.js test/server/atlas-api.test.js`

Expected: PASS.

- [ ] **Step 5: Commit the tab contract**

```bash
git add client/router.js test/client/router.test.js
git commit -m "feat: make Decisions the default Atlas project tab"
```

### Task 2: Article-Relative Progress Calculation

**Files:**
- Modify: `client/progress.js`
- Modify: `client/main.js`
- Create: `test/client/progress.test.js`

**Interfaces:**
- Consumes: progress element and the active `[data-project-reader]` element.
- Produces: `articleProgress(article, viewportTop, viewportHeight) -> number` and `bindReadingProgress(element, article) -> cleanup`.

- [ ] **Step 1: Write failing pure progress tests**

```javascript
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
  assert.equal(articleProgress({ offsetTop: 100, offsetHeight: 400 }, 100, 800), 1);
});
```

- [ ] **Step 2: Run progress tests and verify failure**

Run: `node --test test/client/progress.test.js`

Expected: FAIL because the current module measures the full document.

- [ ] **Step 3: Implement a route-scoped progress binder**

```javascript
export function articleProgress(article, viewportTop, viewportHeight) {
  if (!article) return 0;
  const travel = Math.max(0, article.offsetHeight - viewportHeight);
  if (travel === 0) return viewportTop >= article.offsetTop ? 1 : 0;
  return Math.min(1, Math.max(0, (viewportTop - article.offsetTop) / travel));
}

export function bindReadingProgress(element, article) {
  if (!element || !article) {
    element?.removeAttribute("data-active");
    if (element) element.style.transform = "scaleX(0)";
    return () => {};
  }
  element.setAttribute("data-active", "");
  let frame = 0;
  const update = () => {
    frame = 0;
    const ratio = articleProgress(article, window.scrollY, window.innerHeight);
    element.style.transform = `scaleX(${ratio})`;
  };
  const requestUpdate = () => { if (!frame) frame = requestAnimationFrame(update); };
  update();
  window.addEventListener("scroll", requestUpdate, { passive: true });
  window.addEventListener("resize", requestUpdate);
  return () => {
    window.removeEventListener("scroll", requestUpdate);
    window.removeEventListener("resize", requestUpdate);
    if (frame) cancelAnimationFrame(frame);
  };
}
```

Move binding out of initial module startup. After each route render, `main.js` binds the progress element only to `root.querySelector("[data-project-reader]")` and disposes the prior binding.

- [ ] **Step 4: Run progress and navigation tests**

Run: `node --test test/client/progress.test.js test/client/router.test.js`

Expected: PASS. Non-project routes leave the bar hidden and reset to zero.

- [ ] **Step 5: Commit article progress**

```bash
git add client/progress.js client/main.js test/client/progress.test.js
git commit -m "feat: measure Atlas project reading progress"
```

### Task 3: Structured Decisions Article and Inline Figures

**Files:**
- Modify: `client/render.js`
- Modify: `client/markdown.js`
- Create: `test/client/project-reader.test.js`
- Modify: `test/client/markdown.test.js`

**Interfaces:**
- Consumes: `project.article`, `project.visuals`, `project.systemMap`, `project.timeline`, and `project.evidence` from the public API.
- Produces: `renderArticle(project)`, `renderSystemMap(project)`, `renderTimeline(project)`, `renderEvidence(project)`, and DOM hooks for the reader behavior.

- [ ] **Step 1: Write failing render tests for prose-first sections**

```javascript
test("renders every article section and places figures after its prose", async () => {
  const { renderProjectContent } = await importRenderModule();
  const project = fixtureProject({
    article: {
      readiness: "ready",
      sections: [{
        id: "retention",
        title: "TMAP 데이터 장기 저장 제한 해결",
        section_type: "decision",
        body: "TMAP 데이터는 세션 입력으로만 사용한다.",
        evidence_ids: ["ev-1"],
        diagrams: [{ id: "lifecycle", caption: "두 데이터의 저장 수명", alt: "TMAP과 VWorld 저장 수명 비교" }]
      }]
    },
    visuals: { lifecycle: SAFE_SVG }
  });
  const result = renderProjectContent(project, "decisions");
  assert.match(result.html, /data-article-section="retention"/);
  assert.ok(result.html.indexOf("세션 입력") < result.html.indexOf("data-article-figure"));
  assert.match(result.html, /<figcaption>두 데이터의 저장 수명<\/figcaption>/);
});

test("insufficient evidence renders factual status without empty decision blocks", async () => {
  const { renderProjectContent } = await importRenderModule();
  const result = renderProjectContent(fixtureProject({ article: { readiness: "insufficient-evidence", sections: [] } }), "decisions");
  assert.match(result.html, /확인 가능한 공개 근거가 부족합니다/);
  assert.doesNotMatch(result.html, /대안|롤백|문제 해결 지도/);
});
```

- [ ] **Step 2: Run project-reader tests and verify failure**

Run: `node --test test/client/project-reader.test.js test/client/markdown.test.js`

Expected: FAIL because `renderProjectContent` still consumes legacy Markdown fields.

- [ ] **Step 3: Implement section, figure, timeline, and evidence renderers**

```javascript
function renderArticleFigure(diagram, visuals) {
  const svg = safeInlineSvg(visuals?.[diagram.id]);
  if (!svg) return "";
  return `<figure class="article-figure" data-article-figure aria-label="${escapeHtml(diagram.alt)}">
    <div class="article-figure-media">${svg}</div>
    <figcaption>${escapeHtml(diagram.caption)}</figcaption>
  </figure>`;
}

export function renderArticle(project) {
  const article = project.article;
  if (!article || article.readiness === "insufficient-evidence") {
    return { html: '<p class="empty-state">확인 가능한 공개 근거가 부족합니다.</p>', headings: [] };
  }
  const prior = article.prior_context
    ? `<section id="prior-context" data-article-section="prior-context"><h2>이전 단계</h2>${renderMarkdown(article.prior_context)}</section>`
    : "";
  const sections = article.sections.map(section => `<section id="${escapeHtml(section.id)}" data-article-section="${escapeHtml(section.id)}">
      <p class="section-type">${escapeHtml(section.section_type)}</p>
      <h2>${escapeHtml(section.title)}</h2>
      <div class="markdown-body">${renderMarkdown(section.body)}</div>
      ${(section.diagrams || []).map(item => renderArticleFigure(item, project.visuals)).join("")}
    </section>`).join("");
  return { html: `<article class="decision-article" data-project-reader>${prior}${sections}</article>`, headings: article.sections.map(({ id, title }) => ({ id, label: title })) };
}
```

`System Map` sanitizes the optional SVG and otherwise shows no diagram placeholder. `Build Timeline` renders all events in date order without manufacturing dates. `Evidence` groups only public evidence records and safe URLs; raw locator and session fields are not accepted by client state.

- [ ] **Step 4: Run rendering, store, and privacy tests**

Run: `node --test test/client/project-reader.test.js test/client/markdown.test.js test/server/atlas-store.test.js`

Expected: PASS. Malicious Markdown/SVG remains stripped.

- [ ] **Step 5: Commit structured reader rendering**

```bash
git add client/render.js client/markdown.js test/client/project-reader.test.js test/client/markdown.test.js
git commit -m "feat: render evidence-backed Atlas decision articles"
```

### Task 4: Sticky Left TOC, Active Section, and Hash Restoration

**Files:**
- Create: `client/project-reader.js`
- Modify: `client/render.js`
- Modify: `client/main.js`
- Modify: `test/client/project-reader.test.js`
- Modify: `e2e/atlas-navigation.spec.js`

**Interfaces:**
- Consumes: `[data-project-reader]`, `[data-project-toc]`, section IDs, and `location.hash`.
- Produces: `bindProjectReader(root, { location, history }) -> cleanup`, active TOC markers, compact mobile TOC behavior, and reliable deep links.

- [ ] **Step 1: Write failing active-section and hash tests**

```javascript
test("reader marks the intersecting section and updates the hash", async () => {
  const fixture = readerDom(["retention", "validation"]);
  const observer = new FakeIntersectionObserver();
  const cleanup = bindProjectReader(fixture.root, { observerFactory: () => observer, history: fixture.history, location: fixture.location });
  observer.emit("validation", true);
  assert.equal(fixture.root.querySelector('[href="#validation"]').getAttribute("aria-current"), "location");
  assert.equal(fixture.history.lastUrl, "#validation");
  cleanup();
});

test("reader restores an existing section hash after route rendering", async () => {
  const fixture = readerDom(["retention"], { hash: "#retention" });
  bindProjectReader(fixture.root, fixture.dependencies);
  await fixture.nextFrame();
  assert.equal(fixture.section.scrollIntoViewCalls, 1);
});
```

- [ ] **Step 2: Run reader behavior tests and verify failure**

Run: `node --test test/client/project-reader.test.js`

Expected: FAIL importing `client/project-reader.js`.

- [ ] **Step 3: Implement one observer and non-polluting hash updates**

```javascript
export function bindProjectReader(root, {
  observerFactory = callback => new IntersectionObserver(callback, { rootMargin: "-24% 0px -64%", threshold: [0, 1] }),
  history = window.history,
  location = window.location
} = {}) {
  const sections = [...root.querySelectorAll("[data-article-section]")];
  const links = new Map([...root.querySelectorAll("[data-project-toc] a[href^='#']")].map(link => [link.hash.slice(1), link]));
  if (!sections.length) return () => {};
  const activate = id => {
    links.forEach((link, key) => key === id ? link.setAttribute("aria-current", "location") : link.removeAttribute("aria-current"));
    history.replaceState(history.state, "", `${location.pathname}${location.search}#${encodeURIComponent(id)}`);
  };
  const observer = observerFactory(entries => {
    const current = entries.filter(item => item.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
    if (current) activate(current.target.id);
  });
  sections.forEach(section => observer.observe(section));
  requestAnimationFrame(() => {
    const target = root.querySelector(`#${CSS.escape(decodeURIComponent(location.hash.slice(1)))}`);
    target?.scrollIntoView({ block: "start" });
  });
  return () => observer.disconnect();
}
```

Render the same links in a desktop `<nav>` and mobile `<details>` menu. TOC links are ordinary same-page anchors, not project merge/version navigation.

- [ ] **Step 4: Preserve hashes in SPA navigation and test browser history**

Change `main.js` history writes from `${url.pathname}${url.search}` to `${url.pathname}${url.search}${url.hash}`. After render, bind the reader before focus management; do not force `scrollTo(0)` when a valid hash is present.

Run: `node --test test/client/project-reader.test.js test/client/router.test.js`

Run: `npm run test:ui -- e2e/atlas-navigation.spec.js`

Expected: PASS. Reload, direct deep link, back, and forward restore the same article section.

- [ ] **Step 5: Commit reader navigation behavior**

```bash
git add client/project-reader.js client/render.js client/main.js test/client/project-reader.test.js e2e/atlas-navigation.spec.js
git commit -m "feat: add sticky Atlas article navigation"
```

### Task 5: Reader Layout, Sticky Rails, and Responsive Figures

**Files:**
- Modify: `styles.css`
- Modify: `client/render.js`
- Create: `e2e/atlas-reader.spec.js`
- Modify: `e2e/atlas-responsive.spec.js`

**Interfaces:**
- Consumes: reader DOM hooks from Tasks 2-4.
- Produces: stable desktop and mobile layouts with no overlap, clipping, or layout shift.

- [ ] **Step 1: Add failing geometry assertions for desktop and mobile**

```javascript
test("desktop TOC follows the article below sticky rails", async ({ page }) => {
  await page.goto("/projects/alpha#validation");
  const toc = page.locator("[data-project-toc-desktop]");
  const tabs = page.locator("[data-project-tab-rail]");
  const before = await toc.boundingBox();
  await page.mouse.wheel(0, 900);
  const after = await toc.boundingBox();
  const tabBox = await tabs.boundingBox();
  expect(after.y).toBeGreaterThanOrEqual(tabBox.y + tabBox.height - 1);
  expect(Math.abs(after.y - before.y)).toBeLessThan(8);
});

test("mobile reader has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/projects/alpha");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await expect(page.locator("[data-project-toc-mobile]")).toBeVisible();
  await expect(page.locator("[data-project-toc-desktop]")).toBeHidden();
});
```

- [ ] **Step 2: Run reader E2E and verify failure**

Run: `npm run test:ui -- e2e/atlas-reader.spec.js e2e/atlas-responsive.spec.js`

Expected: FAIL because the TOC is on the right, progress is document-wide, and no mobile TOC exists.

- [ ] **Step 3: Implement the desktop reading grid and sticky offsets**

```css
:root {
  --project-tab-height: 52px;
  --reader-sticky-offset: calc(var(--header-height) + var(--project-tab-height) + 18px);
}

.reading-progress {
  display: none;
  inset-block-start: calc(var(--header-height) + var(--project-tab-height));
}
.reading-progress[data-active] { display: block; }
.project-tab-rail {
  position: sticky;
  inset-block-start: var(--header-height);
  z-index: 35;
  min-block-size: var(--project-tab-height);
  background: color-mix(in srgb, var(--surface) 94%, transparent);
  backdrop-filter: blur(16px);
}
.project-layout {
  grid-template-columns: minmax(180px, 220px) minmax(0, 780px);
  justify-content: center;
  gap: 52px;
}
.project-aside { grid-column: 1; grid-row: 1; }
.project-article { grid-column: 2; grid-row: 1; max-inline-size: 780px; }
.project-aside-inner { position: sticky; inset-block-start: var(--reader-sticky-offset); }
.article-figure { margin: 24px 0 32px; }
.article-figure-media svg { inline-size: 100%; block-size: auto; min-block-size: 180px; }
.article-figure figcaption { margin-top: 9px; color: var(--muted); font-size: 13px; }
```

The shared project title stays above the sticky tab rail. Heading sizes remain compact (`h1` max 42px desktop, 30px mobile) and never scale with viewport width.

- [ ] **Step 4: Add mobile layout and verify dark mode figures**

At `max-width: 760px`, use one column, hide desktop TOC, show mobile `<details>`, keep the tabs horizontally scrollable, set figure minimum height to `140px`, and ensure `.markdown-body pre` scrolls internally. SVG colors use CSS variables embedded in the sanitized file and remain readable in `[data-theme="dark"]`.

Run: `npm run test:ui -- e2e/atlas-reader.spec.js e2e/atlas-responsive.spec.js`

Expected: PASS at 1440x900, 768x1024, 390x844, and 320x740.

- [ ] **Step 5: Commit responsive reader styles**

```bash
git add styles.css client/render.js e2e/atlas-reader.spec.js e2e/atlas-responsive.spec.js
git commit -m "feat: polish Atlas decision reader layout"
```

### Task 6: Reader Visual and Accessibility Gate

**Files:**
- Modify: `e2e/atlas-reader.spec.js`
- Modify: `e2e/atlas-privacy.spec.js`
- Modify: `README.md`

**Interfaces:**
- Consumes: the completed reader and structured fixture bundle.
- Produces: screenshot, nonblank SVG, keyboard, focus, and privacy evidence.

- [ ] **Step 1: Add nonblank, keyboard, and progress-range assertions**

```javascript
test("reader figures are nonblank and progress remains bounded", async ({ page }) => {
  await page.goto("/projects/alpha");
  const figure = page.locator("[data-article-figure]").first();
  await expect(figure).toBeVisible();
  const png = PNG.sync.read(await figure.screenshot());
  expect(new Set(pixelColors(png)).size).toBeGreaterThan(12);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const transform = await page.locator("#reading-progress").evaluate(node => getComputedStyle(node).transform);
  expect(scaleX(transform)).toBeGreaterThanOrEqual(0.98);
  expect(scaleX(transform)).toBeLessThanOrEqual(1);
});

test("tabs and TOC are keyboard reachable", async ({ page }) => {
  await page.goto("/projects/alpha");
  await page.locator("#project-tab-decisions").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#project-tab-system-map")).toBeFocused();
  await page.locator('[data-project-toc] a[href="#validation"]').focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#validation$/);
});
```

- [ ] **Step 2: Run the full UI suite and inspect failures**

Run: `npm run test:ui`

Expected: all existing and new navigation, privacy, responsive, and reader tests PASS.

- [ ] **Step 3: Update public documentation to the four-tab contract**

Replace the README project-detail line with:

```markdown
- `/projects/{id}`: Decisions, System Map, Build Timeline, Evidence 탭과 본문 기준 읽기 진행률
```

Document that empty tabs are omitted at content level and no project family/version merge occurs.

- [ ] **Step 4: Run client syntax and complete validation**

Run: `node --check client/main.js`

Run: `node --check client/render.js`

Run: `npm test`

Run: `npm run test:ui`

Expected: every command exits `0`.

- [ ] **Step 5: Commit the reader gate**

```bash
git add e2e/atlas-reader.spec.js e2e/atlas-privacy.spec.js README.md
git commit -m "test: verify Atlas decision reading experience"
```

## Completion Gate

- [ ] Confirm `/projects/<id>` opens `Decisions` without a query string.
- [ ] Confirm desktop TOC is left-aligned and sticky; mobile shows the compact TOC only.
- [ ] Confirm progress is zero before article entry and reaches one at article end.
- [ ] Confirm every rendered decision section comes from structured content and no Overview repetition remains.
- [ ] Confirm all project URLs still identify one independent project.
- [ ] Confirm `npm test` and `npm run test:ui` pass with screenshots at desktop and mobile sizes.
