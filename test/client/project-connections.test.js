const test = require("node:test");
const assert = require("node:assert/strict");

test("project map distinguishes reviewed direct relations from shared specific attributes", async () => {
  const { buildProjectConnections } = await import("../../client/project-connections.js");
  const projects = ["a", "b", "c", "d"].map(id => ({ id: `project:${id}`, label: id, kind: "Project", url: `/projects/${id}` }));
  const features = ["rare-1", "rare-2", "broad"].map(id => ({ id: `tag:${id}`, label: id, kind: "KnowledgeTag" }));
  const edges = [];
  for (const id of ["a", "b", "c", "d"]) edges.push({ source: `project:${id}`, target: "tag:broad", kind: "HAS_TAG" });
  for (const id of ["a", "b"]) for (const feature of ["rare-1", "rare-2"]) edges.push({ source: `project:${id}`, target: `tag:${feature}`, kind: "HAS_TAG" });
  edges.push({ source: "project:b", target: "project:c", kind: "EVOLVED_FROM", evidence_links: [{ label: "검토된 근거", url: "/projects/b?tab=evidence" }] });

  const result = buildProjectConnections({ nodes: [...projects, ...features], edges });
  assert.equal(result.nodes.length, 4);
  assert.equal(result.edges.length, 2);
  assert.deepEqual(result.edges.find(edge => edge.kind === "SHARED").shared.map(item => item.label), ["rare-1", "rare-2"]);
  assert.deepEqual(result.edges.find(edge => edge.kind === "DIRECT").directRelations, [{
    kind: "EVOLVED_FROM", source: "project:b", target: "project:c", evidence_links: [{ label: "검토된 근거", url: "/projects/b?tab=evidence" }]
  }]);
  assert.equal(result.stats.connectedProjects, 3);
  assert.equal(result.stats.isolatedProjects, 1);
  assert.equal(result.stats.directPairs, 1);
  assert.equal(result.stats.sharedPairs, 1);
});
