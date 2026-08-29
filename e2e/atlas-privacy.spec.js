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

test("browser strips hostile markdown urls and svg markup without navigation", async ({ page }) => {
  await page.route("**/api/atlas/projects/alpha", async (route) => {
    const response = await route.fetch();
    const project = await response.json();
    project.article = {
      ...project.article,
      prior_context: '<a id="unsafe-entity" href="javascript&#58;window.__atlasInjected=1">bad entity</a>',
      sections: [{
        ...project.article.sections[0],
        body: [
          '<a id="unsafe-unquoted" href=javascript:window.__atlasInjected=1>bad unquoted</a>',
          '<a id="unsafe-encoded" href="%6a%61%76%61%73%63%72%69%70%74:window.__atlasInjected=1">bad encoded</a>',
          '<a id="unsafe-localhost" href="https://foo.localhost/private">bad localhost</a>',
          '<a id="unsafe-ipv6" href="https://[::1]/private">bad ipv6</a>',
          '<a id="unsafe-creds" href="https://user:pass@example.com/private">bad creds</a>',
          '<a id="safe-relative" href="/projects/beta">safe relative</a>',
          '<a id="safe-fragment" href="#routing">safe fragment</a>',
          '<a id="safe-public" href="https://example.com/doc">safe public</a>',
          '<form id="unsafe-action-quoted" action="https://foo.local/private"><button type="button">bad quoted action</button></form>',
          '<form id="unsafe-action-unquoted" action=https://foo.internal/private><button type="button">bad unquoted action</button></form>',
          '<form id="unsafe-action-entity" action="https://foo&#46;local/private"><button type="button">bad entity action</button></form>',
          '<form id="unsafe-action-encoded" action="%68%74%74%70%73://example.com/private"><button type="button">bad encoded action</button></form>',
          '<form id="safe-action" action="https://example.com/submit"><button type="button">safe action</button></form>',
          '<button id="unsafe-formaction" formaction="https://foo.local/private">bad formaction</button>',
          '<img id="unsafe-image" src=javascript:window.__atlasImage=1 onerror="window.__atlasImage=1" />'
        ].join("\n")
      }]
    };
    project.systemMap = [
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" onload="window.__atlasSvgInjected=1">',
      '<script>window.__atlasSvgScript=1</script>',
      '<foreignObject><div>unsafe</div></foreignObject>',
      '<animate attributeName="x" from="0" to="10" dur="1s" repeatCount="indefinite" />',
      '<set attributeName="fill" to="red" />',
      '<use href="https://evil.example/asset.svg#shape"></use>',
      '<image href="javascript:window.__atlasSvgImage=1" width="1" height="1"></image>',
      '<g onclick="window.__atlasSvgClick=1"><path d="M1 1h8" /></g>',
      "</svg>"
    ].join("");
    await route.fulfill({ response, contentType: "application/json", body: JSON.stringify(project) });
  });

  await page.goto("/projects/alpha?tab=decisions");
  await expect(page.locator("#safe-relative")).toHaveAttribute("href", "/projects/beta");
  await expect(page.locator("#safe-fragment")).toHaveAttribute("href", "#routing");
  await expect(page.locator("#safe-public")).toHaveAttribute("href", "https://example.com/doc");
  await expect(page.locator("#safe-action")).toHaveAttribute("action", "https://example.com/submit");

  for (const selector of ["#unsafe-entity", "#unsafe-unquoted", "#unsafe-encoded", "#unsafe-localhost", "#unsafe-ipv6", "#unsafe-creds"]) {
    await expect(page.locator(selector)).not.toHaveAttribute("href", /.+/);
  }
  for (const selector of ["#unsafe-action-quoted", "#unsafe-action-unquoted", "#unsafe-action-entity", "#unsafe-action-encoded"]) {
    await expect(page.locator(selector)).not.toHaveAttribute("action", /.+/);
  }
  await expect(page.locator("#unsafe-formaction")).not.toHaveAttribute("formaction", /.+/);
  await expect(page.locator(".decision-article [onerror], .decision-article [onclick], .decision-article [src^=\"javascript:\"], .decision-article [href^=\"javascript:\"]")).toHaveCount(0);
  const before = page.url();
  await page.locator("#unsafe-unquoted").click();
  await expect(page).toHaveURL(before);
  await page.locator("#unsafe-localhost").click();
  await expect(page).toHaveURL(before);
  await page.locator("#unsafe-formaction").click();
  await expect(page).toHaveURL(before);
  expect(await page.evaluate(() => ({ injected: window.__atlasInjected, image: window.__atlasImage }))).toEqual({
    injected: undefined,
    image: undefined
  });

  await page.goto("/projects/alpha?tab=system-map");
  await expect(page.locator("[data-system-map] svg")).toBeVisible();
  await expect(page.locator("[data-system-map] script, [data-system-map] foreignObject, [data-system-map] animate, [data-system-map] set, [data-system-map] use, [data-system-map] image, [data-system-map] [onload], [data-system-map] [onclick], [data-system-map] [href], [data-system-map] [xlink\\:href]")).toHaveCount(0);
  expect(await page.evaluate(() => ({
    injected: window.__atlasSvgInjected,
    script: window.__atlasSvgScript,
    image: window.__atlasSvgImage,
    click: window.__atlasSvgClick
  }))).toEqual({
    injected: undefined,
    script: undefined,
    image: undefined,
    click: undefined
  });
});
