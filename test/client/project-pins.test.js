const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function importBrowserModule() {
  const source = await fs.readFile(path.join(__dirname, "../..", "client/project-pins.js"), "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

function storage(initial = "[]") {
  let value = initial;
  return {
    getItem() { return value; },
    setItem(_key, next) { value = next; },
    value() { return value; }
  };
}

test("project pins persist toggles and keep IDs normalized", async () => {
  const { loadPinnedProjectIds, toggleProjectPinned } = await importBrowserModule();
  const fakeStorage = storage('["beta", "", 4, "beta"]');

  assert.deepEqual([...loadPinnedProjectIds(fakeStorage)], ["beta"]);
  toggleProjectPinned("alpha", true, fakeStorage);
  assert.equal(fakeStorage.value(), '["alpha","beta"]');
  toggleProjectPinned("beta", false, fakeStorage);
  assert.equal(fakeStorage.value(), '["alpha"]');
});

test("pinned projects move ahead of the stable project order", async () => {
  const { sortPinnedProjects } = await importBrowserModule();
  const projects = [{ id: "a" }, { id: "b", pinned: true }, { id: "c" }, { id: "d" }];

  assert.deepEqual(sortPinnedProjects(projects, new Set(["d"])).map((project) => project.id), ["b", "d", "a", "c"]);
});
