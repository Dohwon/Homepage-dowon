const { test, expect } = require("./fixtures");
const { PNG } = require("pngjs");

test("graph renders, filters, zooms and fits", async ({ page }) => {
  await page.goto("/graph");
  const graph = page.locator("#knowledge-graph");
  await expect(graph).toHaveAttribute("role", "group");
  await expect(graph.locator('[data-node-type="Project"]')).toHaveCount(2);
  await expect(graph.locator('[data-node-type="Project"]').first()).toHaveAttribute("role", "button");

  const projectLabel = graph.locator('[data-node-type="Project"] text').first();
  const topicNode = graph.locator('[data-node-type="Domain"]').first();
  const topicLabel = topicNode.locator("text");
  await expect(projectLabel).toHaveCSS("opacity", "1");
  await expect(topicLabel).toHaveCSS("opacity", "0");
  const topicBox = await topicNode.locator("circle").boundingBox();
  await page.mouse.move(topicBox.x + topicBox.width / 2, topicBox.y + topicBox.height / 2);
  await expect(topicLabel).toHaveCSS("opacity", "1");
  await topicNode.focus();
  await expect(topicLabel).toHaveCSS("opacity", "1");

  const before = await graph.locator("#graph-viewport").getAttribute("transform");
  const box = await graph.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -500);
  await expect.poll(() => graph.locator("#graph-viewport").getAttribute("transform")).not.toBe(before);

  await page.locator("[data-graph-fit]").click();
  await expect(page.locator("[data-graph-status]")).toContainText("전체 보기");

  const graphBox = await graph.boundingBox();
  for (const node of await graph.locator('[data-node-type="Project"]').all()) {
    const nodeBox = await node.boundingBox();
    expect(nodeBox.x).toBeGreaterThanOrEqual(graphBox.x - 1);
    expect(nodeBox.y).toBeGreaterThanOrEqual(graphBox.y - 1);
    expect(nodeBox.x + nodeBox.width).toBeLessThanOrEqual(graphBox.x + graphBox.width + 1);
    expect(nodeBox.y + nodeBox.height).toBeLessThanOrEqual(graphBox.y + graphBox.height + 1);
  }

  const png = PNG.sync.read(await graph.screenshot());
  const colors = new Set();
  for (let index = 0; index < png.data.length; index += 4) {
    colors.add(`${png.data[index]}:${png.data[index + 1]}:${png.data[index + 2]}:${png.data[index + 3]}`);
  }
  expect(colors.size).toBeGreaterThan(10);

  await page.locator('[data-graph-filter][value="domain"]').uncheck();
  await expect(graph.locator('[data-node-type="Domain"]')).toHaveCount(0);
});
