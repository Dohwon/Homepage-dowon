const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function importGraphModule() {
  const absolutePath = path.join(__dirname, "../..", "client/graph-view.js");
  const source = await fs.readFile(absolutePath, "utf8");
  const encoded = Buffer.from(`${source}\n//# sourceURL=${pathToFileURL(absolutePath).href}`).toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

test("large project sets use a readable two-column inner layout", async () => {
  const { layoutNodes } = await importGraphModule();
  const projects = Array.from({ length: 33 }, (_, index) => ({
    id: `project:${index}`,
    kind: "project",
    label: `Project ${index}`,
  }));
  const topics = Array.from({ length: 20 }, (_, index) => ({
    id: `domain:${index}`,
    kind: "domain",
    label: `Domain ${index}`,
  }));

  const laidOut = layoutNodes([...projects, ...topics], 1117, 688);
  const projectNodes = laidOut.filter((node) => node.kind === "project");

  assert.equal(new Set(projectNodes.map((node) => node.x)).size, 2);
  assert.equal(new Set(projectNodes.map((node) => node.y)).size, 17);
  assert.equal(projectNodes[0].x, 1117 * 0.3);
  assert.equal(projectNodes[1].x, 1117 * 0.7);
  assert.equal(projectNodes[0].labelSide, "left");
  assert.equal(projectNodes[1].labelSide, "right");
  assert.equal(projectNodes[0].labelLimit, 24);
});

test("actual-scale topic sets keep node circles from overlapping", async () => {
  const { layoutNodes } = await importGraphModule();
  const projects = Array.from({ length: 33 }, (_, index) => ({
    id: `project:${index}`,
    kind: "project",
    label: `Project ${index}`,
  }));
  const topics = Array.from({ length: 241 }, (_, index) => ({
    id: `topic:${index}`,
    kind: "domain",
    label: `Topic ${index}`,
  }));

  const laidOut = layoutNodes([...projects, ...topics], 640, 480);
  const topicNodes = laidOut.filter((node) => node.kind !== "project");
  let minimumDistance = Number.POSITIVE_INFINITY;
  for (let left = 0; left < topicNodes.length; left += 1) {
    for (let right = left + 1; right < topicNodes.length; right += 1) {
      minimumDistance = Math.min(
        minimumDistance,
        Math.hypot(
          topicNodes[left].x - topicNodes[right].x,
          topicNodes[left].y - topicNodes[right].y,
        ),
      );
    }
  }

  assert.ok(minimumDistance >= 18, `minimum topic distance was ${minimumDistance}`);
});

test("visible labels truncate without changing short names", async () => {
  const { visibleNodeLabel } = await importGraphModule();

  assert.equal(visibleNodeLabel("Short project", 28), "Short project");
  assert.equal(visibleNodeLabel("A project name that is deliberately too long", 18), "A project name th…");
});
