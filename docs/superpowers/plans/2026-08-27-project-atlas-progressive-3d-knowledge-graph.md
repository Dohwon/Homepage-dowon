# Project Atlas Progressive 3D Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unreadable tag-similarity graph with a progressive Three.js/WebGL knowledge graph that reuses the useful interactions from the old LLM Wiki and shows only evidence-backed relationships.

**Architecture:** A deterministic Python projector builds a public KG from curated taxonomy, project profiles, public evidence, and explicit project relations. A pure client graph-state module decides which nodes and edges are expanded; the 3D renderer only displays that state. `3d-force-graph` supplies Three.js rendering, force layout, camera controls, node drag, and incremental graph updates, while a searchable hierarchy provides a fail-safe fallback.

**Tech Stack:** Python 3.10+, JSON Schema, pytest, `3d-force-graph` 1.80.0, Three.js/WebGL through the pinned library bundle, vanilla ES modules, Node test runner, Playwright, pngjs

**Spec:** `docs/superpowers/specs/2026-08-27-project-atlas-content-graph-redesign.md`

**Prerequisite:** Complete `2026-08-27-project-atlas-knowledge-content-foundation.md` first so graph artifacts and relation evidence use the same public bundle contract.

## Global Constraints

- Canonical node types are `KnowledgeFocus`, `KnowledgeDomain`, `KnowledgeTag`, `Project`, `Technology`, and `Artifact`.
- Canonical base edge types are `HAS_FOCUS`, `FOCUS_HAS_TAG`, `HAS_SUBTAG`, `HAS_TAG`, `USES_TECH`, `PRODUCES_ARTIFACT`, and `ARTIFACT_HAS_TAG`.
- Optional direct project relations are only `EVOLVED_FROM`, `VALIDATES`, `DEPLOYS`, and `REUSES_COMPONENT`, each backed by curated evidence.
- `project-similarity` edges are forbidden and must total zero in the public bundle.
- Similar names, shared tags, version suffixes, and shared Git remotes never create direct project edges.
- Initial rendering shows KnowledgeFocus and connected Project nodes; Focus and Project clicks progressively expand exact neighborhoods.
- Search reveals a minimal root-to-target path; inactive nodes and edges dim instead of disappearing without context.
- No Neo4j, hosted graph database, CDN, external graph API, or unattended model call is introduced.
- WebGL failure produces an accessible searchable hierarchy.
- Reduced-motion mode settles quickly and never auto-rotates.
- Desktop and mobile canvas pixel checks must prove nonblank rendering without overlap or clipping.

