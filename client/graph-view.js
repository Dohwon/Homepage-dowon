const KIND_COLUMN = Object.freeze({
  KnowledgeFocus: 0,
  KnowledgeDomain: 1,
  KnowledgeTag: 2,
  Project: 3,
  Technology: 4,
  Artifact: 4,
});

const COLUMN_X = Object.freeze([42, 292, 542, 792, 1042]);
const NODE_WIDTH = 208;
const NODE_HEIGHT = 52;
const ROW_GAP = 68;
const GRAPH_WIDTH = 1292;

function escapeXml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[character]));
}

function graphData(value) {
  return {
    nodes: Array.isArray(value?.nodes) ? value.nodes.map(node => ({ ...node })) : [],
    links: Array.isArray(value?.links ?? value?.edges)
      ? (value.links ?? value.edges).map(link => ({ ...link }))
      : [],
  };
}

function splitLabel(value, limit = 22) {
  const label = String(value || "");
  if (label.length <= limit) return [label];
  const words = label.split(/\s+/).filter(Boolean);
  if (words.length < 2) return [label.slice(0, limit - 1) + "…"];
  const lines = [""];
  for (const word of words) {
    const current = lines.at(-1);
    if (!current || `${current} ${word}`.length <= limit) lines[lines.length - 1] = current ? `${current} ${word}` : word;
    else if (lines.length === 1) lines.push(word);
    else lines[1] = `${lines[1]}…`;
  }
  return lines.slice(0, 2);
}

function layoutGraph(graph) {
  const columns = new Map(Array.from({ length: 5 }, (_, index) => [index, []]));
  for (const node of graph.nodes) {
    const column = KIND_COLUMN[node.kind] ?? 4;
    columns.get(column).push(node);
  }
  for (const values of columns.values()) {
    values.sort((left, right) => String(left.label).localeCompare(String(right.label), "ko") || left.id.localeCompare(right.id));
  }
  const rowCount = Math.max(1, ...[...columns.values()].map(values => values.length));
  const height = Math.max(620, 116 + rowCount * ROW_GAP);
  const positions = new Map();
  for (let column = 0; column < 5; column += 1) {
    const values = columns.get(column);
    const offset = Math.max(0, (rowCount - values.length) * ROW_GAP / 2);
    values.forEach((node, index) => {
      positions.set(node.id, {
        x: COLUMN_X[column],
        y: 82 + offset + index * ROW_GAP,
        column,
      });
    });
  }
  return { height, positions };
}

function edgeMarkup(link, positions) {
  const source = positions.get(typeof link.source === "object" ? link.source.id : link.source);
  const target = positions.get(typeof link.target === "object" ? link.target.id : link.target);
  if (!source || !target) return "";
  let sx = source.x + NODE_WIDTH;
  let sy = source.y + NODE_HEIGHT / 2;
  let tx = target.x;
  let ty = target.y + NODE_HEIGHT / 2;
  if (target.column <= source.column) {
    sx = source.x;
    tx = target.x + NODE_WIDTH;
  }
  const middle = (sx + tx) / 2;
  return `<path class="kg-edge${link.dimmed ? " is-dimmed" : ""}" data-edge-kind="${escapeXml(link.kind)}" d="M ${sx} ${sy} C ${middle} ${sy}, ${middle} ${ty}, ${tx} ${ty}" />`;
}

function nodeMarkup(node, position) {
  const lines = splitLabel(node.label);
  const lineMarkup = lines.map((line, index) => (
    `<tspan x="${position.x + 14}" y="${position.y + 23 + index * 15}">${escapeXml(line)}</tspan>`
  )).join("");
  const count = node.kind === "KnowledgeTag" && Number.isFinite(node.projectCount)
    ? `<text class="kg-node-count" x="${position.x + NODE_WIDTH - 12}" y="${position.y + NODE_HEIGHT - 10}" text-anchor="end">${node.projectCount} projects</text>`
    : "";
  return `<g class="kg-node kg-kind-${escapeXml(node.kind)}${node.dimmed ? " is-dimmed" : ""}${node.active ? " is-active" : ""}" data-graph-node="${escapeXml(node.id)}" data-node-id="${escapeXml(node.id)}" role="button" tabindex="0" aria-label="${escapeXml(node.label)}">
    <rect x="${position.x}" y="${position.y}" width="${NODE_WIDTH}" height="${NODE_HEIGHT}" rx="6" />
    <text class="kg-node-label">${lineMarkup}</text>${count}
  </g>`;
}

function renderSvg(graph) {
  const layout = layoutGraph(graph);
  const edges = graph.links.map(link => edgeMarkup(link, layout.positions)).join("");
  const nodes = graph.nodes.map(node => nodeMarkup(node, layout.positions.get(node.id))).join("");
  return {
    html: `<svg xmlns="http://www.w3.org/2000/svg" data-knowledge-graph viewBox="0 0 ${GRAPH_WIDTH} ${layout.height}" role="img" aria-labelledby="kg-title kg-desc">
      <title id="kg-title">프로젝트 지식 그래프</title>
      <desc id="kg-desc">핵심 주제, 도메인, 태그와 프로젝트의 연결 구조</desc>
      <rect class="kg-background" width="${GRAPH_WIDTH}" height="${layout.height}" />
      <g class="kg-edges">${edges}</g>
      <g class="kg-nodes">${nodes}</g>
    </svg>`,
    layout,
  };
}

