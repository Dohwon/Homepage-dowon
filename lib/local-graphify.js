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
  const isSemantic = node => node.file_type !== 'code' && node.file_type !== 'sql';
  const balanced = (items, limit) => {
    const semantic = ranked(items.filter(isSemantic));
    const code = ranked(items.filter(node => !isSemantic(node)));
    const semanticShare = Math.min(semantic.length, Math.ceil(limit * 0.55));
    const chosen = [...semantic.slice(0, semanticShare), ...code.slice(0, limit - semanticShare)];
    if (chosen.length < limit) chosen.push(...semantic.slice(semanticShare, semanticShare + limit - chosen.length));
    return chosen;
  };
  const kinds = items => items.reduce((counts, node) => { const kind = node.file_type || 'unknown'; counts[kind] = (counts[kind] || 0) + 1; return counts; }, {});

  return function select(project = '') {
    const requested = project && groups.has(project) ? project : '';
    let selected;
    if (requested) selected = balanced(groups.get(requested), maxNodes);
    else {
      const perProject = Math.max(15, Math.floor(maxNodes / Math.max(1, groups.size)));
      selected = [...groups.values()].flatMap(items => balanced(items, perProject));
      const selectedIds = new Set(selected.map(node => node.id));
      selected.push(...balanced(nodes.filter(node => !selectedIds.has(node.id)), maxNodes - selected.length));
    }
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
  return async project => {
    const metadataDir = require('node:path').resolve(graphPath, '../../../');
    if (!promise) promise = Promise.all([
      fs.readFile(graphPath, 'utf8'),
      fs.readFile(require('node:path').join(metadataDir, 'scan-manifest.json'), 'utf8').then(JSON.parse).catch(() => ({})),
      fs.readFile(require('node:path').join(metadataDir, 'extraction-status.json'), 'utf8').then(JSON.parse).catch(() => null)
    ]).then(([raw, manifest, status]) => createLocalGraphify(JSON.parse(raw), {
      sourceMap: manifest.converted_source_map || {},
      coverage: manifest.mode ? { mode: manifest.mode, stagedFiles: manifest.staged_files, projectGroups: manifest.project_groups, extraction: status } : null
    }));
    return (await promise)(project);
  };
}

module.exports = { createLocalGraphify, createLocalGraphifyLoader, projectOf };