The renderer dependency and its Three.js/WebGL behavior are documented by the [3d-force-graph official repository](https://github.com/vasturiano/3d-force-graph) and [Three.js WebGLRenderer documentation](https://threejs.org/docs/pages/WebGLRenderer.html). Version `1.80.0` is pinned in `package-lock.json`; no CDN URL is shipped.

---

## Planned File Structure

```text
data/
└── knowledge-taxonomy.yaml        # reviewed public focus/domain/tag hierarchy
atlas_worker/
├── models.py                      # KG node and edge literals
├── kg.py                          # public KG projector
├── article.py                     # optional curated relation loading
└── bundle.py                      # exact KG bundle validation
schemas/
└── public-graph.schema.json
scripts/
├── import_llm_wiki_graph.py       # one-time reviewed migration helper
└── vendor_client_assets.mjs       # local 3d-force-graph bundle
client/
├── graph-state.js                 # graph index, expansion, filters, minimal path
├── graph-view.js                  # 3D renderer adapter and lifecycle
└── render.js                      # graph controls, detail panel, fallback
test/client/
├── graph-state.test.js
└── graph-view.test.js
tests/worker/
└── test_kg.py
e2e/
└── atlas-graph.spec.js
```

### Task 1: Public KG Contract and Curated Projector

**Files:**
- Modify: `atlas_worker/models.py`
- Create: `atlas_worker/kg.py`
- Create: `schemas/public-graph.schema.json`
- Create: `data/knowledge-taxonomy.yaml`
- Create: `tests/worker/test_kg.py`
- Modify: `tests/worker/test_taxonomy_graph.py`

**Interfaces:**
- Consumes: public projects, article evidence, curated `relations.yaml`, and `data/knowledge-taxonomy.yaml`.
- Produces: `build_knowledge_graph(projects, articles, evidence, relations, taxonomy) -> GraphData` and strict public node/edge projections.

- [ ] **Step 1: Write failing KG type and no-similarity tests**

```python
def test_kg_uses_six_node_types_and_no_similarity_edges(projects, taxonomy):
    graph = build_knowledge_graph(projects, {}, {}, {}, taxonomy)
    assert {node.kind for node in graph.nodes} <= {
        "KnowledgeFocus", "KnowledgeDomain", "KnowledgeTag",
        "Project", "Technology", "Artifact",
    }
    assert "project-similarity" not in {edge.kind for edge in graph.edges}
    assert all(edge.kind in GRAPH_EDGE_KINDS for edge in graph.edges)


def test_shared_tags_do_not_create_direct_project_edge(project_factory, taxonomy):
    left = project_factory("left", domain=("Mobility",), technology=("JavaScript",))
    right = project_factory("right", domain=("Mobility",), technology=("JavaScript",))
    graph = build_knowledge_graph((left, right), {}, {}, {}, taxonomy)
    project_pairs = {
        frozenset((edge.source_id, edge.target_id))
        for edge in graph.edges
        if edge.source_id.startswith("project:") and edge.target_id.startswith("project:")
    }
    assert project_pairs == set()


def test_curated_project_relation_requires_public_evidence(projects, taxonomy):
    relations = {"left": [{"type": "EVOLVED_FROM", "target": "right", "evidence_ids": ["missing"]}]}
    with pytest.raises(ValueError, match="graph-relation-evidence"):
        build_knowledge_graph(projects, {}, {}, relations, taxonomy)
```

- [ ] **Step 2: Run the KG tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_kg.py tests/worker/test_taxonomy_graph.py -q`

Expected: FAIL because the existing graph uses tag kinds and `project-similarity`.

- [ ] **Step 3: Replace graph literals and define the reviewed taxonomy**

```python
GraphNodeKind = Literal[
    "KnowledgeFocus", "KnowledgeDomain", "KnowledgeTag",
    "Project", "Technology", "Artifact",
]
GraphEdgeKind = Literal[
    "HAS_FOCUS", "FOCUS_HAS_TAG", "HAS_SUBTAG", "HAS_TAG",
    "USES_TECH", "PRODUCES_ARTIFACT", "ARTIFACT_HAS_TAG",
    "EVOLVED_FROM", "VALIDATES", "DEPLOYS", "REUSES_COMPONENT",
]

@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    kind: GraphEdgeKind
    weight: int = 1
    evidence_links: tuple[dict[str, str], ...] = ()

    @property
    def edge_id(self) -> str:
        return f"{self.kind.lower()}:{quote(self.source_id, safe='')}:{quote(self.target_id, safe='')}"
```

The taxonomy YAML has stable IDs and explicit parent references:

```yaml
focuses:
  - id: product-delivery
    label: Product Delivery
  - id: ai-quality
    label: AI Quality
domains:
  - id: mobility
    label: Mobility
    focus_id: product-delivery
  - id: evaluation
    label: Evaluation
    focus_id: ai-quality
tags:
  - id: evaluation-benchmarking
    label: Evaluation / Benchmarking
    domain_id: evaluation
```

Populate this file by reviewing old LLM Wiki focus/domain/tag labels and current public profiles. Unknown project labels fail audit and enter review; they are not assigned to a guessed focus.

- [ ] **Step 4: Implement deterministic graph projection**

```python
def build_knowledge_graph(projects, articles, evidence, relations, taxonomy):
    nodes = taxonomy_nodes(taxonomy)
    edges = taxonomy_edges(taxonomy)
    for project in sorted(projects, key=lambda item: item.project_id):
        nodes.add(project_node(project))
        for domain in project.tags.domain:
            domain_id = taxonomy.require_domain(domain)
            edges.add(GraphEdge(project_node_id(project.project_id), focus_node_id(taxonomy.focus_for(domain_id)), "HAS_FOCUS", 1))
            edges.add(GraphEdge(project_node_id(project.project_id), domain_node_id(domain_id), "HAS_TAG", 1))
        for technology in project.tags.technology:
            nodes.add(technology_node(technology))
            edges.add(GraphEdge(project_node_id(project.project_id), technology_node_id(technology), "USES_TECH", 1))
        add_public_artifacts(nodes, edges, project, evidence.get(project.project_id, ()))
        add_curated_relations(nodes, edges, project, relations.get(project.project_id, ()), evidence)
    return GraphData(tuple(sorted(nodes, key=node_key)), tuple(sorted(edges, key=edge_key)))
```

Map existing `problem`, `pattern`, and `outcome` profile labels to `KnowledgeTag` nodes through reviewed taxonomy aliases. Never cap nodes by count. Validate duplicate IDs, missing endpoints, self-relations, relation evidence, and exact edge kinds.

Run: `.venv/bin/python -m pytest tests/worker/test_kg.py tests/worker/test_taxonomy_graph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the KG contract**

```bash
git add atlas_worker/models.py atlas_worker/kg.py schemas/public-graph.schema.json data/knowledge-taxonomy.yaml tests/worker/test_kg.py tests/worker/test_taxonomy_graph.py
git commit -m "feat: project evidence-backed Atlas knowledge graph"
```

### Task 2: Bundle and Server Validation for the New KG

**Files:**
- Modify: `atlas_worker/bundle.py`
- Modify: `atlas_worker/cli.py`
- Modify: `lib/atlas-store.js`
- Modify: `tests/worker/test_bundle.py`
- Modify: `tests/worker/test_cli.py`
- Modify: `test/server/atlas-store.test.js`
- Modify: `test/fixtures/public-bundle/graph/nodes.json`
- Modify: `test/fixtures/public-bundle/graph/edges.json`

**Interfaces:**
- Consumes: `GraphData` from Task 1.
- Produces: public graph records with node fields `id`, `label`, `kind`, `url`, `summary`; edge fields `id`, `source`, `target`, `kind`, `weight`, `evidence_links`.

- [ ] **Step 1: Add failing server and bundle tests**

```python
def test_bundle_rejects_every_similarity_edge_even_when_rehashed(valid_bundle, gate):
    edge_path = valid_bundle / "graph/edges.json"
    edges = json.loads(edge_path.read_text())
    edges.append({
        "id": "similarity:left:right", "source": "project:left", "target": "project:right",
        "kind": "project-similarity", "weight": 1, "evidence_links": [],
    })
    rewrite_manifest_hashes(valid_bundle)
    with pytest.raises(ValueError, match="graph-edge-kind"):
        validate_bundle(valid_bundle, gate)
```

```javascript
test("server accepts KG records and strips no allowed relation evidence", async () => {
  const graph = await createStore().graph();
  assert.deepEqual(new Set(graph.nodes.map(node => node.kind)), new Set(["KnowledgeFocus", "Project", "KnowledgeDomain"]));
  assert.equal(graph.edges.some(edge => edge.kind === "project-similarity"), false);
  assert.deepEqual(graph.edges[0].evidence_links, [{ label: "Routing spec", url: "/projects/alpha?tab=evidence" }]);
});
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_bundle.py tests/worker/test_cli.py -q`

Run: `node --test test/server/atlas-store.test.js`

Expected: FAIL against old kind allowlists and record shapes.

- [ ] **Step 3: Update exact record allowlists and graph filtering**

```javascript
const GRAPH_NODE_KINDS = new Set([
  "KnowledgeFocus", "KnowledgeDomain", "KnowledgeTag", "Project", "Technology", "Artifact"
]);
const GRAPH_EDGE_KINDS = new Set([
  "HAS_FOCUS", "FOCUS_HAS_TAG", "HAS_SUBTAG", "HAS_TAG", "USES_TECH",
  "PRODUCES_ARTIFACT", "ARTIFACT_HAS_TAG", "EVOLVED_FROM", "VALIDATES", "DEPLOYS", "REUSES_COMPONENT"
]);
const PUBLIC_RECORD_FIELDS = {
  node: new Set(["id", "label", "kind", "url", "summary"]),
  edge: new Set(["id", "source", "target", "kind", "weight", "evidence_links"]),
  // existing topic, change, and search records remain unchanged
};
```

When CMS hides a project, remove its incident edges, then remove orphaned `Artifact`, `Technology`, and `KnowledgeTag` nodes. Keep curated Focus and Domain nodes so fallback navigation remains stable.

- [ ] **Step 4: Verify exact graph contract and privacy**

Run: `.venv/bin/python -m pytest tests/worker/test_bundle.py tests/worker/test_cli.py tests/worker/test_privacy.py -q`

Run: `node --test test/server/atlas-store.test.js test/server/atlas-api.test.js`

Expected: PASS. Unsafe evidence links or labels reject the whole candidate.

- [ ] **Step 5: Commit the public KG boundary**

```bash
git add atlas_worker/bundle.py atlas_worker/cli.py lib/atlas-store.js tests/worker/test_bundle.py tests/worker/test_cli.py test/server/atlas-store.test.js test/fixtures/public-bundle/graph
git commit -m "feat: validate public Atlas KG records"
```

### Task 3: Progressive Expansion State and Minimal Paths

**Files:**
- Create: `client/graph-state.js`
- Create: `test/client/graph-state.test.js`

**Interfaces:**
- Consumes: immutable public graph `{ nodes, edges }`.
- Produces: `createGraphIndex(graph)`, `initialGraphState(index)`, `expandNode(state, nodeId, index)`, `revealPath(state, nodeId, index)`, `setRelationFilters(state, kinds)`, and `visibleGraph(state, index)`.

- [ ] **Step 1: Write failing initial, one-hop, path, and filter tests**

```javascript
test("initial graph shows only focuses and connected projects", async () => {
  const index = createGraphIndex(fixtureGraph());
  const visible = visibleGraph(initialGraphState(index), index);
  assert.deepEqual(visible.nodes.map(node => node.id).sort(), ["focus:delivery", "project:alpha", "project:beta"]);
  assert.deepEqual(new Set(visible.links.map(link => link.kind)), new Set(["HAS_FOCUS"]));
});

test("project expansion adds exact tag technology and artifact neighbors", async () => {
  const index = createGraphIndex(fixtureGraph());
  const state = expandNode(initialGraphState(index), "project:alpha", index);
  assert.deepEqual(
    visibleGraph(state, index).nodes.map(node => node.id).sort(),
    ["artifact:alpha:report", "focus:delivery", "project:alpha", "project:beta", "tag:routing", "technology:python"]
  );
});

test("search reveals a deterministic shortest path from a focus", async () => {
  const index = createGraphIndex(fixtureGraph());
  const state = revealPath(initialGraphState(index), "artifact:alpha:report", index);
  assert.deepEqual(state.revealedPath, ["focus:delivery", "project:alpha", "artifact:alpha:report"]);
});

test("relation filter never invents replacement edges", async () => {
  const index = createGraphIndex(fixtureGraph());
  const state = setRelationFilters(initialGraphState(index), new Set(["USES_TECH"]));
  assert.equal(visibleGraph(state, index).links.every(link => link.kind === "USES_TECH"), true);
});
```

- [ ] **Step 2: Run graph-state tests and verify failure**

Run: `node --test test/client/graph-state.test.js`

Expected: FAIL importing `client/graph-state.js`.

- [ ] **Step 3: Implement immutable adjacency and expansion rules**

```javascript
const PROJECT_EXPANSION = new Set(["HAS_TAG", "USES_TECH", "PRODUCES_ARTIFACT", "EVOLVED_FROM", "VALIDATES", "DEPLOYS", "REUSES_COMPONENT"]);
const FOCUS_EXPANSION = new Set(["FOCUS_HAS_TAG", "HAS_SUBTAG"]);

export function initialGraphState(index) {
  const visible = new Set(index.nodesByKind.get("KnowledgeFocus") || []);
  for (const edge of index.edges) {
    if (edge.kind === "HAS_FOCUS") {
      visible.add(edge.source);
      visible.add(edge.target);
    }
  }
  return Object.freeze({ visibleNodeIds: visible, selectedId: null, expandedIds: new Set(), relationKinds: new Set(index.edgeKinds), revealedPath: [] });
}

export function expandNode(state, nodeId, index) {
  const node = index.nodes.get(nodeId);
  const allowed = node?.kind === "Project" ? PROJECT_EXPANSION : node?.kind === "KnowledgeFocus" ? FOCUS_EXPANSION : new Set();
  const visible = new Set(state.visibleNodeIds);
  for (const edge of index.adjacency.get(nodeId) || []) {
    if (allowed.has(edge.kind)) {
      visible.add(edge.source);
      visible.add(edge.target);
    }
  }
  return freezeGraphState({ ...state, visibleNodeIds: visible, selectedId: nodeId, expandedIds: new Set([...state.expandedIds, nodeId]) });
}
```

Use stable breadth-first traversal ordered by edge kind and node ID for `revealPath`. `visibleGraph` marks `active` on the selected neighborhood and `dimmed` elsewhere; it does not mutate source records.

- [ ] **Step 4: Run graph-state tests**

Run: `node --test test/client/graph-state.test.js`

Expected: PASS, including cyclic-graph and missing-target cases.

- [ ] **Step 5: Commit progressive graph state**

```bash
git add client/graph-state.js test/client/graph-state.test.js
git commit -m "feat: add progressive Atlas graph expansion"
```

### Task 4: Pin and Vendor the 3D Renderer

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Modify: `scripts/vendor_client_assets.mjs`
- Modify: `index.html`
- Replace: `client/graph-view.js`
- Replace: `test/client/graph-view.test.js`

**Interfaces:**
- Consumes: visible graph data from Task 3 and injected `ForceGraph3D` factory.
- Produces: `supportsWebGL(document)`, `createGraphView(container, graph, options)`, and methods `update`, `focus`, `fit`, `reset`, `destroy`.

- [ ] **Step 1: Write failing adapter and lifecycle tests**

```javascript
test("3D adapter configures orbit controls and incremental graph updates", async () => {
  const fake = fakeForceGraph();
  const view = createGraphView(container(), fixtureGraph(), { forceGraphFactory: fake.factory });
  assert.equal(fake.config.controlType, "orbit");
  assert.equal(fake.calls.graphData.length, 1);
  view.update(expandedGraph());
  assert.equal(fake.calls.graphData.length, 2);
  view.destroy();
  assert.equal(fake.calls.pauseAnimation, 1);
  assert.equal(fake.calls.destructor, 1);
});

test("WebGL capability check fails closed", async () => {
  const document = fakeDocument({ webgl: false });
  assert.equal(supportsWebGL(document), false);
});
```

- [ ] **Step 2: Pin the dependency and verify the old SVG test fails**

Run: `npm install 3d-force-graph@1.80.0 --save-exact`

Run: `node --test test/client/graph-view.test.js`

Expected: FAIL because `createGraphView` still expects an SVG and has no injected 3D factory.

- [ ] **Step 3: Vendor the locked browser bundle locally**

Add this entry to `vendorFiles`:

```javascript
["node_modules/3d-force-graph/dist/3d-force-graph.min.js", "vendor/3d-force-graph.min.js"]
```

Load `/vendor/3d-force-graph.min.js` before `/client/main.js` in `index.html`. No CDN or dynamic remote import is permitted. Run `npm run vendor` and confirm `vendor/3d-force-graph.min.js` exists.

- [ ] **Step 4: Implement the renderer adapter**

```javascript
export function createGraphView(container, graph, {
  forceGraphFactory = (element, config) => new globalThis.ForceGraph3D(element, config),
  onSelect = () => {},
  reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches
} = {}) {
  if (typeof forceGraphFactory !== "function") throw new Error("force_graph_3d_unavailable");
  const instance = forceGraphFactory(container, { controlType: "orbit", rendererConfig: { antialias: true, alpha: true } })
    .nodeId("id")
    .linkSource("source")
    .linkTarget("target")
    .nodeLabel(node => node.active || node.kind === "KnowledgeFocus" ? `${node.label} · ${node.kind}` : "")
    .nodeColor(node => NODE_COLORS[node.kind])
    .nodeOpacity(node => node.dimmed ? 0.18 : 0.92)
    .linkOpacity(link => link.dimmed ? 0.05 : 0.42)
    .onNodeClick(node => onSelect(node))
    .onNodeDragEnd(node => { node.fx = node.x; node.fy = node.y; node.fz = node.z; })
    .cooldownTicks(reducedMotion ? 18 : 80)
    .warmupTicks(reducedMotion ? 12 : 0)
    .graphData(toRendererData(graph));
  if (reducedMotion) instance.d3AlphaDecay(0.3);
  return {
    update(next) { instance.graphData(toRendererData(next)); },
    focus(node) { focusCamera(instance, node, reducedMotion ? 0 : 700); },
    fit() { instance.zoomToFit(reducedMotion ? 0 : 500, 70); },
    reset() { instance.graphData(toRendererData(graph)); instance.zoomToFit(0, 70); },
    destroy() { instance.pauseAnimation(); instance._destructor?.(); container.replaceChildren(); }
  };
}
```

Do not enable auto-rotation. Configure a fixed canvas container size before construction and call `width`/`height` from a `ResizeObserver` without recreating the instance.

Run: `npm run vendor`

Run: `node --test test/client/graph-view.test.js`

Expected: PASS.

- [ ] **Step 5: Commit the local 3D renderer**

```bash
git add package.json package-lock.json scripts/vendor_client_assets.mjs vendor/3d-force-graph.min.js index.html client/graph-view.js test/client/graph-view.test.js
git commit -m "feat: vendor Atlas Three.js graph renderer"
```

### Task 5: Graph Controls, Search, Detail Panel, and Fallback

**Files:**
- Modify: `client/render.js`
- Modify: `client/main.js`
- Modify: `styles.css`
- Modify: `test/client/graph-state.test.js`
- Modify: `e2e/atlas-graph.spec.js`

**Interfaces:**
- Consumes: KG API, graph-state functions, and 3D renderer adapter.
- Produces: relation menu, node search, Fit, Reset, legend, selected-node relation panel, project article link, and WebGL fallback.

- [ ] **Step 1: Add failing interaction and fallback E2E tests**

```javascript
test("graph starts collapsed and expands one project neighborhood", async ({ page }) => {
  await page.goto("/graph");
  await expect(page.locator("[data-graph-node-count]")).toHaveText("3");
  await page.locator('[data-graph-search]').fill("Alpha");
  await page.locator('[data-graph-search-result="project:alpha"]').click();
  await expect(page.locator("[data-selected-node]")).toContainText("Alpha");
  await expect(page.locator("[data-graph-node-count]")).toHaveText("6");
  await expect(page.locator('[data-project-article-link]')).toHaveAttribute("href", "/projects/alpha");
});

test("WebGL failure renders searchable hierarchy", async ({ page }) => {
  await page.addInitScript(() => { HTMLCanvasElement.prototype.getContext = () => null; });
  await page.goto("/graph");
  await expect(page.locator("[data-graph-fallback]")).toBeVisible();
  await page.locator('[data-graph-fallback-search]').fill("Alpha");
  await expect(page.locator('[data-fallback-node="project:alpha"]')).toBeVisible();
});
```

- [ ] **Step 2: Run graph E2E and verify failure**

Run: `npm run test:ui -- e2e/atlas-graph.spec.js`

Expected: FAIL against the old SVG layout and type checkboxes.

- [ ] **Step 3: Render controls and progressive state**

The graph toolbar contains icon buttons for Fit (`maximize-2`) and Reset (`rotate-ccw`), a search input, and a relation menu with checkboxes. Node-type colors appear as swatches, not text buttons. Each unfamiliar icon has `aria-label`, `title`, and a stable 42px square.

`bindGraph` owns one graph state. Selection calls `expandNode`; search calls `revealPath`; relation changes call `setRelationFilters`; each update calls `view.update(visibleGraph(state, index))`. The panel lists relation type, neighbor label, public evidence links, and the selected project's `/projects/<id>` link.

- [ ] **Step 4: Add fallback hierarchy and responsive panel**

```javascript
function renderGraphFallback(graph) {
  const focuses = graph.nodes.filter(node => node.kind === "KnowledgeFocus");
  return `<section class="graph-fallback" data-graph-fallback>
    <label class="graph-search"><span class="sr-only">그래프 노드 검색</span><input type="search" data-graph-fallback-search></label>
    ${focuses.map(focus => `<details open><summary>${escapeHtml(focus.label)}</summary>${fallbackBranch(focus, graph)}</details>`).join("")}
  </section>`;
}
```

Desktop uses canvas plus a 320px detail rail. Mobile uses a full-width canvas and bottom detail sheet below it. Fallback links are keyboard accessible and route to project articles. Reduced-motion is exposed through `data-reduced-motion` for E2E assertions.

Run: `node --test test/client/graph-state.test.js test/client/graph-view.test.js`

Run: `npm run test:ui -- e2e/atlas-graph.spec.js`

Expected: PASS.

- [ ] **Step 5: Commit graph interaction UI**

```bash
git add client/render.js client/main.js styles.css test/client/graph-state.test.js e2e/atlas-graph.spec.js
git commit -m "feat: add progressive Atlas graph exploration"
```

### Task 6: Old LLM Wiki Migration Audit and Visual Gate

**Files:**
- Create: `scripts/import_llm_wiki_graph.py`
- Create: `tests/worker/test_llm_wiki_graph_import.py`
- Modify: `e2e/atlas-graph.spec.js`
- Modify: `README.md`

**Interfaces:**
- Consumes: `projects/llm_wiki/knowledge-graph/nodes.csv`, `edges.csv`, and the reviewed taxonomy.
- Produces: read-only migration report with accepted, rejected, and unmapped node/edge counts; no direct bundle write.

- [ ] **Step 1: Write a failing read-only importer test**

```python
def test_importer_reports_old_graph_without_creating_similarity_or_family_edges(tmp_path, old_graph_fixture):
    report = audit_llm_wiki_graph(old_graph_fixture, reviewed_taxonomy())
    assert report.accepted_node_types == {
        "KnowledgeFocus", "KnowledgeDomain", "KnowledgeTag", "Project", "Technology", "Artifact"
    }
    assert "SHARES_FOCUS" in report.rejected_edge_types
    assert "project-similarity" not in report.output_edge_types
    assert not list(tmp_path.rglob("*.json"))
```

- [ ] **Step 2: Run importer tests and verify failure**

Run: `.venv/bin/python -m pytest tests/worker/test_llm_wiki_graph_import.py -q`

Expected: FAIL importing the migration helper.

- [ ] **Step 3: Implement audit-only CSV import**

The script normalizes the six approved old node types and seven approved base edge types. It rejects `SHARES_FOCUS`, name-derived links, unknown project IDs, missing endpoints, and raw evidence paths. It prints stable JSON counts and suggested taxonomy aliases; it never modifies `data/knowledge-taxonomy.yaml` automatically.

Run: `.venv/bin/python scripts/import_llm_wiki_graph.py --source /home/dowon/securedir/git/codex/projects/llm_wiki --taxonomy data/knowledge-taxonomy.yaml --format json`

Expected: exit `0`, no traceback, no source mutation, and explicit rejected-relation counts.

- [ ] **Step 4: Add canvas pixel and control-overlap checks**

```javascript
test("3D graph canvas is nonblank on desktop and mobile", async ({ page }) => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/graph");
    const canvas = page.locator("[data-graph-canvas] canvas");
    await expect(canvas).toBeVisible();
    await expect.poll(async () => nonBackgroundPixelCount(PNG.sync.read(await canvas.screenshot()))).toBeGreaterThan(500);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  }
});
```

Also test zoom, pan, rotate, node drag, Fit, Reset, relation filter, search path, reduced motion, and project navigation. Assert the initial visible count is less than total KG node count.

- [ ] **Step 5: Run and commit the graph gate**

Run: `.venv/bin/python -m pytest tests/worker/test_kg.py tests/worker/test_llm_wiki_graph_import.py -q`

Run: `npm test`

Run: `npm run test:ui -- e2e/atlas-graph.spec.js`

Expected: every command exits `0`.

```bash
git add scripts/import_llm_wiki_graph.py tests/worker/test_llm_wiki_graph_import.py e2e/atlas-graph.spec.js README.md
git commit -m "test: verify Atlas 3D graph migration"
```

## Completion Gate

- [ ] Confirm `public-bundle/graph/edges.json` contains zero `project-similarity` and zero `SHARES_FOCUS` records.
- [ ] Confirm first render displays Focus and Project nodes but not every KG node.
- [ ] Confirm Focus and Project expansion, minimal-path search, relation filters, Fit, Reset, zoom, pan, rotate, drag, and project links work.
- [ ] Confirm WebGL fallback and reduced-motion behavior pass.
- [ ] Confirm desktop and mobile canvas screenshots are nonblank and controls do not overlap.
- [ ] Confirm all graph packages are locked locally and no CDN reference exists.
