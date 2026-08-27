const SVG_NS = "http://www.w3.org/2000/svg";
const KIND_COLORS = {
  project: "var(--project)",
  domain: "var(--domain)",
  problem: "var(--problem)",
  pattern: "var(--pattern)",
  technology: "var(--technology)",
  outcome: "var(--outcome)"
};

function element(name, attributes = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
}

function displayKind(kind) {
  return `${kind.charAt(0).toUpperCase()}${kind.slice(1)}`;
}

function dimensions(svg) {
  const box = svg.getBoundingClientRect();
  return { width: Math.max(640, Math.round(box.width || 960)), height: Math.max(480, Math.round(box.height || 620)) };
}

export function visibleNodeLabel(label, limit = 34) {
  const value = String(label || "");
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}

function placeProjectGrid(items, width, height) {
  const columns = 2;
  const rows = Math.ceil(items.length / columns);
  const startX = width * 0.3;
  const endX = width * 0.7;
  const startY = height * 0.19;
  const endY = height * 0.81;
  items.forEach((node, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    node.x = columns === 1 ? width / 2 : startX + ((endX - startX) * column) / (columns - 1);
    node.y = rows === 1 ? height / 2 : startY + ((endY - startY) * row) / (rows - 1);
    node.labelSide = column === columns - 1 ? "right" : "left";
    node.labelLimit = 24;
  });
}

function placeTopicBands(items, width, height) {
  const spacing = 18;
  const margin = 14;
  const columns = Math.max(1, Math.floor((width - margin * 2) / spacing) + 1);
  const rows = Math.ceil(items.length / columns);
  const topRows = Math.ceil(rows / 2);
  items.forEach((node, index) => {
    const row = Math.floor(index / columns);
    const column = index % columns;
    node.x = margin + column * spacing;
    node.y = row < topRows
      ? margin + row * spacing
      : height - margin - (row - topRows) * spacing;
    node.labelSide = node.x > width * 0.72 ? "left" : "right";
    node.labelLimit = 28;
  });
}

export function layoutNodes(nodes, width, height) {
  const center = { x: width / 2, y: height / 2 };
  const projects = nodes.filter((node) => node.kind === "project");
  const topics = nodes.filter((node) => node.kind !== "project");
  const placeRing = (items, radiusX, radiusY, offset = 0) => items.forEach((node, index) => {
    const angle = offset + (Math.PI * 2 * index) / Math.max(1, items.length);
    node.x = center.x + Math.cos(angle) * radiusX;
    node.y = center.y + Math.sin(angle) * radiusY;
  });
  if (projects.length > 12) {
    placeProjectGrid(projects, width, height);
  } else {
    placeRing(projects, Math.min(230, width * 0.24), Math.min(150, height * 0.24), -Math.PI / 2);
  }
  placeTopicBands(topics, width, height);
  if (nodes.length === 1) Object.assign(nodes[0], center);
  return nodes;
}

function render(viewport, nodes, edges, onSelect) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  for (const edge of edges) {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) continue;
    viewport.append(element("line", {
      class: "graph-edge",
      x1: source.x,
      y1: source.y,
      x2: target.x,
      y2: target.y,
      "stroke-width": Math.min(4, 0.7 + Number(edge.weight || 1) * 0.35)
    }));
  }
  for (const node of nodes) {
    const group = element("g", {
      class: "graph-node",
      transform: `translate(${node.x} ${node.y})`,
      tabindex: "0",
      role: "button",
      "aria-label": `${node.label}, ${node.kind}`,
      "data-node-id": node.id,
      "data-node-type": displayKind(node.kind)
    });
    const title = element("title");
    title.textContent = node.label;
    group.append(title);
    group.append(element("circle", { r: node.kind === "project" ? 10 : 7, fill: KIND_COLORS[node.kind] || "var(--muted)" }));
    const label = element("text", {
      x: node.labelSide === "left" ? -13 : 13,
      y: 4,
      "text-anchor": node.labelSide === "left" ? "end" : "start"
    });
    label.textContent = visibleNodeLabel(node.label, node.labelLimit);
    group.append(label);
    const select = () => onSelect(node);
    group.addEventListener("click", select);
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select();
      }
    });
    viewport.append(group);
  }
}

