const NODE_COLORS = Object.freeze({
  KnowledgeFocus: "#f2c14e",
  KnowledgeDomain: "#4ea699",
  KnowledgeTag: "#8b7bb8",
  Project: "#4f86c6",
  Technology: "#d96c75",
  Artifact: "#7d8a96",
});

function rendererSize(container) {
  const bounds = container?.getBoundingClientRect?.() || {};
  const width = Math.max(1, Math.round(Number(bounds.width) || Number(container?.clientWidth) || 960));
  const height = Math.max(1, Math.round(Number(bounds.height) || Number(container?.clientHeight) || 620));
  return { width, height };
}

function toRendererData(graph) {
  return {
    nodes: (graph?.nodes || []).map(node => ({ ...node })),
    links: (graph?.links ?? graph?.edges ?? []).map(link => ({ ...link })),
  };
}

function nodeTooltip(node, documentRef) {
  if (!node?.active && node?.kind !== "KnowledgeFocus") return "";
  if (typeof documentRef?.createElement !== "function") return "";
  const label = documentRef.createElement("span");
  label.textContent = `${node.label} · ${node.kind}`;
  return label;
}

function focusCamera(instance, node, duration) {
  if (!node || typeof node !== "object") return false;
  const x = Number(node.x) || 0;
  const y = Number(node.y) || 0;
  const z = Number(node.z) || 0;
  const distance = Math.hypot(x, y, z);
  const position = distance > 0
    ? { x: x * (1 + 120 / distance), y: y * (1 + 120 / distance), z: z * (1 + 120 / distance) }
    : { x: 0, y: 0, z: 120 };
  instance.cameraPosition(position, node, duration);
  return true;
}

export function supportsWebGL(documentRef = globalThis.document) {
  try {
    if (typeof documentRef?.createElement !== "function") return false;
    const canvas = documentRef.createElement("canvas");
    if (typeof canvas?.getContext !== "function") return false;
    return Boolean(canvas.getContext("webgl2"));
  } catch {
    return false;
  }
}

export function createGraphView(container, graph, {
  forceGraphFactory = (element, config) => {
    if (typeof globalThis.ForceGraph3D !== "function") throw new Error("force_graph_3d_unavailable");
    return new globalThis.ForceGraph3D(element, config);
  },
  onSelect = () => {},
  reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false,
  documentRef = globalThis.document,
} = {}) {
  if (typeof forceGraphFactory !== "function") throw new Error("force_graph_3d_unavailable");

  let motionReduced = Boolean(reducedMotion);
  const initialGraph = toRendererData(graph);
  const size = rendererSize(container);
  const previousWidth = container.style.width;
  const previousHeight = container.style.height;
  container.style.width = `${size.width}px`;
  container.style.height = `${size.height}px`;

  let instance;
  try {
    instance = forceGraphFactory(container, {
      controlType: "orbit",
      rendererConfig: { antialias: true, alpha: true },
    });
  } finally {
    container.style.width = previousWidth;
    container.style.height = previousHeight;
  }

  instance
    .nodeId("id")
    .linkSource("source")
    .linkTarget("target")
    .nodeLabel(node => nodeTooltip(node, documentRef))
    .nodeColor(node => NODE_COLORS[node.kind] || NODE_COLORS.Artifact)
    .nodeOpacity(node => node.dimmed ? 0.18 : 0.92)
    .linkOpacity(link => link.dimmed ? 0.05 : 0.42)
    .onNodeClick(node => onSelect(node))
    .onNodeDragEnd((node) => {
      node.fx = node.x;
      node.fy = node.y;
      node.fz = node.z;
    })
    .cooldownTicks(motionReduced ? 18 : 80)
    .warmupTicks(motionReduced ? 12 : 0)
    .graphData(toRendererData(initialGraph));

  if (motionReduced) instance.d3AlphaDecay(0.3);

  let destroyed = false;
  const ResizeObserverClass = globalThis.ResizeObserver;
  const resizeObserver = typeof ResizeObserverClass === "function"
    ? new ResizeObserverClass((entries) => {
      if (destroyed) return;
      const entry = entries.find(item => item.target === container) || entries[0];
      const nextSize = entry?.contentRect
        ? {
          width: Math.max(1, Math.round(Number(entry.contentRect.width) || 1)),
          height: Math.max(1, Math.round(Number(entry.contentRect.height) || 1)),
        }
        : rendererSize(container);
      instance.width(nextSize.width).height(nextSize.height);
    })
    : null;
  resizeObserver?.observe(container);

  return {
    update(next) {
      instance.graphData(toRendererData(next));
    },
    focus(node) {
      return focusCamera(instance, node, motionReduced ? 0 : 700);
    },
    fit() {
      instance.zoomToFit(motionReduced ? 0 : 500, 70);
    },
    setReducedMotion(next) {
      const normalized = Boolean(next);
      if (normalized === motionReduced) return;
      motionReduced = normalized;
      instance
        .cooldownTicks(motionReduced ? 18 : 80)
        .warmupTicks(motionReduced ? 12 : 0);
      if (motionReduced) instance.d3AlphaDecay(0.3);
    },
    reset() {
      instance.graphData(toRendererData(initialGraph));
      instance.zoomToFit(0, 70);
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      resizeObserver?.disconnect();
      instance.pauseAnimation();
      instance._destructor?.();
      container.replaceChildren();
    },
  };
}
