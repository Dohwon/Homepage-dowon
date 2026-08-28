const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function importBrowserModule(relativePath) {
  const absolutePath = path.join(__dirname, "../..", relativePath);
  const source = await fs.readFile(absolutePath, "utf8");
  const encoded = Buffer.from(`${source}\n//# sourceURL=${pathToFileURL(absolutePath).href}`).toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

test("browser public URL helper accepts only strict public destinations", async () => {
  const { toSafePublicHref } = await importBrowserModule("client/public-url.js");

  assert.equal(toSafePublicHref("https://example.com/doc"), "https://example.com/doc");
  assert.equal(toSafePublicHref("/projects/beta", { allowRelative: true }), "/projects/beta");
  assert.equal(toSafePublicHref("#routing", { allowFragment: true }), "#routing");
  assert.equal(toSafePublicHref("/projects/beta"), "");
  assert.equal(toSafePublicHref("#routing"), "");

  for (const value of [
    "http://example.com/doc",
    "https://user:pass@example.com/doc",
    "https://localhost/doc",
    "https://foo.localhost/doc",
    "https://127.0.0.1/doc",
    "https://10.0.0.5/doc",
    "https://169.254.1.2/doc",
    "https://192.168.1.5/doc",
    "https://172.16.0.1/doc",
    "https://[::1]/doc",
    "https://[fc00::1]/doc",
    "https://[fe80::1]/doc",
    "https://[::ffff:192.168.0.1]/doc",
    "javascript:alert(1)",
    "javascript&#58;alert(1)",
    "%6a%61%76%61%73%63%72%69%70%74:alert(1)",
    "https&#58;//example.com/doc"
  ]) {
    assert.equal(toSafePublicHref(value, { allowRelative: true, allowFragment: true }), "", value);
  }
});
