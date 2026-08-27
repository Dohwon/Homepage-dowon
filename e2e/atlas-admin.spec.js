const { test, expect } = require("./fixtures");

test("preserved CMS can log in, create, and delete a project", async ({ page }, testInfo) => {
  const projectId = `cms-${testInfo.project.name}`;
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/admin.html");
  await expect(page.locator("#project-grid [data-project-id]").first()).toBeVisible();

  await page.locator('[data-auth-action="dev-login"]').click();
  await expect(page.locator("#new-project-button")).toBeVisible();
  await page.locator("#new-project-button").click();
  await page.locator('#project-editor-form [name="id"]').fill(projectId);
  await page.locator('#project-editor-form [name="name"]').fill("CMS Browser Regression");
  await page.locator('#project-editor-form [name="category"]').fill("QA");
  await page.locator('#project-editor-form [name="summary"]').fill("Browser-level CMS regression fixture");
  await page.locator('#project-editor-form button[type="submit"]').click();

  const card = page.locator(`[data-project-id="${projectId}"]`);
  await expect(card).toBeVisible();
  await card.locator('[data-card-action="delete"]').click();
  await expect(card).toHaveCount(0);
});
