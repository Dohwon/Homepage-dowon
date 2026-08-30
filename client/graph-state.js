const PROJECT_EXPANSION = new Set([
  "HAS_TAG",
  "USES_TECH",
  "PRODUCES_ARTIFACT",
  "EVOLVED_FROM",
  "VALIDATES",
  "DEPLOYS",
  "REUSES_COMPONENT",
]);

const FOCUS_EXPANSION = new Set(["FOCUS_HAS_TAG", "HAS_SUBTAG"]);

function rejectReadonlyMutation() {
  throw new TypeError("read-only graph collection");
}

function readonlyCollection(collection, mutationMethods) {
  let facade;
  facade = new Proxy(collection, {
    get(target, property) {
      if (mutationMethods.includes(property)) return rejectReadonlyMutation;
      if (property === "valueOf") return () => facade;
      if (property === "forEach") {
        return (callback, thisArg) => target.forEach(
          (value, key) => callback.call(thisArg, value, key, facade),
        );
      }
      const value = Reflect.get(target, property, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
    set: rejectReadonlyMutation,
    defineProperty: rejectReadonlyMutation,
    deleteProperty: rejectReadonlyMutation,
  });
  return Object.freeze(facade);
}

function readonlySet(values) {
  return readonlyCollection(new Set(values), ["add", "delete", "clear"]);
}

function readonlyMap(entries) {
  return readonlyCollection(new Map(entries), ["set", "delete", "clear"]);
}

function freezeNodeRecord(node) {
  return Object.freeze({ ...node });
}

function freezeEdgeRecord(edge) {
  const clone = { ...edge };
  if (Array.isArray(clone.evidence_links)) {
    clone.evidence_links = Object.freeze(
      clone.evidence_links.map((link) => Object.freeze({ ...link })),
    );
  }
  return Object.freeze(clone);
}

function neighborId(edge, nodeId) {
  return edge.source === nodeId ? edge.target : edge.source;
}

function compareStrings(left, right) {
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

function compareAdjacentEdges(nodeId, left, right) {
  return compareStrings(left.kind, right.kind)
    || compareStrings(neighborId(left, nodeId), neighborId(right, nodeId))
    || compareStrings(left.id, right.id);
}

function freezeGraphState(state) {
  return Object.freeze({
    ...state,
    visibleNodeIds: readonlySet(state.visibleNodeIds),
    visibleEdgeIds: readonlySet(state.visibleEdgeIds),
    expandedIds: readonlySet(state.expandedIds),
    relationKinds: readonlySet(state.relationKinds),
    revealedPath: Object.freeze([...state.revealedPath]),
  });
}

export function createGraphIndex(graph) {
  const nodes = new Map();
  const nodesByKind = new Map();
  const edges = (graph?.edges || []).map(freezeEdgeRecord);
  const adjacency = new Map();

  for (const sourceNode of graph?.nodes || []) {
    const node = freezeNodeRecord(sourceNode);
    nodes.set(node.id, node);
    const ids = nodesByKind.get(node.kind) || [];
    ids.push(node.id);
    nodesByKind.set(node.kind, ids);
    adjacency.set(node.id, []);
  }

  for (const edge of edges) {
    if (!nodes.has(edge.source) || !nodes.has(edge.target)) continue;
    adjacency.get(edge.source).push(edge);
    adjacency.get(edge.target).push(edge);
  }

  for (const [nodeId, adjacentEdges] of adjacency) {
    adjacentEdges.sort((left, right) => compareAdjacentEdges(nodeId, left, right));
    adjacency.set(nodeId, Object.freeze(adjacentEdges));
  }

  for (const [kind, ids] of nodesByKind) {
    nodesByKind.set(kind, Object.freeze(ids));
  }

  return Object.freeze({
    nodes: readonlyMap(nodes),
    nodesByKind: readonlyMap(nodesByKind),
    edges: Object.freeze(edges),
    adjacency: readonlyMap(adjacency),
    edgeKinds: readonlySet(edges.map((edge) => edge.kind)),
  });
}

export function initialGraphState(index) {
  const visibleNodeIds = new Set(index.nodesByKind.get("KnowledgeFocus") || []);
  const visibleEdgeIds = new Set();
  for (const edge of index.edges) {
    if (edge.kind !== "HAS_FOCUS") continue;
    if (!index.nodes.has(edge.source) || !index.nodes.has(edge.target)) continue;
    visibleNodeIds.add(edge.source);
    visibleNodeIds.add(edge.target);
    visibleEdgeIds.add(edge.id);
  }

  return freezeGraphState({
    visibleNodeIds,
    visibleEdgeIds,
    selectedId: null,
    expandedIds: new Set(),
    relationKinds: index.edgeKinds,
    revealedPath: [],
  });
}

export function expandNode(state, nodeId, index) {
  const node = index.nodes.get(nodeId);
  const allowedKinds = node?.kind === "Project"
    ? PROJECT_EXPANSION
    : node?.kind === "KnowledgeFocus"
      ? FOCUS_EXPANSION
      : new Set();
  const visibleNodeIds = new Set(state.visibleNodeIds);
  const visibleEdgeIds = new Set(state.visibleEdgeIds);

  for (const edge of index.adjacency.get(nodeId) || []) {
    if (!allowedKinds.has(edge.kind)) continue;
    visibleNodeIds.add(edge.source);
    visibleNodeIds.add(edge.target);
    visibleEdgeIds.add(edge.id);
  }

  return freezeGraphState({
    ...state,
    visibleNodeIds,
    visibleEdgeIds,
    selectedId: nodeId,
    expandedIds: new Set([...state.expandedIds, nodeId]),
  });
}

function shortestPathFromFocus(nodeId, index) {
  if (!index.nodes.has(nodeId)) return null;
  const focusIds = [...(index.nodesByKind.get("KnowledgeFocus") || [])].sort();
  if (focusIds.includes(nodeId)) return { nodeIds: [nodeId], edgeIds: [] };

  const visited = new Set(focusIds);
  const queue = focusIds.map((focusId) => ({ nodeIds: [focusId], edgeIds: [] }));
  let cursor = 0;

  while (cursor < queue.length) {
    const path = queue[cursor];
    cursor += 1;
    const currentId = path.nodeIds[path.nodeIds.length - 1];

    for (const edge of index.adjacency.get(currentId) || []) {
      const nextId = neighborId(edge, currentId);
      if (visited.has(nextId)) continue;
      const nextPath = {
        nodeIds: [...path.nodeIds, nextId],
        edgeIds: [...path.edgeIds, edge.id],
      };
      if (nextId === nodeId) return nextPath;
      visited.add(nextId);
      queue.push(nextPath);
    }
  }

  return null;
}

export function revealPath(state, nodeId, index) {
  const path = shortestPathFromFocus(nodeId, index);
  if (!path) return state;

  return freezeGraphState({
    ...state,
    visibleNodeIds: new Set([...state.visibleNodeIds, ...path.nodeIds]),
    visibleEdgeIds: new Set([...state.visibleEdgeIds, ...path.edgeIds]),
    selectedId: nodeId,
    revealedPath: path.nodeIds,
  });
}

export function setRelationFilters(state, kinds) {
  return freezeGraphState({
    ...state,
    relationKinds: new Set(kinds || []),
  });
}

function selectedNeighborhood(state, index) {
  if (!state.selectedId || !index.nodes.has(state.selectedId)) {
    return new Set(state.visibleNodeIds);
  }

  const activeNodeIds = new Set([state.selectedId]);
  for (const edge of index.adjacency.get(state.selectedId) || []) {
    if (!state.visibleEdgeIds.has(edge.id)) continue;
    if (!state.relationKinds.has(edge.kind)) continue;
    activeNodeIds.add(edge.source);
    activeNodeIds.add(edge.target);
  }
  return activeNodeIds;
}

export function visibleGraph(state, index) {
  const activeNodeIds = selectedNeighborhood(state, index);
  const nodes = [];

  for (const node of index.nodes.values()) {
    if (!state.visibleNodeIds.has(node.id)) continue;
    const active = activeNodeIds.has(node.id);
    nodes.push({ ...node, active, dimmed: !active });
  }

  const links = [];
  for (const edge of index.edges) {
    if (!state.visibleEdgeIds.has(edge.id)) continue;
    if (!state.relationKinds.has(edge.kind)) continue;
    if (!state.visibleNodeIds.has(edge.source) || !state.visibleNodeIds.has(edge.target)) continue;
    if (!index.nodes.has(edge.source) || !index.nodes.has(edge.target)) continue;
    const active = activeNodeIds.has(edge.source) && activeNodeIds.has(edge.target);
    links.push({ ...edge, active, dimmed: !active });
  }

  return { nodes, links };
}
