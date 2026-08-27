const { test, expect } = require("./fixtures");

test("public responses contain no local paths or private session fields", async ({ request }) => {
  for (const path of ["/api/atlas/bootstrap", "/api/atlas/projects/alpha", "/api/atlas/graph"]) {
    const response = await request.get(path);
    expect(response.ok()).toBeTruthy();
    const text = await response.text();
    expect(text).not.toContain("/home/dowon");
    expect(text).not.toMatch(/sessions|provenance|\.jsonl/i);
  }
});

test("public bundle files cannot be fetched directly", async ({ request }) => {
  const response = await request.get("/public-bundle/manifest.json");
  expect(response.status()).toBe(404);
});
