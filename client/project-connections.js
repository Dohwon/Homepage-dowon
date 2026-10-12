const DIRECT_KINDS = new Set(["EVOLVED_FROM", "VALIDATES", "DEPLOYS", "REUSES_COMPONENT"]);
const FEATURE_KINDS = new Set(["HAS_TAG", "USES_TECH"]);

export function buildProjectConnections(graph) {
  const projectNodes = (graph?.nodes || []).filter(node => node.kind === "Project").sort((a, b) => a.id.localeCompare(b.id));
  const projects = new Map(projectNodes.map(node => [node.id, node]));
  const labels = new Map((graph?.nodes || []).map(node => [node.id, node.label]));
  const features = new Map(projectNodes.map(node => [node.id, new Set()]));
  const focuses = new Map(projectNodes.map(node => [node.id, new Set()]));
  const direct = new Map();
  const pairKey = (a, b) => [a, b].sort().join("|");
  for (const edge of graph?.edges || []) {
    if (features.has(edge.source) && FEATURE_KINDS.has(edge.kind) && labels.has(edge.target)) {
      features.get(edge.source).add(edge.target);
    }
    if (focuses.has(edge.source) && edge.kind === "HAS_FOCUS" && labels.has(edge.target)) focuses.get(edge.source).add(edge.target);
    if (DIRECT_KINDS.has(edge.kind) && projects.has(edge.source) && projects.has(edge.target) && edge.source !== edge.target) {
      const key = pairKey(edge.source, edge.target);
      const records = direct.get(key) || [];
      records.push({ kind: edge.kind, source: edge.source, target: edge.target, evidence_links: edge.evidence_links || [] });
      direct.set(key, records);
    }
  }
  const frequency = new Map();
  for (const values of features.values()) {
    for (const id of values) frequency.set(id, (frequency.get(id) || 0) + 1);
  }
  const maxSpecificFrequency = Math.max(2, Math.ceil(projectNodes.length * 0.3));
  const edges = [];
  const connected = new Set();
  let sharedPairs = 0;
  for (let i = 0; i < projectNodes.length; i += 1) {
    for (let j = i + 1; j < projectNodes.length; j += 1) {
      const source = projectNodes[i].id;
      const target = projectNodes[j].id;
      const shared = [...features.get(source)]
        .filter(id => features.get(target).has(id) && frequency.get(id) <= maxSpecificFrequency)
        .map(id => ({ id, label: labels.get(id), projectCount: frequency.get(id) }))
        .sort((a, b) => a.projectCount - b.projectCount || a.label.localeCompare(b.label));
      const directRelations = direct.get(pairKey(source, target)) || [];
      if (shared.length < 2 && !directRelations.length) continue;
      const score = shared.reduce((sum, item) => sum + Math.log((projectNodes.length + 1) / (item.projectCount + 1)), 0);
      const kind = directRelations.length ? "DIRECT" : "SHARED";
      if (shared.length >= 2) sharedPairs += 1;
      edges.push({
        id: pairKey(source, target), source, target, kind,
        score: Math.round(score * 100) / 100, shared, directRelations
      });
      connected.add(source);
      connected.add(target);
    }
  }
  edges.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  return {
    nodes: projectNodes.map(node => ({
      id: node.id, label: node.label, url: node.url, summary: node.summary || "",
      focus: [...focuses.get(node.id)].sort()[0] || "other"
    })),
    edges,
    stats: {
      projects: projectNodes.length,
      connectedProjects: connected.size,
      isolatedProjects: projectNodes.length - connected.size,
      directPairs: edges.filter(edge => edge.directRelations.length).length,
      sharedPairs
    }
  };
}
