const COLORS = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#7C92C8", "#55A8A1"];

export function createSourceGraphView(container, graph, { onSelect = () => {}, onReady = () => {} } = {}) {
  const Vis = globalThis.vis;
  if (!Vis?.DataSet || !Vis?.Network) throw new Error("graphify_visualizer_unavailable");
  const communities = [...new Set(graph.nodes.map(node => node.community))].sort();
  const colors = new Map(communities.map((id, index) => [id, COLORS[index % COLORS.length]]));
  const projects = [...new Set(graph.nodes.map(node => node.project))].sort();
  const projectIndex = new Map(projects.map((id, index) => [id, index]));
  const nodes = new Vis.DataSet(graph.nodes.map((node, index) => {
    const projectAngle = 2 * Math.PI * (projectIndex.get(node.project) || 0) / Math.max(1, projects.length);
    const centerRadius = graph.scope === 'all' ? 430 : 0;
    const angle = index * 2.399963;
    const radius = 8 * Math.sqrt(index % 160);
    const color = colors.get(node.community);
    return {
      id: node.id, label: '', title: `${node.label}\n${node.kind} · ${node.file}`,
      x: centerRadius * Math.cos(projectAngle) + radius * Math.cos(angle),
      y: centerRadius * Math.sin(projectAngle) + radius * Math.sin(angle),
      shape: 'dot', size: Math.min(14, (node.kind === 'code' ? 3 : 5) + Math.log2((node.degree || 0) + 1)),
      color: { background: color, border: color, highlight: { background: '#fff', border: color } },
      borderWidth: node.kind === 'code' ? 0.3 : 1.5, community: node.community
    };
  }));
  const edges = new Vis.DataSet(graph.edges.map(edge => ({
    id: edge.id, from: edge.source, to: edge.target, title: `${edge.relation} · ${edge.confidence}${edge.file ? `\n${edge.file}` : ''}`,
    color: { color: '#9ba7b8', opacity: 0.3 }, width: 0.7,
    dashes: edge.confidence === 'INFERRED'
  })));
  const network = new Vis.Network(container, { nodes, edges }, {
    physics: { enabled: true, solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -45, centralGravity: 0.004, springLength: 55, springConstant: 0.04, damping: 0.55 }, stabilization: { iterations: 110, fit: true } },
    interaction: { hover: true, tooltipDelay: 100, hideEdgesOnDrag: true },
    edges: { smooth: false }, nodes: { shape: 'dot' }
  });
  network.once('stabilizationIterationsDone', () => { network.setOptions({ physics: { enabled: false } }); onReady(); });
  network.on('selectNode', params => { if (params.nodes[0]) onSelect(params.nodes[0]); });
  return {
    focus(id) { if (!nodes.get(id)) return; network.selectNodes([id]); network.focus(id, { scale: 1.5, animation: { duration: 300 } }); onSelect(id); },
    fit() { network.fit({ animation: { duration: 300 } }); },
    filter(visible) {
      nodes.update(graph.nodes.map(node => ({ id: node.id, hidden: !visible.has(node.community) })));
      edges.update(graph.edges.map(edge => ({ id: edge.id, hidden: !visible.has(nodes.get(edge.source).community) || !visible.has(nodes.get(edge.target).community) })));
      network.fit();
    },
    destroy() { network.destroy(); }
  };
}