function clampScroll(value, maximum) {
  return Math.max(0, Math.min(Number.isFinite(value) ? value : 0, Math.max(0, maximum)));
}

export function supportsSvg(documentRef = globalThis.document) {
  try {
    if (typeof documentRef?.createElementNS !== "function") return false;
    const element = documentRef.createElementNS("http://www.w3.org/2000/svg", "svg");
    return Boolean(element && element.namespaceURI === "http://www.w3.org/2000/svg");
  } catch {
    return false;
  }
}

export function createGraphView(container, graph, {
  onSelect = () => {},
  onFailure = () => {},
  reducedMotion = false,
} = {}) {
  let current = graphData(graph);
  const initial = graphData(graph);
  let motionReduced = Boolean(reducedMotion);
  let destroyed = false;
  let layout = null;
  let lastCommand = null;

  const teardown = () => {
    if (destroyed) return;
    destroyed = true;
    container.removeEventListener?.("click", onClick);
    container.removeEventListener?.("keydown", onKeydown);
    container.replaceChildren?.();
  };
  const fail = (error) => {
    if (destroyed) return;
    teardown();
    try {
      onFailure(error instanceof Error ? error : new Error("graph_render_failed"));
    } catch {
      // The accessible list remains the final fallback.
    }
  };
  const render = () => {
    if (destroyed) return;
    try {
      const projected = renderSvg(current);
      layout = projected.layout;
      container.innerHTML = projected.html;
    } catch (error) {
      fail(error);
    }
  };
  const selectedNode = (event) => {
    const element = event?.target?.closest?.("[data-graph-node]");
    if (!element) return null;
    return current.nodes.find(node => node.id === element.dataset.graphNode) || null;
  };
  function onClick(event) {
    const node = selectedNode(event);
    if (node) onSelect(node);
  }
  function onKeydown(event) {
    if (!new Set(["Enter", " "]).has(event.key)) return;
    const node = selectedNode(event);
    if (!node) return;
    event.preventDefault?.();
    onSelect(node);
  }

  container.addEventListener?.("click", onClick);
  container.addEventListener?.("keydown", onKeydown);
  render();

  const record = (operation, nodeId = null) => {
    lastCommand = Object.freeze({ operation, nodeId, reducedMotion: motionReduced });
  };

  return {
    update(next) {
      if (destroyed) return;
      current = graphData(next);
      render();
    },
    focus(node) {
      if (destroyed || !node?.id) return false;
      const target = container.querySelector?.(`[data-node-id="${String(node.id).replace(/"/g, "")}"]`);
      if (!target) return false;
      record("focus", node.id);
      const containerRect = container.getBoundingClientRect?.() || { left: 0, top: 0 };
      const targetRect = target.getBoundingClientRect?.();
      const position = layout?.positions.get(node.id);
      const targetCenterX = targetRect
        ? (container.scrollLeft || 0) + targetRect.left - (containerRect.left || 0) + targetRect.width / 2
        : (position?.x || 0) + NODE_WIDTH / 2;
      const targetCenterY = targetRect
        ? (container.scrollTop || 0) + targetRect.top - (containerRect.top || 0) + targetRect.height / 2
        : (position?.y || 0) + NODE_HEIGHT / 2;
      const visibleWidth = container.clientWidth || containerRect.width || 0;
      const visibleHeight = container.clientHeight || containerRect.height || 0;
      container.scrollTo?.({
        left: clampScroll(targetCenterX - visibleWidth / 2, (container.scrollWidth || GRAPH_WIDTH) - visibleWidth),
        top: clampScroll(targetCenterY - visibleHeight / 2, (container.scrollHeight || layout?.height || 0) - visibleHeight),
        behavior: motionReduced ? "auto" : "smooth",
      });
      return true;
    },
    fit() {
      if (destroyed) return;
      record("fit");
      container.scrollTo?.({ top: 0, left: 0, behavior: motionReduced ? "auto" : "smooth" });
    },
    setReducedMotion(next) {
      motionReduced = Boolean(next);
    },
    reset() {
      if (destroyed) return;
      current = graphData(initial);
      render();
      record("reset");
      container.scrollTo?.({ top: 0, left: 0, behavior: "auto" });
    },
    inspect() {
      const positions = layout?.positions || new Map();
      return Object.freeze({
        layout: "layered-2d",
        reducedMotion: motionReduced,
        lastCommand,
        viewBox: Object.freeze({ width: GRAPH_WIDTH, height: layout?.height || 0 }),
        visibleKinds: Object.freeze([...new Set(current.nodes.map(node => node.kind))].sort()),
        nodes: Object.freeze(current.nodes.map(node => Object.freeze({
          id: node.id,
          kind: node.kind,
          position: Object.freeze({ ...(positions.get(node.id) || { x: 0, y: 0, column: 0 }) }),
        }))),
      });
    },
    destroy() {
      teardown();
    },
  };
}
