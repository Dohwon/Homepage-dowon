const playwright = require("@playwright/test");

const cdpEndpoint = process.env.ATLAS_CDP_ENDPOINT;
const test = cdpEndpoint
  ? playwright.test.extend({
      context: async ({ playwright: engine }, use, testInfo) => {
        const browser = await engine.chromium.connectOverCDP(cdpEndpoint);
        const projectUse = testInfo.project.use || {};
        const context = await browser.newContext({
          viewport: projectUse.viewport,
          deviceScaleFactor: projectUse.deviceScaleFactor,
          isMobile: projectUse.isMobile,
          hasTouch: projectUse.hasTouch,
          userAgent: projectUse.userAgent
        });
        await use(context);
        await context.close();
      }
    })
  : playwright.test;

module.exports = { test, expect: playwright.expect };
