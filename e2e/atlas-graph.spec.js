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

async function canvasPng(canvas) {
  return PNG.sync.read(await canvas.screenshot());
}

function vectorDistance(left, right) {
  return Math.hypot(left.x - right.x, left.y - right.y, left.z - right.z);
}

function cameraVector(snapshot) {
  return {
    x: snapshot.camera.x - snapshot.target.x,
    y: snapshot.camera.y - snapshot.target.y,
    z: snapshot.camera.z - snapshot.target.z
  };
}

async function graphSnapshot(page) {
  return page.locator("[data-graph-canvas]").evaluate((element) => (
    typeof element.__atlasGraphInspector === "function"
      ? element.__atlasGraphInspector()
      : null
  ));
}

function snapshotMotion(previous, current) {
  const currentNodes = new Map(current.nodes.map((node) => [node.id, node]));
  const nodeMotion = previous.nodes.reduce((maximum, node) => {
    const next = currentNodes.get(node.id);
    return next ? Math.max(maximum, vectorDistance(node.position, next.position)) : Number.POSITIVE_INFINITY;
  }, 0);
  return Math.max(
    vectorDistance(previous.camera, current.camera),
    vectorDistance(previous.target, current.target),
    nodeMotion
  );
}

async function waitForSettledGraph(page) {
  await expect.poll(async () => (await graphSnapshot(page))?.engineSettled).toBe(true);
  let previous = await graphSnapshot(page);
  let stableSamples = 0;
  await expect.poll(async () => {
    await page.waitForTimeout(80);
    const current = await graphSnapshot(page);
    stableSamples = current && snapshotMotion(previous, current) < 0.05 ? stableSamples + 1 : 0;
    previous = current;
    return stableSamples;
  }).toBeGreaterThanOrEqual(2);
  return graphSnapshot(page);
}

