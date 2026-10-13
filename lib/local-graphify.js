const fs = require('node:fs/promises');
const path = require('node:path');

function formatOf(file) {
  const ext = path.extname(file).toLowerCase();
  if (ext === '.pdf') return 'PDF';
  if (['.docx', '.xlsx', '.pptx'].includes(ext)) return 'Office';
  if (['.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'].includes(ext)) return '이미지';
  if (['.md', '.txt', '.yaml', '.yml', '.html', '.rst'].includes(ext)) return '문서';
  return '코드·데이터';
}

function projectOf(file) {
  if (typeof file !== 'string' || !file.includes('/')) return null;
  const parts = file.split('/');
  const project = parts[0] === 'finish' && parts[1] ? `finish/${parts[1]}` : parts[0];
  return project === '..' || project.startsWith('@') ? null : project;
}

function createLocalGraphify(graph, { maxNodes = 1400, sourceMap = {}, coverage = null } = {}) {
  if (!Array.isArray(graph?.nodes) || !Array.isArray(graph?.links)) throw new TypeError('invalid_graphify_graph');
  const hyperedges = Array.isArray(graph.hyperedges) ? graph.hyperedges : [];
  const rawNodes = [
    ...graph.nodes,
    ...hyperedges.filter(item => item.id && item.source_file).map(item => ({
      id: `hyperedge:${item.id}`, label: item.label || item.relation || item.id,
      source_file: item.source_file, file_type: 'hyperedge', community: 'hyperedge'
    }))
  ];
  const nodes = rawNodes.map(node => ({ ...node, source_file: sourceMap[node.source_file] || node.source_file }))
    .filter(node => node.id && node.source_file && projectOf(node.source_file));
  const representedFiles = new Set(nodes.map(node => node.source_file)).size;
  const byId = new Map(nodes.map(node => [node.id, node]));
  const degree = new Map();
  const hyperLinks = hyperedges.flatMap(item => (item.nodes || []).map(id => ({
    source: `hyperedge:${item.id}`, target: id, relation: item.relation || 'groups',
    confidence: item.confidence || 'EXTRACTED', confidence_score: item.confidence_score,
    source_file: item.source_file
  })));
  const links = [...graph.links, ...hyperLinks].filter(edge => byId.has(edge.source) && byId.has(edge.target) && edge.source !== edge.target);
  const crossFileEdges = links.filter(edge => byId.get(edge.source).source_file !== byId.get(edge.target).source_file).length;
  const crossProjectEdges = links.filter(edge => projectOf(byId.get(edge.source).source_file) !== projectOf(byId.get(edge.target).source_file)).length;
  const crossProjectSemanticEdges = links.filter(edge =>
    projectOf(byId.get(edge.source).source_file) !== projectOf(byId.get(edge.target).source_file)
    && byId.get(edge.source).file_type !== 'code' && byId.get(edge.target).file_type !== 'code'
  ).length;
  for (const edge of links) {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
  }
  const groups = new Map();
  for (const node of nodes) {
    const project = projectOf(node.source_file);
    if (!groups.has(project)) groups.set(project, []);
    groups.get(project).push(node);
  }
  const projects = [...groups].map(([id, items]) => ({ id, nodes: items.length }))
    .sort((a, b) => b.nodes - a.nodes || a.id.localeCompare(b.id));
  const ranked = items => [...items].sort((a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0) || a.id.localeCompare(b.id));
  const isSemantic = node => ['문서', 'PDF', 'Office', '이미지'].includes(formatOf(node.source_file));
  const balanced = (items, limit) => {
    const semantic = ranked(items.filter(isSemantic));
    const code = ranked(items.filter(node => !isSemantic(node)));
    const semanticShare = Math.min(semantic.length, Math.ceil(limit * 0.55));
    const chosen = [...semantic.slice(0, semanticShare), ...code.slice(0, limit - semanticShare)];
    if (chosen.length < limit) chosen.push(...semantic.slice(semanticShare, semanticShare + limit - chosen.length));
    return chosen;
  };
  const kinds = items => items.reduce((counts, node) => { const kind = node.file_type || 'unknown'; counts[kind] = (counts[kind] || 0) + 1; return counts; }, {});
  const adjacency = new Map(nodes.map(node => [node.id, []]));
  for (const edge of links) {
    adjacency.get(edge.source).push(edge.target);
    adjacency.get(edge.target).push(edge.source);
  }
  const rankedAll = ranked(nodes);
  const defaultSelection = (() => {
    if (nodes.length <= maxNodes) return nodes;
    const chosen = [];
    const chosenIds = new Set();
    const connected = new Map();
    const heap = [];
    const score = id => (connected.get(id) || 0) * 1000 + Math.sqrt(degree.get(id) || 0);
    const push = id => {
      const item = { id, score: score(id) };
      heap.push(item);
      for (let index = heap.length - 1; index > 0;) {
        const parent = (index - 1) >> 1;
        if (heap[parent].score >= item.score) break;
        heap[index] = heap[parent];
        index = parent;
        heap[index] = item;
      }
    };
    const pop = () => {
      const top = heap[0];
      const last = heap.pop();
      if (heap.length) {
        let index = 0;
        while (index * 2 + 1 < heap.length) {
          let child = index * 2 + 1;
          if (child + 1 < heap.length && heap[child + 1].score > heap[child].score) child++;
          if (heap[child].score <= last.score) break;
          heap[index] = heap[child];
          index = child;
        }
        heap[index] = last;
      }
      return top;
    };
    const add = node => {
      if (chosenIds.has(node.id) || chosen.length >= maxNodes) return;
      chosenIds.add(node.id);
      chosen.push(node);
      for (const neighbor of adjacency.get(node.id) || []) {
        if (chosenIds.has(neighbor)) continue;
        connected.set(neighbor, (connected.get(neighbor) || 0) + 1);
        push(neighbor);
      }
    };
    // Include evidence-bearing documents across projects before growing connected clusters.
    const seeds = [...groups.values()].map(items => ({
      semantic: ranked(items.filter(isSemantic)).slice(0, 5),
      structural: ranked(items.filter(node => !isSemantic(node))).slice(0, 2)
    }));
    for (let index = 0; index < 5; index++) for (const group of seeds) if (group.semantic[index]) add(group.semantic[index]);
    for (let index = 0; index < 2; index++) for (const group of seeds) if (group.structural[index]) add(group.structural[index]);
    while (chosen.length < maxNodes && heap.length) {
      const item = pop();
      if (chosenIds.has(item.id)) continue;
      if (item.score !== score(item.id)) continue;
      add(byId.get(item.id));
    }
    for (const node of rankedAll) add(node);
    return chosen;
  })();

  return function select(project = '') {
    const requested = project && groups.has(project) ? project : '';
    let selected;
    if (requested) selected = balanced(groups.get(requested), maxNodes);
    else selected = defaultSelection;
    const ids = new Set(selected.map(node => node.id));
    const visibleEdges = links.filter(edge => ids.has(edge.source) && ids.has(edge.target));
    const communityCounts = new Map();
    for (const node of selected) {
      const key = String(node.community ?? 'unknown');
      const prev = communityCounts.get(key) || { id: key, label: node.community_name || node.label || `Community ${key}`, nodes: 0, degree: -1 };
      prev.nodes += 1;
      if (!node.community_name && (degree.get(node.id) || 0) > prev.degree) {
        prev.label = node.label || `Community ${key}`;
        prev.degree = degree.get(node.id) || 0;
      }
      communityCounts.set(key, prev);
    }
    return {
      source: 'Graphify',
      scope: requested || 'all',
      coverage,
      summary: { representedFiles, totalNodes: graph.nodes.length, totalEdges: graph.links.length, totalHyperedges: hyperedges.length, totalCommunities: new Set(graph.nodes.map(node => node.community)).size, crossFileEdges, crossProjectEdges, crossProjectSemanticEdges, visibleNodes: selected.length, visibleEdges: visibleEdges.length, kinds: kinds(nodes), visibleKinds: kinds(selected) },
      projects,
      communities: [...communityCounts.values()].map(({ degree: _degree, ...community }) => community).sort((a, b) => b.nodes - a.nodes),
      nodes: selected.map(node => ({ id: node.id, label: node.label || node.id, project: projectOf(node.source_file), file: node.source_file, format: formatOf(node.source_file), location: node.source_location || '', community: String(node.community ?? 'unknown'), kind: node.file_type || 'unknown', degree: degree.get(node.id) || 0 })),
      edges: visibleEdges.map((edge, index) => ({ id: index, source: edge.source, target: edge.target, relation: edge.relation || 'related', confidence: edge.confidence || 'EXTRACTED', score: edge.confidence_score ?? null, file: sourceMap[edge.source_file] || edge.source_file || '', location: edge.source_location || '' }))
    };
  };
}

