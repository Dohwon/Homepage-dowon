const fsp = require("node:fs/promises");
const path = require("node:path");
const { assertSafePublicValue } = require("./public-content-policy");

const PUBLIC_OVERRIDE_FIELDS = new Set([
  "name",
  "summary",
  "highlights",
  "links",
  "manualOrder",
  "pinned",
  "preview"
]);
const PROJECT_SECTION_FILES = {
  buildStory: "build-story.md",
  decisions: "decisions.md",
  rollbacks: "rollbacks.md",
  visualMap: "visuals/problem-solving.svg"
};
const PROJECT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

async function readJson(filePath) {
  return JSON.parse(await fsp.readFile(filePath, "utf8"));
}

async function readOptionalText(filePath) {
  try {
    return await fsp.readFile(filePath, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return undefined;
    throw error;
  }
}

async function loadBundle(bundleDir, manifest) {
  if (!manifest || typeof manifest.version !== "string" || !Array.isArray(manifest.projects)) {
    throw new Error("invalid_atlas_manifest");
  }

  const projects = [];
  for (const id of manifest.projects) {
    if (typeof id !== "string" || !PROJECT_ID.test(id)) throw new Error("invalid_atlas_project_id");
    const projectDir = path.join(bundleDir, "projects", id);
    const record = await readJson(path.join(projectDir, "project.json"));
    if (record.id !== id) throw new Error("atlas_project_id_mismatch");

    const project = structuredClone(record);
    for (const [field, filename] of Object.entries(PROJECT_SECTION_FILES)) {
      const content = await readOptionalText(path.join(projectDir, filename));
      if (content !== undefined) project[field] = content;
    }
    projects.push(project);
  }

  const [nodes, edges, topics, changelog, searchIndex] = await Promise.all([
    readJson(path.join(bundleDir, "graph", "nodes.json")),
    readJson(path.join(bundleDir, "graph", "edges.json")),
    readJson(path.join(bundleDir, "topics.json")),
    readJson(path.join(bundleDir, "changelog.json")),
    readJson(path.join(bundleDir, "search-index.json"))
  ]);

  return {
    version: manifest.version,
    projects,
    graph: { nodes, edges },
    topics,
    changelog,
    searchIndex
  };
}

function applyCmsOverride(project, override = {}) {
  const merged = structuredClone(project);
  for (const field of PUBLIC_OVERRIDE_FIELDS) {
    if (!Object.hasOwn(override, field)) continue;
    assertSafePublicValue(override[field]);
    merged[field] = structuredClone(override[field]);
  }
  return merged;
}

function mergeCms(bundle, cms = {}) {
  const hiddenIds = new Set(
    Array.isArray(cms?.meta?.hiddenProjectIds)
      ? cms.meta.hiddenProjectIds.map(String)
      : []
  );
  const overrides = new Map(
    (Array.isArray(cms?.projects) ? cms.projects : [])
      .filter((project) => project && typeof project.id === "string")
      .map((project) => [project.id, project])
  );
  const projects = bundle.projects
    .filter((project) => !hiddenIds.has(project.id))
    .map((project) => applyCmsOverride(project, overrides.get(project.id)));
  const visibleIds = new Set(projects.map((project) => project.id));

  return {
    version: bundle.version,
    projects,
    graph: filterGraph(bundle.graph, visibleIds),
    topics: bundle.topics
      .map((topic) => ({
        ...structuredClone(topic),
        project_ids: topic.project_ids.filter((id) => visibleIds.has(id))
      }))
      .filter((topic) => topic.project_ids.length > 0),
    changelog: bundle.changelog
      .filter((entry) => visibleIds.has(entry.project_id))
      .map((entry) => structuredClone(entry)),
    searchIndex: bundle.searchIndex
      .filter((entry) => visibleIds.has(entry.project_id))
      .map((entry) => structuredClone(entry))
  };
}

function filterGraph(graph, visibleIds) {
  const hiddenProjectNodeIds = new Set(
    graph.nodes
      .filter((node) => node.kind === "project" && !visibleIds.has(node.id.replace(/^project:/, "")))
      .map((node) => node.id)
  );
  const edges = graph.edges
    .filter((edge) => !hiddenProjectNodeIds.has(edge.source) && !hiddenProjectNodeIds.has(edge.target))
    .map((edge) => structuredClone(edge));
  const connectedNodeIds = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
  const nodes = graph.nodes
    .filter((node) => {
      if (hiddenProjectNodeIds.has(node.id)) return false;
      return node.kind === "project" || connectedNodeIds.has(node.id);
    })
    .map((node) => structuredClone(node));
  return { nodes, edges };
}

function projectList(bundle) {
  return [...bundle.projects]
    .sort(compareProjects)
    .map((project) => {
      const item = structuredClone(project);
      for (const field of Object.keys(PROJECT_SECTION_FILES)) delete item[field];
      return item;
    });
}

function compareProjects(left, right) {
  if (Boolean(left.pinned) !== Boolean(right.pinned)) return left.pinned ? -1 : 1;
  const leftOrder = Number.isFinite(Number(left.manualOrder)) ? Number(left.manualOrder) : Number.POSITIVE_INFINITY;
  const rightOrder = Number.isFinite(Number(right.manualOrder)) ? Number(right.manualOrder) : Number.POSITIVE_INFINITY;
  if (leftOrder !== rightOrder) return leftOrder - rightOrder;
  return String(left.id).localeCompare(String(right.id), "en");
}

function projectById(bundle, id) {
  const project = bundle.projects.find((item) => item.id === id);
  return project ? structuredClone(project) : undefined;
}

function searchBundle(bundle, query) {
  const normalized = String(query || "").trim().toLocaleLowerCase();
  if (!normalized) return [];
  return bundle.searchIndex
    .filter((item) => [item.title, item.body, item.id].some((value) => String(value || "").toLocaleLowerCase().includes(normalized)))
    .sort((left, right) => String(left.project_id).localeCompare(String(right.project_id), "en") || String(left.id).localeCompare(String(right.id), "en"))
    .map((item) => structuredClone(item));
}

function createAtlasStore({ bundleDir, loadCmsContent = async () => ({}) }) {
  if (!bundleDir) throw new Error("atlas_bundle_dir_required");
  if (typeof loadCmsContent !== "function") throw new TypeError("loadCmsContent must be a function");

  let cachedVersion = null;
  let cachedBundle = null;

  async function load() {
    const manifest = await readJson(path.join(bundleDir, "manifest.json"));
    if (!cachedBundle || cachedVersion !== manifest.version) {
      cachedBundle = await loadBundle(bundleDir, manifest);
      cachedVersion = manifest.version;
    }
    return mergeCms(cachedBundle, await loadCmsContent());
  }

  return {
    bootstrap: async () => {
      const bundle = await load();
      return {
        version: bundle.version,
        projects: projectList(bundle),
        topics: structuredClone(bundle.topics),
        changelog: structuredClone(bundle.changelog)
      };
    },
    project: async (id) => projectById(await load(), String(id)),
    graph: async () => structuredClone((await load()).graph),
    search: async (query) => searchBundle(await load(), query)
  };
}

module.exports = {
  createAtlasStore
};
