const { test, expect } = require("./fixtures");

test("public navigation, search, theme and project tabs work", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("atlas-theme", "light"));
  await page.goto("/");
  await expect(page.locator(".brand-mark")).toHaveText("👩‍💻");
  await expect(page.locator(".page-heading h1.sr-only")).toHaveText("Project knowledge base");
  await expect(page.locator("[data-project-card]")).toHaveCount(2);

  const viewCopy = {
    projects: "프로젝트 별 결과/결정, 작업 지도",
    topics: "도메인, 문제, 작업 패턴, 기술 결과 별 태그 모음",
    graph: "프로젝트와 공통 주제를 연결해 반복되는 문제와 작업 패턴을 보여줍니다.",
    changelog: "프로젝트 변경점 기록"
  };
  for (const [view, description] of Object.entries(viewCopy)) {
    await page.locator(`[data-view="${view}"]:visible`).first().click();
    await expect(page).toHaveURL(new RegExp(`/${view}$`));
    await expect(page.locator(".page-heading h1.sr-only")).toHaveCount(1);
    await expect(page.locator(".page-heading-copy")).toContainText(description);
    if (view === "projects") {
      await expect(page.locator("[data-project-count]")).toHaveText("전체 2");
    }
  }

  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await expect(page.locator("#search-dialog")).toBeVisible();
  await page.locator("#atlas-search-input").fill("routing");
  await expect(page.locator("[data-search-result]")).toHaveCount(1);
  await page.locator("[data-search-close]").click();

  await page.locator("[data-theme-toggle]").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.goto("/projects/alpha?tab=build-timeline");
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Build Timeline");
  await expect(page.locator('[role="tab"]')).toHaveText(["Decisions", "System Map", "Build Timeline", "Evidence"]);
  await expect(page.locator("[data-project-next]")).toBeVisible();
  await expect(page.locator('[role="tabpanel"]')).toContainText("Published routing record");

  await page.goto("/projects/alpha?tab=decisions");
  await expect(page.locator(".decision-article")).toContainText("The routing decision is published as a deterministic public contract.");
  await expect(page.locator("script[data-injected], [data-unsafe-image][onerror]")).toHaveCount(0);
  expect(await page.evaluate(() => window.__atlasInjected)).toBeUndefined();
});

test("project tab URL survives refresh", async ({ page }) => {
  await page.goto("/projects/alpha?tab=decisions");
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Decisions");
  await page.reload();
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Decisions");
});

test("decision section hashes survive reload, back and forward navigation", async ({ page }) => {
  await page.goto("/projects/alpha#routing");
  await expect(page.locator('[data-project-toc] a[href="#routing"]')).toHaveAttribute("aria-current", "location");
  await expect(page).toHaveURL(/\/projects\/alpha#routing$/);

  await page.reload();
  await expect(page.locator('[data-project-toc] a[href="#routing"]')).toHaveAttribute("aria-current", "location");

  await page.getByRole("tab", { name: "Evidence" }).click();
  await expect(page).toHaveURL(/\?tab=evidence$/);
  await page.goBack();
  await expect(page).toHaveURL(/#routing$/);
  await expect(page.locator('[data-project-toc] a[href="#routing"]')).toHaveAttribute("aria-current", "location");
  await page.goForward();
  await expect(page).toHaveURL(/\?tab=evidence$/);
  await expect(page.getByRole("tab", { name: "Evidence" })).toHaveAttribute("aria-selected", "true");
});

test("malformed decision hashes fail safely", async ({ page }) => {
  await page.goto("/projects/alpha#%E0%A4%A");
  await expect(page.locator("[data-project-reader]")).toBeVisible();
  await expect(page.locator('[data-project-toc] [aria-current="location"]')).toHaveCount(0);
});

test("arrow-key tab navigation preserves focus and tabpanel relationships", async ({ page }) => {
  await page.goto("/projects/alpha?tab=build-timeline");
  const selected = page.locator('[role="tab"][aria-selected="true"]');
  await selected.focus();
  await page.keyboard.press("ArrowRight");

  await expect(page).toHaveURL(/tab=evidence$/);
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Evidence");
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toBeFocused();
  await expect(page.locator('[role="tabpanel"]')).toHaveAttribute("aria-labelledby", /project-tab-evidence/);
});

test("pager and graph project routes land on Decisions", async ({ page }) => {
  await page.goto("/projects/alpha?tab=system-map");
  await page.locator("[data-project-next]").click();
  await expect(page).toHaveURL(/\/projects\/beta$/);
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Decisions");

  await page.goto("/graph");
  await page.locator('#knowledge-graph [data-node-type="Project"]').first().click();
  await expect(page).toHaveURL(/\/projects\/alpha$/);
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText("Decisions");
});
