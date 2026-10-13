const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createLocalGraphify, createLocalGraphifyLoader } = require('../../lib/local-graphify');

test('local Graphify view keeps distinct project source groups and real edges', () => {
  const graph = {
    nodes: [
      { id: 'a', label: 'Alpha', source_file: 'alpha/src/a.py', community: 1 },
      { id: 'b', label: 'Beta', source_file: 'alpha/src/b.py', community: 1 },
      { id: 'c', label: 'Done', source_file: 'finish/done/src/c.py', community: 2 },
      { id: 'external', label: 'Library', source_file: '@library/mod.py', community: 3 }
    ],
    links: [
      { source: 'a', target: 'b', relation: 'calls' },
      { source: 'b', target: 'c', relation: 'imports' },
      { source: 'a', target: 'external', relation: 'imports' }
    ]
  };
  const select = createLocalGraphify(graph, { maxNodes: 10 });
  const all = select();
  assert.deepEqual(all.projects.map(project => project.id), ['alpha', 'finish/done']);
  assert.equal(all.summary.visibleNodes, 3);
  assert.equal(all.summary.visibleEdges, 2);
  assert.equal(all.summary.crossFileEdges, 2);
  assert.equal(all.summary.crossProjectEdges, 1);
  assert.equal(select('alpha').summary.visibleEdges, 1);
  assert.equal(select('finish/done').nodes[0].file, 'finish/done/src/c.py');
});

test('semantic document and converted Office nodes keep project provenance and relationship evidence', () => {
  const converted = 'graphify-out/converted/plan_12345678.md';
  const graph = {
    nodes: [
      { id: 'paper', label: 'Research', source_file: 'alpha/research.pdf', file_type: 'concept', community: 1 },
      { id: 'sheet', label: 'Estimate', source_file: converted, file_type: 'concept', community: 1 },
      { id: 'code', label: 'parse', source_file: 'alpha/src/parse.py', file_type: 'code', community: 1 }
    ],
    links: [{ source: 'paper', target: 'sheet', relation: 'supports', confidence: 'INFERRED', confidence_score: 0.8, source_file: converted }],
    hyperedges: [{ id: 'cluster', label: 'Research cluster', nodes: ['paper', 'sheet'], relation: 'groups', source_file: 'alpha/research.pdf' }]
  };
  const result = createLocalGraphify(graph, { maxNodes: 3, sourceMap: { [converted]: 'alpha/plan.xlsx' } })();
  assert.equal(result.summary.kinds.concept, 2);
  assert.equal(result.summary.visibleKinds.concept, 2);
  assert.equal(result.summary.representedFiles, 3);
  assert.equal(result.summary.totalHyperedges, 1);
  assert.equal(result.nodes.find(node => node.id === 'sheet').file, 'alpha/plan.xlsx');
  assert.equal(result.nodes.find(node => node.id === 'sheet').format, 'Office');
  assert.equal(result.nodes.find(node => node.id === 'paper').format, 'PDF');
  assert.deepEqual(result.edges.find(edge => edge.source === 'paper' && edge.target === 'sheet'), { id: 0, source: 'paper', target: 'sheet', relation: 'supports', confidence: 'INFERRED', score: 0.8, file: 'alpha/plan.xlsx', location: '' });
});

test('overview keeps multiple projects and favors connected evidence within its node limit', () => {
  const graph = {
    nodes: ['a1', 'a2', 'a3', 'a4', 'a5', 'b1', 'b2'].map(id => ({
      id, label: id, source_file: `${id[0]}/notes/${id}.md`, file_type: 'concept'
    })),
    links: [
      ['a1', 'a2'], ['a1', 'a3'], ['a2', 'a3'], ['a2', 'a4'], ['a3', 'a4'],
      ['a4', 'a5'], ['b1', 'b2'], ['a1', 'b1']
    ].map(([source, target]) => ({ source, target, relation: 'related' }))
  };
  const overview = createLocalGraphify(graph, { maxNodes: 5 })();
  assert.equal(overview.nodes.length, 5);
  assert.deepEqual(new Set(overview.nodes.map(node => node.project)), new Set(['a', 'b']));
  assert.ok(overview.summary.visibleEdges >= 4);
  assert.ok(overview.edges.every(edge => graph.links.some(link => link.source === edge.source && link.target === edge.target)));
});

test('local Graphify loader reads a rebuilt graph without restarting the server', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'atlas-graphify-reload-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const graphDir = path.join(root, 'source', 'graphify-out');
  await fs.mkdir(graphDir, { recursive: true });
  const graphPath = path.join(graphDir, 'graph.json');
  const graph = nodes => ({ nodes, links: [], hyperedges: [] });
  await fs.writeFile(graphPath, JSON.stringify(graph([{ id: 'one', label: 'One', source_file: 'alpha/one.md' }])));
  const load = createLocalGraphifyLoader(graphPath);
  assert.equal((await load()).summary.totalNodes, 1);
  await fs.writeFile(graphPath, JSON.stringify(graph([
    { id: 'one', label: 'One', source_file: 'alpha/one.md' },
    { id: 'two', label: 'Two', source_file: 'beta/two.md' }
  ])));
  assert.equal((await load()).summary.totalNodes, 2);
});
