const { test, expect } = require("./fixtures");

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
  { width: 320, height: 740 }
]) {
  test(`layout is bounded at ${viewport.width}`, async ({ page }) => {
    await page.route("**/api/atlas/projects/alpha", async (route) => {
      const response = await route.fetch();
      const project = await response.json();
      project.systemMap = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M1 1h8" /></svg>';
      await route.fulfill({ response, contentType: "application/json", body: JSON.stringify(project) });
    });
    await page.setViewportSize(viewport);
    await page.addInitScript(() => localStorage.setItem("atlas-theme", "dark"));
    await page.goto("/projects/alpha?tab=system-map");
    await expect(page.locator("[data-system-map] svg")).toBeVisible();
    await expect(page.locator("[data-system-map] script, [data-system-map] foreignObject, [data-system-map] [onload]")).toHaveCount(0);
    expect(await page.evaluate(() => window.__atlasSvgInjected)).toBeUndefined();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    const letterSpacing = await page.locator('[role="tab"]').first().evaluate((element) => getComputedStyle(element).letterSpacing);
    expect(["normal", "0px"]).toContain(letterSpacing);
    const titleSize = Number.parseFloat(await page.locator(".project-title-row h1").evaluate((element) => getComputedStyle(element).fontSize));
    expect(titleSize).toBeLessThanOrEqual(viewport.width <= 760 ? 30 : 42);
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
