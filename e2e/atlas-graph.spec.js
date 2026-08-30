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

function pixelDifferenceCount(left, right) {
  if (left.width !== right.width || left.height !== right.height) return Number.POSITIVE_INFINITY;
  let count = 0;
  for (let offset = 0; offset < left.data.length; offset += 4) {
    const delta = Math.abs(left.data[offset] - right.data[offset])
      + Math.abs(left.data[offset + 1] - right.data[offset + 1])
      + Math.abs(left.data[offset + 2] - right.data[offset + 2]);
    if (delta > 42) count += 1;
  }
  return count;
}

function projectPixel(image) {
  const target = [79, 134, 198];
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      const offset = (y * image.width + x) * 4;
      const red = image.data[offset];
      const green = image.data[offset + 1];
      const blue = image.data[offset + 2];
      const delta = Math.abs(red - target[0]) + Math.abs(green - target[1]) + Math.abs(blue - target[2]);
      if (image.data[offset + 3] > 0 && delta < 90 && blue > red && blue > green) return { x, y };
    }
  }
  return null;
}

async function canvasPng(canvas) {
  return PNG.sync.read(await canvas.screenshot());
}

async function expectCanvasChanged(canvas, action) {
  const before = await canvasPng(canvas);
  await action();
  await expect.poll(async () => pixelDifferenceCount(before, await canvasPng(canvas))).toBeGreaterThan(200);
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

test("3D graph canvas is nonblank and bounded on desktop and mobile", async ({ page }) => {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("/graph");
    const canvas = page.locator("[data-graph-canvas] canvas");
    await expect(canvas).toBeVisible();
    await expect.poll(async () => nonBackgroundPixelCount(await canvasPng(canvas))).toBeGreaterThan(500);

    const graph = await page.request.get("/api/atlas/graph").then((response) => response.json());
    const initialCount = Number(await page.locator("[data-graph-node-count]").textContent());
    expect(initialCount).toBeGreaterThan(0);
    expect(initialCount).toBeLessThan(graph.nodes.length);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await expectControlsDoNotOverlap(page);
  }
});

test("canvas supports zoom, pan, rotate, node drag, Fit, and Reset", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/graph");
  const canvas = page.locator("[data-graph-canvas] canvas");
  await expect(canvas).toBeVisible();
  await expect.poll(async () => nonBackgroundPixelCount(await canvasPng(canvas))).toBeGreaterThan(500);
  await page.waitForTimeout(500);
  const box = await canvas.boundingBox();

  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.55);
  await expectCanvasChanged(canvas, () => page.mouse.wheel(0, -600));
  await expectCanvasChanged(canvas, async () => {
    await page.mouse.move(box.x + box.width * 0.72, box.y + box.height * 0.72);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.62, box.y + box.height * 0.64, { steps: 8 });
    await page.mouse.up();
  });
  await expectCanvasChanged(canvas, async () => {
    await page.mouse.move(box.x + box.width * 0.74, box.y + box.height * 0.74);
    await page.mouse.down({ button: "right" });
    await page.mouse.move(box.x + box.width * 0.66, box.y + box.height * 0.68, { steps: 8 });
    await page.mouse.up({ button: "right" });
  });

  const beforeDrag = await canvasPng(canvas);
  const pixel = projectPixel(beforeDrag);
  expect(pixel, "a rendered Project node pixel is required for drag").not.toBeNull();
  const scaleX = box.width / beforeDrag.width;
  const scaleY = box.height / beforeDrag.height;
  const start = { x: box.x + pixel.x * scaleX, y: box.y + pixel.y * scaleY };
  const end = { x: start.x + 42, y: start.y + 30 };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(end.x, end.y, { steps: 10 });
  await page.mouse.up();
  await expect.poll(async () => pixelDifferenceCount(beforeDrag, await canvasPng(canvas))).toBeGreaterThan(200);

  await expectCanvasChanged(canvas, () => page.locator("[data-graph-fit]").click());
  await page.locator("[data-graph-reset]").click();
  await expect(page.locator("[data-graph-node-count]")).toHaveText("4");
  await expect(page.locator("[data-selected-node]")).toContainText("노드를 선택");
});

test("progressive graph controls reveal exact paths and navigate to projects", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/graph");

  await expect(page.locator("#knowledge-graph")).toHaveAttribute("role", "group");
  await expect(page.locator("[data-graph-node-count]")).toHaveText("4");
  await expect(page.locator("[data-reduced-motion]")).toHaveAttribute("data-reduced-motion", "false");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("[data-reduced-motion]")).toHaveAttribute("data-reduced-motion", "true");

  for (const selector of ["[data-graph-fit]", "[data-graph-reset]"]) {
    const box = await page.locator(selector).boundingBox();
    expect(box.width).toBe(42);
    expect(box.height).toBe(42);
  }

  await page.locator("[data-graph-search]").fill("AI Quality");
  await page.locator('[data-graph-search-result="focus:ai-quality"]').click();
  await expect(page.locator("[data-selected-node]")).toContainText("AI Quality");
  await expect(page.locator("[data-graph-node-count]")).toHaveText("8");

  await page.locator("[data-graph-reset]").click();
  await page.locator("[data-graph-search]").fill("Knowledge Systems");
  await page.locator('[data-graph-search-result="domain:knowledge-systems"]').click();
  await expect(page.locator("[data-selected-node]")).toContainText("Knowledge Systems");
  await expect(page.locator("[data-graph-node-count]")).toHaveText("5");

  await page.locator("[data-graph-reset]").click();
  await page.locator("[data-graph-search]").fill("Alpha");
  await page.locator('[data-graph-search-result="project:alpha"]').click();
  await expect(page.locator("[data-selected-node]")).toContainText("Alpha");
  await expect(page.locator("[data-graph-node-count]")).toHaveText("5");
  await expect(page.locator("[data-project-article-link]")).toHaveAttribute("href", "/projects/alpha");
  await expect(page.locator("[data-selected-relations]")).toContainText("HAS_FOCUS");
  await expect(page.locator("[data-selected-relations]")).toContainText("Routing spec");

  await page.locator("[data-graph-relation-menu] summary").click();
  await page.locator('[data-graph-relation-filter][value="HAS_TAG"]').uncheck();
  await expect(page.locator('[data-selected-relations] code', { hasText: "HAS_TAG" })).toHaveCount(0);

  await page.locator("[data-project-article-link]").click();
  await expect(page).toHaveURL(/\/projects\/alpha$/);
  await expect(page.locator("h1")).toContainText("Alpha");
});

test("WebGL failure renders a searchable hierarchy", async ({ page }) => {
  await page.addInitScript(() => {
    HTMLCanvasElement.prototype.getContext = () => null;
  });
  await page.goto("/graph");

  await expect(page.locator("[data-graph-fallback]")).toBeVisible();
  await page.locator("[data-graph-fallback-search]").fill("Alpha");
  await expect(page.locator('[data-fallback-node="project:alpha"]')).toBeVisible();
  await expect(page.locator('[data-fallback-node="project:alpha"]')).toHaveAttribute("href", "/projects/alpha");
});
