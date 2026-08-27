const { test, expect } = require("./fixtures");

test("public navigation, search, theme and project tabs work", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("atlas-theme", "light"));
  await page.goto("/");
  await expect(page.locator("[data-project-card]")).toHaveCount(2);

  for (const view of ["projects", "topics", "graph", "changelog"]) {
    await page.locator(`[data-view="${view}"]:visible`).first().click();
    await expect(page).toHaveURL(new RegExp(`/${view}$`));
  }

  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await expect(page.locator("#search-dialog")).toBeVisible();
  await page.locator("#atlas-search-input").fill("routing");
  await expect(page.locator("[data-search-result]")).toHaveCount(1);
  await page.locator("[data-search-close]").click();

  await page.locator("[data-theme-toggle]").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.goto("/projects/alpha?tab=build-story");
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Build Story");
  await expect(page.locator("script[data-injected]")).toHaveCount(0);
  await expect(page.locator("[data-project-next]")).toBeVisible();
  await expect(page.locator("[data-project-toc]")).toContainText("Constraint");

  await page.goto("/projects/alpha?tab=decisions");
  await expect(page.locator(".markdown-body")).toContainText("Safe decision");
  await expect(page.locator("script[data-injected], [data-unsafe-image][onerror]")).toHaveCount(0);
  expect(await page.evaluate(() => window.__atlasInjected)).toBeUndefined();
});

test("project tab URL survives refresh", async ({ page }) => {
  await page.goto("/projects/alpha?tab=decisions");
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Decisions");
  await page.reload();
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Decisions");
});

test("arrow-key tab navigation preserves focus and tabpanel relationships", async ({ page }) => {
  await page.goto("/projects/alpha?tab=build-story");
  const selected = page.locator('[role="tab"][aria-selected="true"]');
  await selected.focus();
  await page.keyboard.press("ArrowRight");

  await expect(page).toHaveURL(/tab=decisions$/);
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Decisions");
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toBeFocused();
  await expect(page.locator('[role="tabpanel"]')).toHaveAttribute("aria-labelledby", /project-tab-decisions/);
});
