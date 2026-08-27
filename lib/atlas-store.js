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
const GRAPH_NODE_KINDS = new Set(["project", "domain", "problem", "pattern", "technology", "outcome"]);
const GRAPH_EDGE_KINDS = new Set(["tag-membership", "project-similarity"]);
const TAG_LIMITS = {
  domain: [1, 2],
  problem: [1, 3],
  pattern: [1, 3],
  technology: [0, 12],
  outcome: [1, 2]
};
const PUBLIC_PROJECT_FIELDS = new Set([
  "id",
  "name",
  "lifecycle",
  "publication",
  "summary",
  "tags",
  "outcome",
  "aliases"
]);
const PUBLIC_RECORD_FIELDS = {
  node: new Set(["id", "label", "kind"]),
  edge: new Set(["source", "target", "kind", "weight", "reasons"]),
  topic: new Set(["kind", "label", "project_ids"]),
  change: new Set(["project_id", "event_id", "title", "stage", "context", "decision", "outcome", "date"]),
  search: new Set(["id", "project_id", "title", "body", "url"])
};
const EMPTY_BUNDLE = {
  version: "unavailable",
  projects: [],
  graph: { nodes: [], edges: [] },
  topics: [],
  changelog: [],
  searchIndex: []
};

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

function copyPublicRecord(record, allowedFields, errorCode) {
  if (!record || typeof record !== "object" || Array.isArray(record)) throw new Error(errorCode);
  for (const field of Object.keys(record)) {
    if (!allowedFields.has(field)) throw new Error(errorCode);
  }
  return structuredClone(record);
}

function copyPublicRecords(records, allowedFields, errorCode) {
  if (!Array.isArray(records)) throw new Error(errorCode);
  return records.map((record) => copyPublicRecord(record, allowedFields, errorCode));
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.length > 0;
}

function isStringArray(value, { minimum = 0, maximum = Number.POSITIVE_INFINITY } = {}) {
  return Array.isArray(value)
    && value.length >= minimum
    && value.length <= maximum
    && value.every(isNonEmptyString);
}

function validateTags(tags) {
  if (!tags || typeof tags !== "object" || Array.isArray(tags)) return false;
  if (Object.keys(tags).length !== Object.keys(TAG_LIMITS).length) return false;
  return Object.entries(TAG_LIMITS).every(([kind, [minimum, maximum]]) => (
    Object.hasOwn(tags, kind) && isStringArray(tags[kind], { minimum, maximum })
  ));
}

function validatePublicProject(record) {
  const project = copyPublicRecord(record, PUBLIC_PROJECT_FIELDS, "invalid_atlas_project_field");
  const valid = PROJECT_ID.test(project.id)
    && isNonEmptyString(project.name)
    && new Set(["active", "finished"]).has(project.lifecycle)
    && project.publication === "public"
    && isNonEmptyString(project.summary)
    && validateTags(project.tags)
    && (project.outcome === undefined || typeof project.outcome === "string")
    && (project.aliases === undefined || isStringArray(project.aliases));
  if (!valid) throw new Error("invalid_atlas_project");
  return project;
}

function validateGraphNode(record) {
  const node = copyPublicRecord(record, PUBLIC_RECORD_FIELDS.node, "invalid_atlas_graph_node");
  if (!isNonEmptyString(node.id) || !isNonEmptyString(node.label) || !GRAPH_NODE_KINDS.has(node.kind)) {
    throw new Error("invalid_atlas_graph_node");
  }
  return node;
}

function validateGraphEdge(record) {
  const edge = copyPublicRecord(record, PUBLIC_RECORD_FIELDS.edge, "invalid_atlas_graph_edge");
  const valid = isNonEmptyString(edge.source)
    && isNonEmptyString(edge.target)
    && GRAPH_EDGE_KINDS.has(edge.kind)
    && Number.isInteger(edge.weight)
    && edge.weight > 0
    && isStringArray(edge.reasons);
  if (!valid) throw new Error("invalid_atlas_graph_edge");
  return edge;
}

function validateTopic(record, projectIds) {
  const topic = copyPublicRecord(record, PUBLIC_RECORD_FIELDS.topic, "invalid_atlas_topic");
  const valid = GRAPH_NODE_KINDS.has(topic.kind)
    && topic.kind !== "project"
    && isNonEmptyString(topic.label)
    && isStringArray(topic.project_ids, { minimum: 1 })
    && topic.project_ids.every((id) => projectIds.has(id));
  if (!valid) throw new Error("invalid_atlas_topic");
  return topic;
}

function validateChange(record, projectIds) {
  const change = copyPublicRecord(record, PUBLIC_RECORD_FIELDS.change, "invalid_atlas_change");
  const valid = projectIds.has(change.project_id)
    && ["event_id", "title", "stage"].every((field) => isNonEmptyString(change[field]))
    && ["context", "decision", "outcome"].every((field) => typeof change[field] === "string")
    && (change.date === undefined || /^\d{4}-\d{2}-\d{2}$/.test(change.date));
  if (!valid) throw new Error("invalid_atlas_change");
  return change;
}

function validateSearchRecord(record, projectIds) {
  const search = copyPublicRecord(record, PUBLIC_RECORD_FIELDS.search, "invalid_atlas_search_record");
  const valid = ["id", "project_id", "title", "url"].every((field) => isNonEmptyString(search[field]))
    && typeof search.body === "string"
    && projectIds.has(search.project_id)
    && search.url.startsWith("/projects/");
  if (!valid) throw new Error("invalid_atlas_search_record");
  return search;
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

    const project = validatePublicProject(record);
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

  const projectIds = new Set(projects.map((project) => project.id));
  const bundle = {
    version: manifest.version,
    projects,
    graph: {
      nodes: copyPublicRecords(nodes, PUBLIC_RECORD_FIELDS.node, "invalid_atlas_graph_node").map(validateGraphNode),
      edges: copyPublicRecords(edges, PUBLIC_RECORD_FIELDS.edge, "invalid_atlas_graph_edge").map(validateGraphEdge)
    },
    topics: copyPublicRecords(topics, PUBLIC_RECORD_FIELDS.topic, "invalid_atlas_topic").map((topic) => validateTopic(topic, projectIds)),
    changelog: copyPublicRecords(changelog, PUBLIC_RECORD_FIELDS.change, "invalid_atlas_change").map((change) => validateChange(change, projectIds)),
    searchIndex: copyPublicRecords(searchIndex, PUBLIC_RECORD_FIELDS.search, "invalid_atlas_search_record").map((record) => validateSearchRecord(record, projectIds))
  };
  assertSafePublicValue(bundle);
  return bundle;
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
    let manifest;
    try {
      manifest = await readJson(path.join(bundleDir, "manifest.json"));
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      return mergeCms(EMPTY_BUNDLE, await loadCmsContent());
    }
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
