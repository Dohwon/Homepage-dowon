const test = require("node:test");
const assert = require("node:assert/strict");

test("Graphify projection covers reviewed source folders and retains cross-file relations", async () => {
  const { buildPublicCodeGraph } = await import("../../scripts/export_graphify_code_graph.mjs");
  const graph = {
    nodes: [
      { id: "main", source_file: "client/main.js" },
      { id: "api", source_file: "client/api.js" },
      { id: "worker", source_file: "atlas_worker/graph.py" },
      { id: "test", source_file: "tests/worker/test_graph.py" },
      { id: "doc", source_file: "docs/design.md" },
      { id: "server", source_file: "server.js" },
      { id: "private", source_file: ".claude/CLAUDE.md" },
      { id: "generated", source_file: "public-bundle/manifest.json" }
    ],
    links: [
      { source: "main", target: "api", relation: "imports", confidence: "EXTRACTED" },
      { source: "main", target: "api", relation: "calls", confidence: "EXTRACTED" },
      { source: "worker", target: "test", relation: "references", confidence: "INFERRED" },
      { source: "main", target: "private", relation: "calls", confidence: "EXTRACTED" },
      { source: "main", target: "generated", relation: "calls", confidence: "EXTRACTED" }
    ]
  };

  const result = buildPublicCodeGraph(graph);
  assert.deepEqual(result.folders.map(folder => folder.id), ["(root)", "atlas_worker", "client", "docs", "tests"]);
  assert.deepEqual(result.nodes.filter(node => node.kind === "file").map(node => node.id), [
    "atlas_worker/graph.py", "client/api.js", "client/main.js", "docs/design.md", "server.js", "tests/worker/test_graph.py"
  ]);
  assert.deepEqual(result.edges.find(edge => edge.source === "client/main.js" && edge.target === "client/api.js"), {
    id: "client/main.js|client/api.js",
    source: "client/main.js",
    target: "client/api.js",
    kind: "relation",
    weight: 2,
    relations: ["calls", "imports"],
    confidence: "EXTRACTED"
  });
  assert.equal(result.edges.filter(edge => edge.kind === "contains").length, 6);
  assert.doesNotMatch(JSON.stringify(result), /\.claude|public-bundle|source_location/);
});
