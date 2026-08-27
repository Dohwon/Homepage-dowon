const { test, expect } = require("./fixtures");

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`layout is bounded at ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => localStorage.setItem("atlas-theme", "dark"));
    await page.goto("/projects/alpha?tab=visual-map");
    await expect(page.locator("[data-project-map] svg")).toBeVisible();
    await expect(page.locator("[data-project-map] script, [data-project-map] foreignObject, [data-project-map] [onload]")).toHaveCount(0);
    expect(await page.evaluate(() => window.__atlasSvgInjected)).toBeUndefined();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    const letterSpacing = await page.locator('[role="tab"]').first().evaluate((element) => getComputedStyle(element).letterSpacing);
    expect(["normal", "0px"]).toContain(letterSpacing);
  });
}

test("mobile navigation is visible without covering the document", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects");
  await expect(page.locator("#mobile-nav")).toBeVisible();
  const lastCard = page.locator("[data-project-card]").last();
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const cardBox = await lastCard.boundingBox();
  const navBox = await page.locator("#mobile-nav").boundingBox();
  expect(cardBox.y + cardBox.height).toBeLessThanOrEqual(navBox.y + 1);
});
