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

function layoutNodes(nodes, width, height) {
  const center = { x: width / 2, y: height / 2 };
  const projects = nodes.filter((node) => node.kind === "project");
  const topics = nodes.filter((node) => node.kind !== "project");
  const placeRing = (items, radiusX, radiusY, offset = 0) => items.forEach((node, index) => {
    const angle = offset + (Math.PI * 2 * index) / Math.max(1, items.length);
    node.x = center.x + Math.cos(angle) * radiusX;
    node.y = center.y + Math.sin(angle) * radiusY;
  });
  placeRing(projects, Math.min(230, width * 0.24), Math.min(150, height * 0.24), -Math.PI / 2);
  placeRing(topics, Math.min(410, width * 0.4), Math.min(255, height * 0.4), -Math.PI / 2 + 0.18);
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
    group.append(element("circle", { r: node.kind === "project" ? 10 : 7, fill: KIND_COLORS[node.kind] || "var(--muted)" }));
    const label = element("text", { x: 13, y: 4 });
    label.textContent = node.label;
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
