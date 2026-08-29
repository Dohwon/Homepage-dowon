const { test, expect } = require("./fixtures");

async function installLongDecisionArticle(page) {
  await page.route("**/api/atlas/projects/alpha", async (route) => {
    const response = await route.fetch();
    const project = await response.json();
    project.visuals ||= {};
    project.visuals["routing-flow"] = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90"><path d="M20 45h120" fill="none" stroke="currentColor" stroke-width="8" /></svg>';
    project.article.sections = Array.from({ length: 8 }, (_, index) => ({
      id: `section-${index + 1}`,
      title: index === 0
        ? "DecisionTitleWithAnIntentionallyLongUnbrokenIdentifierThatMustWrapInsideTheReaderAt320Pixels"
        : `Decision section ${index + 1}`,
      section_type: "decision",
      body: `${"This section records the public decision context and validation outcome. ".repeat(8)}\n\n\`implementation-contract-with-a-deliberately-long-token-${index + 1}\``,
      evidence_ids: [],
      diagrams: index === 1 ? [{ id: "routing-flow", alt: "Routing flow", caption: "Public routing flow" }] : []
    }));
    await route.fulfill({ response, contentType: "application/json", body: JSON.stringify(project) });
  });
}

async function scrollInstantly(page, top) {
  const target = await page.evaluate((requestedTop) => {
    document.documentElement.style.scrollBehavior = "auto";
    const maxTop = document.documentElement.scrollHeight - window.innerHeight;
    const settledTop = Math.max(0, Math.min(requestedTop, maxTop));
    window.scrollTo({ top: settledTop, left: 0, behavior: "auto" });
    return settledTop;
  }, top);
  await page.waitForFunction((expectedTop) => Math.abs(window.scrollY - expectedTop) <= 1, target);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

test("desktop TOC stays left of the article below the sticky rails", async ({ page }) => {
  await installLongDecisionArticle(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/projects/alpha");

  const toc = page.locator("[data-project-toc-desktop]");
  const article = page.locator(".project-article");
  const tabs = page.locator("[data-project-tab-rail]");
  await expect(toc).toBeVisible();
  await expect(page.locator("[data-project-toc-mobile]")).toBeHidden();

  await scrollInstantly(page, 900);
  const before = await toc.boundingBox();
  await scrollInstantly(page, 1400);
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
  await expect(page.locator(".primary-nav")).toBeHidden();
  await expect(page.locator("#mobile-nav")).toBeVisible();
  const visibleGlobalNavs = await page.locator(".primary-nav, #mobile-nav").evaluateAll((elements) => elements.filter((element) => {
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden";
  }).length);
  expect(visibleGlobalNavs).toBe(1);
  const mobileNavHeight = await page.locator("#mobile-nav").evaluate((element) => element.getBoundingClientRect().height);
  const bodyBottomClearance = await page.locator("body").evaluate((element) => Number.parseFloat(getComputedStyle(element).paddingBottom));
  expect(bodyBottomClearance).toBeGreaterThanOrEqual(mobileNavHeight);
  await scrollInstantly(page, 1_000_000);
  const pagerBox = await page.locator(".project-pager").boundingBox();
  const mobileNavBox = await page.locator("#mobile-nav").boundingBox();
  expect(pagerBox).not.toBeNull();
  expect(mobileNavBox).not.toBeNull();
  expect(pagerBox.y + pagerBox.height).toBeLessThanOrEqual(mobileNavBox.y + 1);

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

  const longHeading = page.locator("#section-1 > h2");
  await expect(longHeading).toBeVisible();
  const headingGeometry = await longHeading.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    overflowWrap: getComputedStyle(element).overflowWrap
  }));
  expect(headingGeometry.scrollWidth).toBeLessThanOrEqual(headingGeometry.clientWidth + 1);
  expect(headingGeometry.overflowWrap).toBe("anywhere");

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
