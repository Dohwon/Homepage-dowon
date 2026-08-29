const { test, expect } = require("./fixtures");

async function installLongDecisionArticle(page) {
  await page.route("**/api/atlas/projects/alpha", async (route) => {
    const response = await route.fetch();
    const project = await response.json();
    project.visuals ||= {};
    project.visuals["routing-flow"] = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90"><path d="M20 45h120" fill="none" stroke="currentColor" stroke-width="8" /></svg>';
    project.article.sections = Array.from({ length: 8 }, (_, index) => ({
      id: `section-${index + 1}`,
      title: `Decision section ${index + 1}`,
      section_type: "decision",
      body: `${"This section records the public decision context and validation outcome. ".repeat(8)}\n\n\`implementation-contract-with-a-deliberately-long-token-${index + 1}\``,
      evidence_ids: [],
      diagrams: index === 1 ? [{ id: "routing-flow", alt: "Routing flow", caption: "Public routing flow" }] : []
    }));
    await route.fulfill({ response, contentType: "application/json", body: JSON.stringify(project) });
  });
}

test("desktop TOC stays left of the article below the sticky rails", async ({ page }) => {
  await installLongDecisionArticle(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/projects/alpha#section-4");

  const toc = page.locator("[data-project-toc-desktop]");
  const article = page.locator(".project-article");
  const tabs = page.locator("[data-project-tab-rail]");
  await expect(toc).toBeVisible();
  await expect(page.locator("[data-project-toc-mobile]")).toBeHidden();

  await page.evaluate(() => window.scrollTo(0, 900));
  const before = await toc.boundingBox();
  await page.mouse.wheel(0, 500);
  const after = await toc.boundingBox();
  const articleBox = await article.boundingBox();
  const tabBox = await tabs.boundingBox();

  expect(before).not.toBeNull();
  expect(after).not.toBeNull();
  expect(articleBox).not.toBeNull();
  expect(tabBox).not.toBeNull();
  expect(after.x + after.width).toBeLessThan(articleBox.x);
  expect(after.y).toBeGreaterThanOrEqual(tabBox.y + tabBox.height - 1);
  expect(Math.abs(after.y - before.y)).toBeLessThan(8);
  expect(articleBox.width).toBeLessThanOrEqual(780);
});

test("reader switches between desktop and compact mobile TOC at the layout boundary", async ({ page }) => {
  await installLongDecisionArticle(page);
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/projects/alpha");
  await expect(page.locator("[data-project-toc-desktop]")).toBeVisible();
  await expect(page.locator("[data-project-toc-mobile]")).toBeHidden();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("[data-project-toc-desktop]")).toBeHidden();
  await expect(page.locator("[data-project-toc-mobile]")).toBeVisible();
  await expect(page.locator("[data-project-toc-mobile] details")).not.toHaveAttribute("open", "");
});

test("320px dark reader keeps tabs, prose and figures inside the viewport", async ({ page }) => {
  await installLongDecisionArticle(page);
  await page.setViewportSize({ width: 320, height: 740 });
  await page.addInitScript(() => localStorage.setItem("atlas-theme", "dark"));
  await page.goto("/projects/alpha");

  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("[data-project-toc-mobile]")).toBeVisible();
  await expect(page.locator("[data-project-toc-desktop]")).toBeHidden();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  const tabs = page.locator("[data-project-tab-rail]");
  const tabGeometry = await tabs.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    overflowX: getComputedStyle(element).overflowX
  }));
  expect(tabGeometry.scrollWidth).toBeGreaterThan(tabGeometry.clientWidth);
  expect(["auto", "scroll"]).toContain(tabGeometry.overflowX);

  const figure = page.locator("[data-article-figure]").first();
  await expect(figure).toBeVisible();
  const figureBox = await figure.boundingBox();
  const articleBox = await page.locator(".project-article").boundingBox();
  expect(figureBox).not.toBeNull();
  expect(articleBox).not.toBeNull();
  expect(figureBox.width).toBeLessThanOrEqual(articleBox.width + 1);
  expect(await figure.locator("svg").evaluate((element) => getComputedStyle(element).minHeight)).toBe("140px");
  const figureColors = await figure.evaluate((element) => {
    const media = element.querySelector(".article-figure-media");
    const path = element.querySelector("path");
    return {
      background: getComputedStyle(media).backgroundColor,
      foreground: getComputedStyle(media).color,
      stroke: getComputedStyle(path).stroke
    };
  });
  expect(figureColors.foreground).not.toBe(figureColors.background);
  expect(figureColors.stroke).toBe(figureColors.foreground);
});