function applyTransform(viewport, state) {
  viewport.setAttribute("transform", `translate(${state.x} ${state.y}) scale(${state.scale})`);
}

export function createGraphView(svg, graph, { onSelect = () => {}, kinds } = {}) {
  const allNodes = (graph?.nodes || []).map((node) => ({ ...node, kind: String(node.kind || "project").toLowerCase() }));
  const allEdges = (graph?.edges || []).map((edge) => ({ ...edge }));
  const enabled = new Set(kinds || Object.keys(KIND_COLORS));
  const viewport = element("g", { id: "graph-viewport" });
  const state = { scale: 1, x: 0, y: 0, dragging: false, pointerX: 0, pointerY: 0 };
  let currentNodes = [];
  let destroyed = false;

  const draw = () => {
    const { width, height } = dimensions(svg);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    currentNodes = layoutNodes(allNodes.filter((node) => enabled.has(node.kind)), width, height);
    const ids = new Set(currentNodes.map((node) => node.id));
    const edges = allEdges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
    viewport.replaceChildren();
    render(viewport, currentNodes, edges, onSelect);
    applyTransform(viewport, state);
  };
  const fit = () => {
    state.scale = 1;
    state.x = 0;
    state.y = 0;
    applyTransform(viewport, state);
  };
  const focus = (id) => {
    const node = currentNodes.find((item) => item.id === id);
    if (!node) return false;
    const { width, height } = dimensions(svg);
    state.scale = 1.45;
    state.x = width / 2 - node.x * state.scale;
    state.y = height / 2 - node.y * state.scale;
    applyTransform(viewport, state);
    svg.querySelectorAll(".graph-node").forEach((item) => item.toggleAttribute("data-focused", item.dataset.nodeId === id));
    return true;
  };
  const setKinds = (nextKinds) => {
    enabled.clear();
    nextKinds.forEach((kind) => enabled.add(kind));
    fit();
    draw();
  };
  const onWheel = (event) => {
    event.preventDefault();
    const bounds = svg.getBoundingClientRect();
    const px = event.clientX - bounds.left;
    const py = event.clientY - bounds.top;
    const next = Math.min(3.2, Math.max(0.55, state.scale * Math.exp(-event.deltaY * 0.0012)));
    const ratio = next / state.scale;
    state.x = px - (px - state.x) * ratio;
    state.y = py - (py - state.y) * ratio;
    state.scale = next;
    applyTransform(viewport, state);
  };
  const onPointerDown = (event) => {
    if (event.button !== 0) return;
    state.dragging = true;
    state.pointerX = event.clientX;
    state.pointerY = event.clientY;
    svg.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event) => {
    if (!state.dragging) return;
    state.x += event.clientX - state.pointerX;
    state.y += event.clientY - state.pointerY;
    state.pointerX = event.clientX;
    state.pointerY = event.clientY;
    applyTransform(viewport, state);
  };
  const onPointerUp = (event) => {
    state.dragging = false;
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
  };
  const resizeObserver = new ResizeObserver(() => {
    if (!destroyed) draw();
  });

  svg.replaceChildren(viewport);
  draw();
  svg.addEventListener("wheel", onWheel, { passive: false });
  svg.addEventListener("pointerdown", onPointerDown);
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", onPointerUp);
  svg.addEventListener("pointercancel", onPointerUp);
  resizeObserver.observe(svg);

  return {
    fit,
    focus,
    setKinds,
    destroy() {
      destroyed = true;
      resizeObserver.disconnect();
      svg.removeEventListener("wheel", onWheel);
      svg.removeEventListener("pointerdown", onPointerDown);
      svg.removeEventListener("pointermove", onPointerMove);
      svg.removeEventListener("pointerup", onPointerUp);
      svg.removeEventListener("pointercancel", onPointerUp);
      svg.replaceChildren();
    }
  };
}
