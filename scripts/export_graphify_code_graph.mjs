import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import publicPolicy from "../lib/public-content-policy.js";

// The Atlas website is public. Project-only instructions, generated bundles,
// datasets and third-party packages must stay out of its Graphify projection.
const PUBLIC_FOLDERS = new Set([
  "atlas_worker", "client", "deploy", "docs", "e2e", "lib", "schemas", "scripts", "test", "tests"
]);
const PUBLIC_ROOT_FILES = new Set([
  "README.md", "admin.js", "app.js", "package.json", "playwright.config.js", "railway.json", "server.js"
]);
const RELATIONS = new Set([
  "calls", "dynamic_import", "imports", "imports_from", "indirect_call", "inherits", "re_exports", "references", "uses"
]);

function publicFile(value) {
  if (typeof value !== "string" || !value || value.startsWith("/") || value.includes("\\")) return false;
  const segments = value.split("/");
  if (segments.some(segment => !segment || segment === "." || segment === ".." || segment.startsWith(".") || segment === "public-bundle" || segment === "fixtures")) return false;
  return segments.length === 1 ? PUBLIC_ROOT_FILES.has(value) : PUBLIC_FOLDERS.has(segments[0]);
}

function folderOf(file) {
  return file.includes("/") ? file.split("/")[0] : "(root)";
}

export function buildPublicCodeGraph(graph) {
  if (!Array.isArray(graph?.nodes) || !Array.isArray(graph?.links)) throw new TypeError("invalid_graphify_graph");
  const sourceById = new Map(graph.nodes.map(node => [node.id, node.source_file]));
  const files = new Map();
  for (const node of graph.nodes) {
    const file = node.source_file;
    if (!publicFile(file)) continue;
    const record = files.get(file) || { id: file, label: path.posix.basename(file), kind: "file", folder: folderOf(file), symbols: 0 };
    record.symbols += 1;
    files.set(file, record);
  }
  const fileNodes = [...files.values()].sort((a, b) => a.id.localeCompare(b.id));
  const folderCounts = new Map();
  for (const node of fileNodes) folderCounts.set(node.folder, (folderCounts.get(node.folder) || 0) + 1);
  const folders = [...folderCounts].sort(([a], [b]) => a.localeCompare(b)).map(([id, fileCount]) => ({ id, fileCount }));
  const folderNodes = folders.map(folder => ({
    id: `folder:${folder.id}`, label: folder.id, kind: "folder", folder: folder.id, fileCount: folder.fileCount
  }));
  const pairs = new Map();
  for (const link of graph.links) {
    if (!RELATIONS.has(link.relation) || !new Set(["EXTRACTED", "INFERRED"]).has(link.confidence)) continue;
    const source = sourceById.get(link.source);
    const target = sourceById.get(link.target);
    if (!files.has(source) || !files.has(target) || source === target) continue;
    const id = `${source}|${target}`;
    const pair = pairs.get(id) || { id, source, target, kind: "relation", weight: 0, relations: new Set(), extracted: false };
    pair.weight += 1;
    pair.relations.add(link.relation);
    if (link.confidence === "EXTRACTED") pair.extracted = true;
    pairs.set(id, pair);
  }
  const relationEdges = [...pairs.values()].sort((a, b) => a.id.localeCompare(b.id)).map(pair => ({
    id: pair.id, source: pair.source, target: pair.target, kind: pair.kind,
    weight: pair.weight, relations: [...pair.relations].sort(),
    confidence: pair.extracted ? "EXTRACTED" : "INFERRED"
  }));
  const containsEdges = fileNodes.map(node => ({
    id: `folder:${node.folder}|${node.id}`, source: `folder:${node.folder}`, target: node.id,
    kind: "contains", weight: 1, relations: ["contains"], confidence: "EXTRACTED"
  }));
  return publicPolicy.assertSafePublicValue({
    schemaVersion: 2,
    source: "Graphify AST",
    corpus: { nodes: graph.nodes.length, edges: graph.links.length },
    folders,
    nodes: [...folderNodes, ...fileNodes],
    edges: [...containsEdges, ...relationEdges]
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
  const source = path.join(root, "graphify-out", "graph.json");
  const destination = path.join(root, "data", "code-graph-public.json");
  const graph = buildPublicCodeGraph(JSON.parse(await readFile(source, "utf8")));
  await writeFile(destination, `${JSON.stringify(graph, null, 2)}\n`, "utf8");
  process.stdout.write(`Wrote ${graph.nodes.length} nodes, ${graph.edges.length} edges and ${graph.folders.length} folders to ${destination}\n`);
}