export function createGraphifyView(container, graph, { onSelect = () => {}, onReady = () => {} } = {}) {
  const Vis = globalThis.vis;
  if (!Vis?.DataSet || !Vis?.Network) throw new Error("graphify_visualizer_unavailable");
  const folderColors = new Map(graph.folders.map((folder, index) => [folder.id, COLORS[index % COLORS.length]]));
  const folderIndexes = new Map(graph.folders.map((folder, index) => [folder.id, index]));
  const fileIndexes = new Map();
  const nodes = new Vis.DataSet(graph.nodes.map(node => {
    const folderIndex = folderIndexes.get(node.folder) || 0;
    const angle = 2 * Math.PI * folderIndex / Math.max(1, graph.folders.length);
    const centerX = 250 * Math.cos(angle);
    const centerY = 250 * Math.sin(angle);
    const fileIndex = fileIndexes.get(node.folder) || 0;
    if (node.kind === "file") fileIndexes.set(node.folder, fileIndex + 1);
    const fileAngle = fileIndex * 2.399963;
    const fileRadius = 45 + 22 * Math.sqrt(fileIndex);
    const color = folderColors.get(node.folder);
    return {
      id: node.id,
      label: node.kind === "folder" ? node.label : "",
      title: node.id,
      x: node.kind === "folder" ? centerX : centerX + fileRadius * Math.cos(fileAngle),
      y: node.kind === "folder" ? centerY : centerY + fileRadius * Math.sin(fileAngle),
      shape: "dot",
      size: node.kind === "folder" ? 21 : Math.min(15, 7 + Math.sqrt(node.symbols || 1)),
      color: { background: color, border: color, highlight: { background: "#ffffff", border: color } },
      font: node.kind === "folder" ? { size: 15, color: "#dce5f2", face: "Inter" } : { size: 0 },
      borderWidth: 1.5,
      mass: node.kind === "folder" ? 3 : 1
    };
  }));
  const edges = new Vis.DataSet(graph.edges.map(edge => ({
    id: edge.id,
    from: edge.source,
    to: edge.target,
    title: edge.kind === "contains" ? "folder contains file" : `${edge.relations.join(" · ")} [${edge.confidence}] · ${edge.weight}`,
    width: edge.kind === "contains" ? 0.8 : Math.min(3.2, 1 + Math.log2(edge.weight + 1) * 0.45),
    color: { color: edge.kind === "contains" ? "#687487" : "#97abc4", opacity: edge.kind === "contains" ? 0.22 : 0.52 },
    dashes: edge.confidence === "INFERRED",
    arrows: edge.kind === "relation" ? { to: { enabled: true, scaleFactor: 0.35 } } : undefined
  })));
  const network = new Vis.Network(container, { nodes, edges }, {
    physics: {
      enabled: true,
      solver: "forceAtlas2Based",
      forceAtlas2Based: {
        gravitationalConstant: -60,
        centralGravity: 0.005,
        springLength: 120,
        springConstant: 0.08,
        damping: 0.4,
        avoidOverlap: 0.8
      },
      stabilization: { iterations: 180, fit: true }
    },
    interaction: { hover: true, tooltipDelay: 100, hideEdgesOnDrag: true, navigationButtons: false },
    nodes: { shape: "dot" },
    edges: { smooth: { type: "continuous", roundness: 0.2 }, selectionWidth: 3 }
  });
  network.once("stabilizationIterationsDone", () => {
    network.setOptions({ physics: { enabled: false } });
    onReady();
  });
  network.on("selectNode", params => {
    if (params.nodes[0]) onSelect(params.nodes[0]);
  });
  return {
    focus(id) {
      if (!nodes.get(id)) return;
      network.selectNodes([id]);
      network.focus(id, { scale: 1.25, animation: { duration: 400 } });
      onSelect(id);
    },
    fit() { network.fit({ animation: { duration: 350 } }); },
    destroy() { network.destroy(); }
  };
}

export function createProjectConnectionsView(container, graph, { onSelect = () => {}, onReady = () => {} } = {}) {
  const Vis = globalThis.vis;
  if (!Vis?.DataSet || !Vis?.Network) throw new Error("graphify_visualizer_unavailable");
  const focuses = [...new Set(graph.nodes.map(node => node.focus))].sort();
  const colors = new Map(focuses.map((id, index) => [id, COLORS[index % COLORS.length]]));
  const nodes = new Vis.DataSet(graph.nodes.map((node, index) => {
    const angle = index * 2.399963;
    const radius = 30 * Math.sqrt(index);
    const color = colors.get(node.focus);
    return {
      id: node.id,
      label: node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label,
      title: node.label,
      x: radius * Math.cos(angle), y: radius * Math.sin(angle),
      shape: "dot", size: 15,
      color: { background: color, border: color, highlight: { background: "#ffffff", border: color } },
      font: { size: 11, color: "#eaf0f8", face: "IBM Plex Sans KR", strokeWidth: 3, strokeColor: "#111b2a" },
      borderWidth: 1.5
    };
  }));
  const edges = new Vis.DataSet(graph.edges.map(edge => ({
    id: edge.id,
    from: edge.source,
    to: edge.target,
    title: edge.kind === "DIRECT" ? "근거가 기록된 직접 관계" : `공유 속성 ${edge.shared.length}개`,
    width: edge.kind === "DIRECT" ? 3.5 : Math.min(2.5, 0.8 + edge.score * 0.17),
    color: { color: edge.kind === "DIRECT" ? "#f7bd69" : "#9db7d4", opacity: edge.kind === "DIRECT" ? 0.95 : 0.52 },
    dashes: edge.kind !== "DIRECT"
  })));
  const network = new Vis.Network(container, { nodes, edges }, {
    physics: {
      enabled: true, solver: "forceAtlas2Based",
      forceAtlas2Based: { gravitationalConstant: -55, centralGravity: 0.005, springLength: 165, springConstant: 0.07, damping: 0.45, avoidOverlap: 0.8 },
      stabilization: { iterations: 220, fit: true }
    },
    interaction: { hover: true, tooltipDelay: 100, hideEdgesOnDrag: true },
    edges: { smooth: { type: "continuous", roundness: 0.2 }, selectionWidth: 3 }
  });
  network.once("stabilizationIterationsDone", () => {
    network.setOptions({ physics: { enabled: false } });
    onReady();
  });
  network.on("selectNode", params => { if (params.nodes[0]) onSelect(params.nodes[0]); });
  return {
    focus(id) {
      if (!nodes.get(id)) return;
      network.selectNodes([id]);
      network.focus(id, { scale: 1.1, animation: { duration: 350 } });
      onSelect(id);
    },
    fit() { network.fit({ animation: { duration: 350 } }); },
    destroy() { network.destroy(); }
  };
}
