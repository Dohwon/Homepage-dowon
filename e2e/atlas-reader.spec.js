const { test, expect } = require("./fixtures");
const { PNG } = require("pngjs");

function nonDominantPixelCount(png) {
  const counts = new Map();
  for (let index = 0; index < png.data.length; index += 4) {
    const key = `${png.data[index]}:${png.data[index + 1]}:${png.data[index + 2]}:${png.data[index + 3]}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const dominant = Math.max(...counts.values());
  return { colorCount: counts.size, pixels: (png.width * png.height) - dominant };
}

async function readProgressScale(page) {
  return page.locator("#reading-progress").evaluate((element) => {
    const transform = getComputedStyle(element).transform;
    if (transform === "none") return 0;
    return new DOMMatrixReadOnly(transform).a;
  });
}

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

test("reader figure pixels are nonblank and article progress stays bounded", async ({ page }) => {
  await installLongDecisionArticle(page);
  await page.goto("/projects/alpha");

  const svg = page.locator("[data-article-figure] svg").first();
  await expect(svg).toBeVisible();
  const png = PNG.sync.read(await svg.screenshot());
  const ink = nonDominantPixelCount(png);
  expect(ink.colorCount).toBeGreaterThan(1);
  expect(ink.pixels).toBeGreaterThan(Math.max(64, png.width * png.height * 0.002));

  const progress = page.locator("#reading-progress");
  await expect(progress).toHaveAttribute("data-active", "");
  const samples = [await readProgressScale(page)];
  expect(samples[0]).toBeLessThanOrEqual(0.02);

  const article = page.locator("[data-project-reader]");
  const articleEnd = await article.evaluate((element) => element.offsetTop + element.offsetHeight);
  await scrollInstantly(page, articleEnd);
  await expect.poll(() => readProgressScale(page)).toBeGreaterThanOrEqual(0.98);
  samples.push(await readProgressScale(page));

  for (const value of samples) {
    expect(Number.isFinite(value)).toBeTruthy();
    expect(value).toBeGreaterThanOrEqual(0);
    expect(value).toBeLessThanOrEqual(1);
  }
});

test("project tabs and visible TOC preserve keyboard focus and section hash", async ({ page }) => {
  await installLongDecisionArticle(page);
  await page.goto("/projects/alpha");

  const decisions = page.locator("#project-tab-decisions");
  await decisions.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#project-tab-system-map")).toBeFocused();
  await expect(page).toHaveURL(/\?tab=system-map$/);

  await page.keyboard.press("Home");
  await expect(page.locator("#project-tab-decisions")).toBeFocused();
  await expect(page).toHaveURL(/\/projects\/alpha$/);

  const mobileToc = page.locator("[data-project-toc-mobile]");
  if (await mobileToc.isVisible()) {
    await mobileToc.locator("summary").click();
  }
  const tocLink = page.locator("[data-project-toc]:visible a[href='#section-2']");
  await tocLink.focus();
  await expect(tocLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/projects\/alpha#section-2$/);
  await expect(tocLink).toHaveAttribute("aria-current", "location");
});