function createLocalGraphifyLoader(graphPath) {
  let promise;
  let cachedVersion;
  const metadataDir = path.resolve(graphPath, '../../../');
  const manifestPath = path.join(metadataDir, 'scan-manifest.json');
  const statusPath = path.join(metadataDir, 'extraction-status.json');
  const versionOf = async file => fs.stat(file, { bigint: true }).then(stat => `${stat.size}:${stat.mtimeNs}`, () => 'missing');
  return async project => {
    const version = (await Promise.all([graphPath, manifestPath, statusPath].map(versionOf))).join('|');
    if (version !== cachedVersion || !promise) {
      cachedVersion = version;
      promise = Promise.all([
        fs.readFile(graphPath, 'utf8'),
        fs.readFile(manifestPath, 'utf8').then(JSON.parse).catch(() => ({})),
        fs.readFile(statusPath, 'utf8').then(JSON.parse).catch(() => null)
      ]).then(([raw, manifest, status]) => createLocalGraphify(JSON.parse(raw), {
        sourceMap: manifest.converted_source_map || {},
        coverage: manifest.mode ? { mode: manifest.mode, stagedFiles: manifest.staged_files, projectGroups: manifest.project_groups, extraction: status } : null
      })).catch(error => {
        if (cachedVersion === version) { cachedVersion = null; promise = null; }
        throw error;
      });
    }
    return (await promise)(project);
  };
}

module.exports = { createLocalGraphify, createLocalGraphifyLoader, projectOf };
