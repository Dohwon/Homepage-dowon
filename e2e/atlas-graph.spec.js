const { PNG } = require("pngjs");
const { test, expect } = require("./fixtures");

test.setTimeout(60_000);

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 }
];

function nonBackgroundPixelCount(image) {
  const background = [image.data[0], image.data[1], image.data[2]];
  let count = 0;
  for (let offset = 0; offset < image.data.length; offset += 4) {
    const delta = Math.abs(image.data[offset] - background[0])
      + Math.abs(image.data[offset + 1] - background[1])
      + Math.abs(image.data[offset + 2] - background[2]);
    if (image.data[offset + 3] > 0 && delta > 36) count += 1;
  }
  return count;
}

async function graphSnapshot(page) {
  return page.locator("[data-graph-canvas]").evaluate((element) => (
    typeof element.__atlasGraphInspector === "function"
      ? element.__atlasGraphInspector()
      : null
  ));
}

async function expectControlsDoNotOverlap(page) {
  const selectors = [
    ".graph-search",
    "[data-graph-relation-menu] summary",
    "[data-graph-fit]",
    "[data-graph-reset]",
    "[data-graph-status]"
  ];
  const boxes = [];
  for (const selector of selectors) {
    const box = await page.locator(selector).boundingBox();
    expect(box, `${selector} must have layout bounds`).not.toBeNull();
    boxes.push({ selector, ...box });
  }
  for (let left = 0; left < boxes.length; left += 1) {
    for (let right = left + 1; right < boxes.length; right += 1) {
      const a = boxes[left];
      const b = boxes[right];
      const overlaps = a.x < b.x + b.width - 1
        && a.x + a.width > b.x + 1
        && a.y < b.y + b.height - 1
        && a.y + a.height > b.y + 1;
      expect(overlaps, `${a.selector} overlaps ${b.selector}`).toBe(false);
    }
  }
}

test("2D KG is nonblank, labeled, and bounded on desktop and mobile", async ({ page }) => {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("/graph");
    const graphSurface = page.locator("[data-graph-canvas]");
    const svg = graphSurface.locator("svg[data-knowledge-graph]");
    await expect(svg).toBeVisible();
    await expect(graphSurface.locator("canvas")).toHaveCount(0);
    await expect.poll(async () => (
      nonBackgroundPixelCount(PNG.sync.read(await svg.screenshot()))
    )).toBeGreaterThan(500);

    const snapshot = await graphSnapshot(page);
    expect(snapshot.layout).toBe("layered-2d");
    expect(snapshot.visibleKinds).toContain("KnowledgeFocus");
    expect(snapshot.visibleKinds).toContain("KnowledgeDomain");
    expect(snapshot.nodes.length).toBeGreaterThan(0);
    await expect(page.locator("[data-graph-node]")).toHaveCount(snapshot.nodes.length);
    const labels = await page.locator("[data-graph-node]").evaluateAll((nodes) => (
      nodes.map((node) => node.getAttribute("aria-label"))
    ));
    expect(labels.every(Boolean)).toBe(true);

    const background = await svg.locator(".kg-background").evaluate((element) => (
      getComputedStyle(element).fill
    ));
    expect(background).not.toBe("rgb(0, 0, 0)");
    expect(await page.evaluate(() => (
      document.documentElement.scrollWidth - document.documentElement.clientWidth
    ))).toBeLessThanOrEqual(1);
    await expectControlsDoNotOverlap(page);
  }
});

test("2D controls, search, keyboard selection, filters, and Reset remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/graph");

  await expect(page.locator("#knowledge-graph")).toHaveAttribute("role", "group");
  const initialCount = Number(await page.locator("[data-graph-node-count]").textContent());
  expect(initialCount).toBeGreaterThan(0);
  await expect(page.locator("[data-reduced-motion]")).toHaveAttribute("data-reduced-motion", "false");

  await page.locator("[data-graph-fit]").click();
  await expect.poll(async () => (await graphSnapshot(page))?.lastCommand?.operation).toBe("fit");
  for (const selector of ["[data-graph-fit]", "[data-graph-reset]"]) {
    const box = await page.locator(selector).boundingBox();
    expect(box.width).toBe(42);
    expect(box.height).toBe(42);
  }

  await page.locator("[data-graph-search]").fill("Alpha");
  await page.locator('[data-graph-search-result="project:alpha"]').click();
  await expect(page.locator("[data-selected-node]")).toContainText("Alpha");
  expect(Number(await page.locator("[data-graph-node-count]").textContent())).toBeGreaterThanOrEqual(initialCount);
  await expect(page.locator('[data-graph-node="project:alpha"]')).toBeVisible();
  await expect(page.locator("[data-project-article-link]")).toHaveAttribute("href", "/projects/alpha");
  await expect(page.locator("[data-selected-relations]")).toContainText("HAS_FOCUS");
  await expect(page.locator("[data-selected-relations]")).toContainText("Routing spec");

  const projectNode = page.locator('[data-graph-node="project:alpha"]');
  await projectNode.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-selected-node]")).toContainText("Alpha");

  await page.locator("[data-graph-relation-menu] summary").click();
  await page.locator('[data-graph-relation-filter][value="HAS_TAG"]').uncheck();
  await expect(page.locator('[data-selected-relations] code', { hasText: "HAS_TAG" })).toHaveCount(0);

  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("[data-reduced-motion]")).toHaveAttribute("data-reduced-motion", "true");
  await expect.poll(async () => (await graphSnapshot(page))?.reducedMotion).toBe(true);

  await page.locator("[data-graph-reset]").click();
  await expect(page.locator("[data-graph-node-count]")).toHaveText(String(initialCount));
  await expect(page.locator("[data-selected-node]")).toContainText("노드를 선택");
  await expect.poll(async () => (await graphSnapshot(page))?.lastCommand?.operation).toBe("reset");
});

test("project search result navigates to the project article", async ({ page }) => {
  await page.goto("/graph");
  await page.locator("[data-graph-search]").fill("Alpha");
  await page.locator('[data-graph-search-result="project:alpha"]').click();
  await page.locator("[data-project-article-link]").click();
  await expect(page).toHaveURL(/\/projects\/alpha$/);
  await expect(page.locator("h1")).toContainText("Alpha");
});

test("SVG capability failure renders a searchable hierarchy", async ({ page }) => {
  await page.addInitScript(() => {
    const original = Document.prototype.createElementNS;
    Document.prototype.createElementNS = function createElementNS(namespace, name, ...args) {
      if (namespace === "http://www.w3.org/2000/svg" && name === "svg") return {};
      return original.call(this, namespace, name, ...args);
    };
  });
  await page.goto("/graph");

  await expect(page.locator("[data-graph-fallback]")).toBeVisible();
  await page.locator("[data-graph-fallback-search]").fill("Alpha");
  await expect(page.locator('[data-fallback-node="project:alpha"]')).toBeVisible();
  await expect(page.locator('[data-fallback-node="project:alpha"]')).toHaveAttribute("href", "/projects/alpha");
});