function backgroundGesturePoint(box, snapshot) {
  const candidates = [
    { x: box.width * 0.8, y: box.height * 0.75 },
    { x: box.width * 0.2, y: box.height * 0.75 },
    { x: box.width * 0.75, y: box.height * 0.45 }
  ];
  return candidates.sort((left, right) => {
    const clearance = point => Math.min(...snapshot.nodes.map(node => (
      Math.hypot(point.x - node.screen.x, point.y - node.screen.y)
    )));
    return clearance(right) - clearance(left);
  })[0];
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
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/graph");
  const canvas = page.locator("[data-graph-canvas] canvas");
  await expect(canvas).toBeVisible();
  await expect.poll(async () => nonBackgroundPixelCount(await canvasPng(canvas))).toBeGreaterThan(500);
  const box = await canvas.boundingBox();

  const beforeZoom = await waitForSettledGraph(page);
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.55);
  await page.mouse.wheel(0, -600);
  await expect.poll(async () => (await graphSnapshot(page)).controlRevision).toBeGreaterThan(beforeZoom.controlRevision);
  const afterZoom = await waitForSettledGraph(page);
  expect(vectorDistance(beforeZoom.target, afterZoom.target)).toBeLessThan(1);
  expect(Math.abs(vectorDistance(beforeZoom.camera, beforeZoom.target) - vectorDistance(afterZoom.camera, afterZoom.target))).toBeGreaterThan(2);

  const beforeRotate = afterZoom;
  const rotatePoint = backgroundGesturePoint(box, beforeRotate);
  await page.mouse.move(box.x + rotatePoint.x, box.y + rotatePoint.y);
  await page.mouse.down();
  await page.mouse.move(box.x + rotatePoint.x - 90, box.y + rotatePoint.y - 55, { steps: 8 });
  await page.mouse.up();
  await expect.poll(async () => (await graphSnapshot(page)).controlRevision).toBeGreaterThan(beforeRotate.controlRevision);
  const afterRotate = await waitForSettledGraph(page);
  expect(vectorDistance(beforeRotate.target, afterRotate.target)).toBeLessThan(1);
  expect(Math.abs(vectorDistance(beforeRotate.camera, beforeRotate.target) - vectorDistance(afterRotate.camera, afterRotate.target))).toBeLessThan(2);
  expect(vectorDistance(cameraVector(beforeRotate), cameraVector(afterRotate))).toBeGreaterThan(2);

  const beforePan = afterRotate;
  const panPoint = backgroundGesturePoint(box, beforePan);
  await page.mouse.move(box.x + panPoint.x, box.y + panPoint.y);
  await page.mouse.down({ button: "right" });
  await page.mouse.move(box.x + panPoint.x - 75, box.y + panPoint.y - 45, { steps: 8 });
  await page.mouse.up({ button: "right" });
  await expect.poll(async () => (await graphSnapshot(page)).controlRevision).toBeGreaterThan(beforePan.controlRevision);
  const afterPan = await waitForSettledGraph(page);
  expect(vectorDistance(beforePan.target, afterPan.target)).toBeGreaterThan(2);
  expect(vectorDistance(cameraVector(beforePan), cameraVector(afterPan))).toBeLessThan(2);

  const commandRevision = afterPan.lastCameraCommand?.revision || 0;
  await page.locator("[data-graph-fit]").click();
  await expect.poll(async () => (await graphSnapshot(page)).lastCameraCommand?.revision || 0).toBeGreaterThan(commandRevision);
  const afterFit = await waitForSettledGraph(page);
  expect(afterFit.lastCameraCommand).toMatchObject({ operation: "fit", duration: 500 });

  const project = afterFit.nodes.find(node => (
    node.kind === "Project"
    && node.screen.x > 0 && node.screen.x < box.width
    && node.screen.y > 100 && node.screen.y < box.height
  ));
  expect(project, "a projected Project node is required for drag").toBeTruthy();
  const dragRevision = afterFit.lastDrag?.revision || 0;
  const start = { x: box.x + project.screen.x, y: box.y + project.screen.y };
  const end = { x: start.x + 42, y: start.y + 30 };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(end.x, end.y, { steps: 10 });
  await page.mouse.up();
  await expect.poll(async () => (await graphSnapshot(page)).lastDrag?.revision || 0).toBeGreaterThan(dragRevision);
  const afterDrag = await graphSnapshot(page);
  expect(afterDrag.lastDrag.id).toBe(project.id);
  expect(afterDrag.lastDrag.pinned).toBe(true);
  expect(vectorDistance(afterDrag.lastDrag.from, afterDrag.lastDrag.to)).toBeGreaterThan(2);
  expect(afterDrag.nodes.find(node => node.id === project.id).pinned).toBe(true);

  await page.locator("[data-graph-reset]").click();
  await expect(page.locator("[data-graph-node-count]")).toHaveText("4");
  await expect(page.locator("[data-selected-node]")).toContainText("노드를 선택");
  await expect.poll(async () => (await graphSnapshot(page)).lastCameraCommand?.operation).toBe("reset");
});

test("progressive graph controls reveal exact paths and navigate to projects", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/graph");

  await expect(page.locator("#knowledge-graph")).toHaveAttribute("role", "group");
  await expect(page.locator("[data-graph-node-count]")).toHaveText("4");
  await expect(page.locator("[data-reduced-motion]")).toHaveAttribute("data-reduced-motion", "false");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("[data-reduced-motion]")).toHaveAttribute("data-reduced-motion", "true");
  await expect.poll(async () => (await graphSnapshot(page))?.reducedMotion).toBe(true);
  const motionCommandRevision = (await graphSnapshot(page)).lastCameraCommand?.revision || 0;
  await page.locator("[data-graph-fit]").click();
  await expect.poll(async () => {
    const command = (await graphSnapshot(page)).lastCameraCommand;
    return command?.operation === "fit" && command.revision > motionCommandRevision
      ? command.duration
      : null;
  }).toBe(0);

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
