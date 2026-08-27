const { defineConfig, devices } = require("@playwright/test");
const path = require("node:path");

const root = __dirname;
const executablePath = process.env.ATLAS_CHROMIUM_EXECUTABLE;

module.exports = defineConfig({
  testDir: path.join(root, "e2e"),
  globalSetup: path.join(root, "e2e", "global-setup.js"),
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4182",
    launchOptions: executablePath ? { executablePath } : {},
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: {
    command: "node server.js",
    url: "http://127.0.0.1:4182/api/health",
    cwd: root,
    env: {
      PORT: "4182",
      HOST: "127.0.0.1",
      ATLAS_BUNDLE_DIR: path.join(root, "test", "fixtures", "public-bundle"),
      PORTFOLIO_DATA_DIR: path.join(root, ".atlas-test-data"),
      DEV_ALLOW_LOCAL_LOGIN: "true",
      DEV_ADMIN_EMAIL: "admin@example.com"
    },
    reuseExistingServer: false,
    timeout: 30_000
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    {
      name: "mobile-chromium",
      use: {
        browserName: "chromium",
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true
      }
    }
  ]
});
