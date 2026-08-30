const { test, expect } = require("./fixtures");

test("graph starts collapsed and expands one project neighborhood", async ({ page }) => {
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

  await page.locator("[data-graph-reset]").click();
  await expect(page.locator("[data-graph-node-count]")).toHaveText("4");
  await expect(page.locator("[data-selected-node]")).toContainText("노드를 선택");
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
