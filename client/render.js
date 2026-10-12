import { toRouteHref, PROJECT_TABS } from "./router.js";
import { renderMarkdown, sanitizeSvg } from "./markdown.js";
import { toSafePublicHref } from "./public-url.js";
import { createGraphView, supportsSvg } from "./graph-view.js";
import { createGraphifyView, createProjectConnectionsView, createSourceGraphView } from "./graphify-view.js";
import { buildProjectConnections } from "./project-connections.js";
import {
  createGraphIndex,
  expandNode,
  initialGraphState,
  revealPath,
  setRelationFilters,
  visibleGraph,
} from "./graph-state.js";

const TAB_LABELS = {
  "decisions": "Decisions",
  "system-map": "System Map",
  "build-timeline": "Build Timeline",
  "evidence": "Evidence"
};

const KIND_LABELS = {
  domain: "Domain",
  problem: "Problem",
  pattern: "Pattern",
  technology: "Technology",
  outcome: "Outcome"
};

const GRAPH_KIND_COLORS = {
  KnowledgeFocus: "#f2c14e",
  KnowledgeDomain: "#4ea699",
  KnowledgeTag: "#8b7bb8",
  Project: "#4f86c6",
  Technology: "#d96c75",
  Artifact: "#7d8a96"
};

const GRAPH_KIND_LABELS = {
  KnowledgeFocus: "핵심 주제",
  KnowledgeDomain: "도메인",
  KnowledgeTag: "태그",
  Project: "프로젝트",
  Technology: "기술",
  Artifact: "산출물"
};

const SYSTEM_MAP_FAMILY_TYPES = {
  "버전 로드맵": new Set(["hybrid-drive-recording", "navigation-flow", "planned-route-recording", "road-recording"]),
  "상태 전이": new Set(["approval-workflow", "cross-surface-ledger", "personal-agent-service", "relationship-chat", "state-machine-ui"]),
  "평가 루프": new Set(["agent-test-lifecycle", "dataset-release-pipeline", "evaluation-pipeline", "learning-loop", "multiturn-evaluation", "testset-generation"]),
  "에이전트 오케스트레이션": new Set(["agent-execution-control", "agent-routing", "language-schema-pipeline", "memory-distribution", "retrieval-routing", "routing-pipeline", "tool-registry"]),
  "서비스 경계": new Set(["browser-extension-service", "browser-instrument", "documentation-publishing", "local-desktop-app", "local-finance-app", "private-content-service"]),
};

const GRAPH_RELATION_LABELS = {
  HAS_FOCUS: "핵심 주제",
  FOCUS_HAS_TAG: "주제 분류",
  HAS_SUBTAG: "하위 태그",
  HAS_TAG: "태그",
  USES_TECH: "사용 기술",
  PRODUCES_ARTIFACT: "산출물",
  ARTIFACT_HAS_TAG: "산출물 태그",
  EVOLVED_FROM: "발전 관계",
  VALIDATES: "검증",
  DEPLOYS: "배포",
  REUSES_COMPONENT: "구성요소 재사용"
};

const SECTION_TYPE_LABELS = {
  planning: "Planning",
  decision: "Decision",
  implementation: "Implementation",
  validation: "Validation",
  result: "Result"
};

const EVIDENCE_TYPE_LABELS = {
  session: "Sessions",
  spec: "Specs",
  code: "Code",
  test: "Tests",
  git: "Git",
  project_memory: "Project Memory"
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[character]));
}

function flattenTags(project) {
  return Object.values(project.tags || {}).flat().filter(Boolean);
}

function projectCard(project, index) {
  const tags = flattenTags(project).slice(0, 4);
  const pinned = Boolean(project.pinned);
  const href = toRouteHref({ view: "project", projectId: project.id });
  return `
    <article class="project-card" data-project-card>
      <div class="project-card-top">
        <a class="project-card-index-link" data-route-link href="${href}" aria-label="${escapeHtml(project.name || project.id)} 열기"><span class="project-index">${String(index + 1).padStart(2, "0")}</span></a>
        <div class="project-card-actions">
          <span class="status-dot ${project.lifecycle === "active" ? "active" : ""}" aria-label="${project.lifecycle === "active" ? "진행 중" : "완료"}"></span>
          <span class="project-star ${pinned ? "is-pinned" : ""}" role="img" aria-label="${pinned ? "대표 프로젝트" : "일반 프로젝트"}" title="${pinned ? "대표 프로젝트" : "일반 프로젝트"}"><i data-lucide="star" aria-hidden="true"></i></span>
        </div>
      </div>
      <a class="project-card-body" data-route-link href="${href}">
        <h2>${escapeHtml(project.name || project.id)}</h2>
        <p>${escapeHtml(project.summary)}</p>
        <div class="tag-row">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
      </a>
    </article>`;
}

function pageHeading(kicker, title, description = "", action = "") {
  const heading = title || kicker;
  return `
    <div class="page-heading">
      <div class="page-heading-copy">
        <p class="eyebrow">${escapeHtml(kicker)}</p>
        <h1${title ? "" : ' class="sr-only"'}>${escapeHtml(heading)}</h1>
        ${description ? `<p>${escapeHtml(description)}</p>` : ""}
      </div>
      ${action ? `<div class="page-heading-actions">${action}</div>` : ""}
    </div>`;
}

function projectCounts(bootstrap) {
  const projects = bootstrap.projects || [];
  return {
    all: projects.length,
    active: projects.filter((project) => project.lifecycle === "active").length,
    topics: bootstrap.topics?.length || 0,
    changes: bootstrap.changelog?.length || 0
  };
}

function renderHome(state) {
  const bootstrap = state.bootstrap;
  const counts = projectCounts(bootstrap);
  const projects = bootstrap.projects || [];
  const featured = [...projects]
    .sort((left, right) => Number(Boolean(right.pinned)) - Number(Boolean(left.pinned)))
    .slice(0, 6);
  const latestChanges = [...(bootstrap.changelog || [])].sort((left, right) => String(right.date || "").localeCompare(String(left.date || ""))).slice(0, 4);
  return `
    <div class="content-shell">
      ${pageHeading("Project knowledge base", "", "완성된 결과와 그 과정에서 바뀐 판단을 프로젝트 단위로 정리합니다.")}
      <div class="summary-strip" aria-label="Atlas 요약">
        <div class="summary-stat"><span>Projects</span><strong>${counts.all}</strong></div>
        <div class="summary-stat"><span>Active</span><strong>${counts.active}</strong></div>
        <div class="summary-stat"><span>Topics</span><strong>${counts.topics}</strong></div>
        <div class="summary-stat"><span>Changes</span><strong>${counts.changes}</strong></div>
      </div>
      <div class="section-bar"><h2>Selected projects</h2><a class="text-link" href="/projects" data-route-link>전체 보기</a></div>
      <div class="project-grid">${featured.map((project, index) => projectCard(project, index)).join("")}</div>
      ${latestChanges.length ? `
        <div class="section-bar"><h2>Recent changes</h2><a class="text-link" href="/changelog" data-route-link>전체 기록</a></div>
        ${changelogRows(latestChanges, projects)}` : ""}
    </div>`;
}

function renderProjects(state) {
  const projects = state.bootstrap.projects || [];
  const domains = [...new Set(projects.flatMap((project) => project.tags?.domain || []))].sort((a, b) => a.localeCompare(b));
  return `
    <div class="content-shell">
      ${pageHeading("Projects", "", "프로젝트 별 결과/결정, 작업 지도", `<span class="project-count-badge" data-project-count aria-label="전체 프로젝트 ${projects.length}개">전체 ${projects.length}</span><button class="icon-button" type="button" data-search-trigger-inline aria-label="프로젝트 검색" title="검색"><i data-lucide="search" aria-hidden="true"></i></button>`)}
      <div class="filter-toolbar" aria-label="프로젝트 필터">
        <button class="filter-button" type="button" data-project-filter="all" aria-pressed="true">All</button>
        <button class="filter-button" type="button" data-project-filter="active" aria-pressed="false">Active</button>
        <button class="filter-button" type="button" data-project-filter="finished" aria-pressed="false">Finished</button>
        ${domains.map((domain) => `<button class="filter-button" type="button" data-domain-filter="${escapeHtml(domain)}" aria-pressed="false">${escapeHtml(domain)}</button>`).join("")}
      </div>
      <div class="project-grid" data-project-grid>${projects.map((project, index) => projectCard(project, index)).join("")}</div>
      <p class="empty-state" data-project-empty hidden>조건에 맞는 프로젝트가 없습니다.</p>
    </div>`;
}

function bindProjectFilters(root, state) {
  const projects = state.bootstrap.projects || [];
  const grid = root.querySelector("[data-project-grid]");
  if (!grid) return () => {};
  const statusButtons = [...root.querySelectorAll("[data-project-filter]")];
  const domainButtons = [...root.querySelectorAll("[data-domain-filter]")];
  let status = "all";
  let domain = "";
  const draw = () => {
    const filtered = projects.filter((project) => {
      const statusMatches = status === "all" || project.lifecycle === status;
      const domainMatches = !domain || (project.tags?.domain || []).includes(domain);
      return statusMatches && domainMatches;
    });
    grid.innerHTML = filtered.map((project, index) => projectCard(project, index)).join("");
    try { window.lucide?.createIcons(); } catch { /* Keep text controls usable without SVG icons. */ }
    root.querySelector("[data-project-empty]").hidden = filtered.length > 0;
  };
  const onClick = (event) => {
    const statusButton = event.target.closest("[data-project-filter]");
    const domainButton = event.target.closest("[data-domain-filter]");
    if (statusButton) {
      status = statusButton.dataset.projectFilter;
      statusButtons.forEach((button) => button.setAttribute("aria-pressed", String(button === statusButton)));
    }
    if (domainButton) {
      const selected = domainButton.getAttribute("aria-pressed") !== "true";
      domain = selected ? domainButton.dataset.domainFilter : "";
      domainButtons.forEach((button) => button.setAttribute("aria-pressed", String(selected && button === domainButton)));
    }
    if (statusButton || domainButton) draw();
  };
  root.addEventListener("click", onClick);
  return () => root.removeEventListener("click", onClick);
}

function renderTopics(state) {
  const projects = new Map((state.bootstrap.projects || []).map((project) => [project.id, project]));
  const groups = new Map();
  for (const topic of state.bootstrap.topics || []) {
    if (!groups.has(topic.kind)) groups.set(topic.kind, []);
    groups.get(topic.kind).push(topic);
  }
  const content = [...groups.entries()].map(([kind, topics]) => `
    <section class="topic-group">
      <div class="topic-group-heading"><h2>${escapeHtml(KIND_LABELS[kind] || kind)}</h2><span>${topics.length}</span></div>
      <div class="topic-list">
        ${topics.sort((a, b) => b.project_ids.length - a.project_ids.length || a.label.localeCompare(b.label)).map((topic) => {
          const firstProject = projects.get(topic.project_ids[0]);
          return `<a class="topic-link" data-route-link href="${firstProject ? `/projects/${encodeURIComponent(firstProject.id)}` : "/projects"}"><strong>${escapeHtml(topic.label)}</strong><span>${topic.project_ids.length}</span></a>`;
        }).join("")}
      </div>
    </section>`).join("");
  return `<div class="content-shell">${pageHeading("Topics", "", "도메인, 문제, 작업 패턴, 기술 결과 별 태그 모음")}<div class="topic-groups">${content || '<p class="empty-state">등록된 주제가 없습니다.</p>'}</div></div>`;
}

function changelogRows(changes, projects) {
  const names = new Map(projects.map((project) => [project.id, project.name || project.id]));
  return `<div class="changelog">${changes.map((change) => `
    <article class="change-row">
      <time class="change-date">${escapeHtml(change.date || "No date")}</time>
      <a class="change-project" data-route-link href="/projects/${encodeURIComponent(change.project_id)}">${escapeHtml(names.get(change.project_id) || change.project_id)}</a>
      <div class="change-copy"><h2>${escapeHtml(change.title)}</h2><p>${escapeHtml(change.outcome || change.decision || change.context)}</p></div>
    </article>`).join("")}</div>`;
}

function renderChangelog(state) {
  const changes = [...(state.bootstrap.changelog || [])].sort((left, right) => String(right.date || "").localeCompare(String(left.date || "")));
  return `<div class="content-shell">${pageHeading("Changelog", "", "프로젝트 변경점 기록")}${changes.length ? changelogRows(changes, state.bootstrap.projects || []) : '<p class="empty-state">공개된 변경 기록이 없습니다.</p>'}</div>`;
}

function projectHref(node) {
  if (node?.kind !== "Project" || !node.id?.startsWith("project:")) return "";
  return `/projects/${encodeURIComponent(node.id.slice("project:".length))}`;
}

function graphNeighborId(edge, nodeId) {
  return edge.source === nodeId ? edge.target : edge.source;
}

function fallbackForest(graph) {
  const nodes = new Map((graph.nodes || []).map((node) => [node.id, node]));
  const adjacency = new Map([...nodes.keys()].map((nodeId) => [nodeId, []]));
  for (const edge of graph.edges || []) {
    if (!nodes.has(edge.source) || !nodes.has(edge.target)) continue;
    adjacency.get(edge.source).push(edge);
    adjacency.get(edge.target).push(edge);
  }
  for (const [nodeId, edges] of adjacency) {
    edges.sort((left, right) => {
      const leftId = graphNeighborId(left, nodeId);
      const rightId = graphNeighborId(right, nodeId);
      return String(nodes.get(leftId)?.label || leftId).localeCompare(String(nodes.get(rightId)?.label || rightId), "ko")
        || String(left.kind).localeCompare(String(right.kind))
        || String(left.id).localeCompare(String(right.id));
    });
  }

  const roots = [...nodes.values()]
    .filter((node) => node.kind === "KnowledgeFocus")
    .sort((left, right) => left.label.localeCompare(right.label, "ko"));
  const children = new Map([...nodes.keys()].map((nodeId) => [nodeId, []]));
  const seen = new Set(roots.map((node) => node.id));
  const queue = roots.map((node) => node.id);
  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const nodeId = queue[cursor];
    for (const edge of adjacency.get(nodeId) || []) {
      const nextId = graphNeighborId(edge, nodeId);
      if (seen.has(nextId)) continue;
      seen.add(nextId);
      children.get(nodeId).push(nextId);
      queue.push(nextId);
    }
  }

  return {
    nodes,
    roots,
    children,
    orphans: [...nodes.values()].filter((node) => !seen.has(node.id)),
  };
}

function fallbackTreeItem(nodeId, forest) {
  const node = forest.nodes.get(nodeId);
  if (!node) return "";
  const rawLabel = String(node.label || node.id);
  const label = escapeHtml(rawLabel);
  const kind = escapeHtml(GRAPH_KIND_LABELS[node.kind] || node.kind);
  const href = projectHref(node);
  const control = href
    ? `<a href="${href}" data-route-link data-fallback-node="${escapeHtml(node.id)}">${label}<span>${kind}</span></a>`
    : `<button type="button" data-fallback-select="${escapeHtml(node.id)}" data-fallback-node="${escapeHtml(node.id)}">${label}<span>${kind}</span></button>`;
  const children = forest.children.get(nodeId) || [];
  return `<li data-fallback-item data-fallback-label="${escapeHtml(rawLabel.toLocaleLowerCase("ko"))}">
    ${control}
    ${children.length ? `<ul>${children.map((childId) => fallbackTreeItem(childId, forest)).join("")}</ul>` : ""}
  </li>`;
}

function renderGraphFallback(graph) {
  const forest = fallbackForest(graph);
  const branches = forest.roots.map((focus) => `<details open>
    <summary data-fallback-node="${escapeHtml(focus.id)}" data-fallback-label="${escapeHtml(focus.label.toLocaleLowerCase("ko"))}">${escapeHtml(focus.label)}</summary>
    <ul>${(forest.children.get(focus.id) || []).map((nodeId) => fallbackTreeItem(nodeId, forest)).join("")}</ul>
  </details>`).join("");
  const orphans = forest.orphans.length
    ? `<details open><summary>기타</summary><ul>${forest.orphans.map((node) => fallbackTreeItem(node.id, forest)).join("")}</ul></details>`
    : "";
  return `<section class="graph-fallback" data-graph-fallback hidden aria-label="프로젝트 지식 그래프 목록">
    <div class="graph-fallback-heading">
      <h2>목록으로 보기</h2>
      <p>그래프를 표시할 수 없어 연결 구조를 목록으로 제공합니다.</p>
    </div>
    <label class="graph-fallback-search">
      <span class="sr-only">그래프 노드 검색</span>
      <i data-lucide="search" aria-hidden="true"></i>
      <input type="search" placeholder="노드 검색" autocomplete="off" data-graph-fallback-search>
    </label>
    <div class="graph-fallback-tree">${branches}${orphans}</div>
    <p class="graph-fallback-empty" data-graph-fallback-empty hidden>일치하는 노드가 없습니다.</p>
  </section>`;
}

function renderEvidenceLinks(links) {
  const safeLinks = (links || []).map((link) => {
    const href = toSafePublicHref(link.url, { allowRelative: true });
    if (!href) return "";
    const external = href.startsWith("https://");
    return `<a href="${escapeHtml(href)}"${external ? ' target="_blank" rel="noreferrer"' : " data-route-link"}>${escapeHtml(link.label || "근거 보기")}</a>`;
  }).filter(Boolean);
  return safeLinks.length ? `<div class="graph-evidence-links">${safeLinks.join("")}</div>` : "";
}

function renderGraphDetail(graphState, index) {
  const selected = graphState.selectedId ? index.nodes.get(graphState.selectedId) : null;
  if (!selected) {
    return `<div class="graph-detail-empty">
      <p class="graph-detail-kicker">선택한 노드</p>
      <h2 data-selected-node>노드를 선택하세요</h2>
      <p>연결 관계와 공개 근거를 확인할 수 있습니다.</p>
    </div>`;
  }

  const relations = (index.adjacency.get(selected.id) || []).filter((edge) => (
    graphState.visibleEdgeIds.has(edge.id) && graphState.relationKinds.has(edge.kind)
  ));
  const href = projectHref(selected);
  return `<div class="graph-detail-content">
    <p class="graph-detail-kicker">${escapeHtml(GRAPH_KIND_LABELS[selected.kind] || selected.kind)}</p>
    <h2 data-selected-node>${escapeHtml(selected.label || selected.id)}</h2>
    ${selected.summary ? `<p class="graph-node-summary">${escapeHtml(selected.summary)}</p>` : ""}
    ${href ? `<a class="graph-project-link" href="${href}" data-route-link data-project-article-link>프로젝트 글 보기<i data-lucide="arrow-up-right" aria-hidden="true"></i></a>` : ""}
    <div class="graph-relation-panel">
      <h3>연결 관계</h3>
      <div class="graph-relation-list" data-selected-relations>
        ${relations.length ? relations.map((edge) => {
          const neighbor = index.nodes.get(graphNeighborId(edge, selected.id));
          return `<article class="graph-relation-row">
            <div class="graph-relation-heading"><span>${escapeHtml(GRAPH_RELATION_LABELS[edge.kind] || edge.kind)}</span><code>${escapeHtml(edge.kind)}</code></div>
            <strong>${escapeHtml(neighbor?.label || graphNeighborId(edge, selected.id))}</strong>
            ${renderEvidenceLinks(edge.evidence_links)}
          </article>`;
        }).join("") : '<p class="graph-relation-empty">현재 표시할 관계가 없습니다.</p>'}
      </div>
    </div>
  </div>`;
}

function renderGraph(state) {
  const graph = state.graph || { nodes: [], edges: [] };
  const relationKinds = [...new Set((graph.edges || []).map((edge) => edge.kind))].sort();
  const graphKinds = new Set((graph.nodes || []).map((node) => node.kind));
  const orderedKinds = [
    ...Object.keys(GRAPH_KIND_LABELS).filter((kind) => graphKinds.has(kind)),
    ...[...graphKinds].filter((kind) => !Object.hasOwn(GRAPH_KIND_LABELS, kind)).sort(),
  ];
  return `
    <div class="content-shell wide graph-page">
      ${pageHeading("지식 그래프", "", "프로젝트와 공통 주제의 근거 있는 연결을 단계별로 살펴봅니다.")}
      <div class="graph-shell" data-graph-shell>
        <section class="graph-stage" data-graph-stage aria-label="2D 지식 그래프">
          <div id="knowledge-graph" role="group" aria-label="프로젝트 지식 그래프" data-graph-canvas></div>
          <div class="graph-toolbar" aria-label="그래프 도구">
            <div class="graph-search-wrap">
              <label class="graph-search">
                <span class="sr-only">그래프 노드 검색</span>
                <i data-lucide="search" aria-hidden="true"></i>
                <input type="search" placeholder="노드 검색" autocomplete="off" data-graph-search aria-controls="graph-search-results" aria-expanded="false">
              </label>
              <div id="graph-search-results" class="graph-search-results" data-graph-search-results role="listbox" hidden></div>
            </div>
            <details class="graph-relation-menu" data-graph-relation-menu>
              <summary>관계 <span data-graph-relation-count>${relationKinds.length}</span></summary>
              <div class="graph-relation-options">
                ${relationKinds.map((kind) => `<label><input type="checkbox" value="${escapeHtml(kind)}" checked data-graph-relation-filter><span>${escapeHtml(GRAPH_RELATION_LABELS[kind] || kind)}</span></label>`).join("")}
              </div>
            </details>
            <button class="icon-button" type="button" data-graph-fit aria-label="그래프 맞춤 보기" title="맞춤 보기"><i data-lucide="maximize-2" aria-hidden="true"></i></button>
            <button class="icon-button" type="button" data-graph-reset aria-label="그래프 초기화" title="초기화"><i data-lucide="rotate-ccw" aria-hidden="true"></i></button>
          </div>
          <p class="graph-status" data-graph-status><output data-graph-node-count>0</output>개 노드</p>
        </section>
        ${renderGraphFallback(graph)}
        <aside class="graph-sidebar" data-graph-detail aria-live="polite">
          <div data-graph-detail-content></div>
          <section class="graph-legend" aria-labelledby="graph-legend-title">
            <h2 id="graph-legend-title">노드 유형</h2>
            <ul>${orderedKinds.map((kind) => `<li><span class="graph-swatch" style="--kind-color: ${GRAPH_KIND_COLORS[kind] || "var(--muted)"}"></span><span>${escapeHtml(GRAPH_KIND_LABELS[kind] || kind)}</span></li>`).join("")}</ul>
          </section>
        </aside>
      </div>
    </div>`;
}

function renderCodeGraph(state) {
  const graph = state.codeGraph || { nodes: [], edges: [], folders: [], corpus: { nodes: 0, edges: 0 } };
  const fileCount = graph.nodes.filter(node => node.kind === "file").length;
  const relationCount = graph.edges.filter(edge => edge.kind === "relation").length;
  return `<div class="content-shell wide graph-page">
    ${pageHeading("Graphify · Atlas 구조", "", "Portfolio 홈페이지 코드의 파일 관계를 둥근 네트워크로 탐색합니다.")}
    ${graphifyScopeTabs("code")}
    <p class="graphify-summary">Graphify 원본 ${graph.corpus.nodes}개 심벌 · ${graph.corpus.edges}개 관계에서 공개 가능한 ${graph.folders.length}개 폴더 · ${fileCount}개 파일 · ${relationCount}개 파일 간 관계를 표시합니다.</p>
    <div class="graph-shell code-graph-shell">
      <section class="graph-stage graphify-stage" aria-label="Graphify Atlas 네트워크">
        <div id="code-knowledge-graph" data-code-graph-canvas role="img" aria-label="폴더와 파일이 둥근 군집으로 연결된 Graphify 네트워크"></div>
        <div class="graphify-controls">
          <label><span class="sr-only">Graphify 파일 검색</span><input type="search" data-code-graph-search placeholder="파일·폴더 검색" autocomplete="off"></label>
          <button type="button" data-code-graph-fit>전체 보기</button>
        </div>
        <p class="graph-status" data-code-graph-status>파일을 클릭하거나 검색해 연결을 확인하세요.</p>
      </section>
      <aside class="graph-sidebar code-graph-sidebar">
        <div data-code-graph-detail aria-live="polite"><h2>폴더나 파일을 선택하세요</h2><p>색은 최상위 폴더를 뜻하고, 점은 파일, 선은 Graphify가 추출한 관계를 뜻합니다.</p></div>
        <div data-code-graph-results hidden></div>
        <h3>분석된 폴더</h3>
        <ul class="code-graph-file-list">${graph.folders.map(folder => `<li><button type="button" data-code-graph-select="folder:${escapeHtml(folder.id)}">${escapeHtml(folder.id)} <span>${folder.fileCount}</span></button></li>`).join("")}</ul>
        <p class="code-graph-source">출처: Graphify 로컬 분석. 공개 화면에는 파일명과 관계만 표시하며, 생성물·외부 라이브러리·비공개 지침은 제외합니다.</p>
      </aside>
    </div>
  </div>`;
}

function graphifyScopeTabs(scope) {
  return `<nav class="graphify-scope-tabs" aria-label="Graphify 탐색 범위">
    <a href="/graphify" data-route-link${scope === "source" ? ' aria-current="page"' : ""}>전체 소스 그래프</a>
    <a href="/graphify?scope=projects" data-route-link${scope === "projects" ? ' aria-current="page"' : ""}>프로젝트 연결</a>
    <a href="/graphify?scope=code" data-route-link${scope === "code" ? ' aria-current="page"' : ""}>Atlas 코드 구조</a>
  </nav>`;
}

function renderSourceGraph(state) {
  const graph = state.sourceGraph;
  const localBrowser = ["127.0.0.1", "localhost", "::1"].includes(globalThis.location?.hostname);
  if (!graph) return `<div class="content-shell wide graph-page">
    ${pageHeading("Graphify · 전체 소스 그래프", "", "projects/ 전체의 코드, 문서, PDF, Office 파일에서 추출한 관계를 탐색합니다.")}
    ${graphifyScopeTabs("source")}
    <p class="graphify-summary">이 서버에는 전체 소스 그래프가 연결되지 않았습니다.${localBrowser ? ' 그래프 서버 주소는 <a href="http://127.0.0.1:4190/graphify">http://127.0.0.1:4190/graphify</a>입니다.' : ' 전체 소스 그래프는 로컬 서버에서 확인할 수 있습니다.'}</p>
  </div>`;
  const communityColors = new Map([...graph.communities].sort((a, b) => a.id.localeCompare(b.id)).map((item, index) => [item.id, ['#4E79A7','#F28E2B','#E15759','#76B7B2','#59A14F','#EDC948','#B07AA1','#FF9DA7','#9C755F','#7C92C8','#55A8A1'][index % 11]]));
  return `<div class="content-shell wide graph-page">
    ${pageHeading("Graphify · 전체 소스 그래프", "", "projects/ 하위 코드와 문서에서 Graphify가 추출한 개념과 관계를 탐색합니다.")}
    ${graphifyScopeTabs("source")}
    <p class="graphify-summary">전체 ${graph.summary.totalNodes.toLocaleString()}개 노드 · ${graph.summary.totalEdges.toLocaleString()}개 관계 · ${Number(graph.summary.totalHyperedges || 0).toLocaleString()}개 다자 관계 · ${graph.summary.totalCommunities.toLocaleString()}개 커뮤니티 · ${graph.summary.representedFiles.toLocaleString()}개 파일 · 현재 화면 ${graph.summary.visibleNodes.toLocaleString()}개 노드 / ${graph.summary.visibleEdges.toLocaleString()}개 선</p>
    <p class="graphify-summary">서로 다른 파일을 잇는 관계 ${Number(graph.summary.crossFileEdges || 0).toLocaleString()}개 · 프로젝트 간 관계 ${Number(graph.summary.crossProjectEdges || 0).toLocaleString()}개 (코드 외 개념 간 ${Number(graph.summary.crossProjectSemanticEdges || 0).toLocaleString()}개)</p>
    ${graph.coverage?.mode === 'priority' ? `<p class="graphify-summary">입력 범위: 프로젝트 ${Number(graph.coverage.projectGroups || 0).toLocaleString()}개 그룹의 지원 코드·PDF 전체, 프로젝트별 대표 문서·Office·이미지 일부. 문서 ${Number(graph.coverage.stagedFiles?.document || 0).toLocaleString()}개 · PDF ${Number(graph.coverage.stagedFiles?.paper || 0).toLocaleString()}개 · Office ${Number(graph.coverage.stagedFiles?.office || 0).toLocaleString()}개 · 이미지 ${Number(graph.coverage.stagedFiles?.image || 0).toLocaleString()}개를 입력했습니다.</p>` : ''}
    ${graph.coverage?.extraction && !graph.coverage.extraction.complete ? `<p class="graphify-summary graphify-incomplete">문서 의미 추출 진행 상태: ${Number(graph.coverage.extraction.succeeded_chunks || 0).toLocaleString()}/${Number(graph.coverage.extraction.total_chunks || 0).toLocaleString()}청크 성공. 실패한 청크의 문서 관계는 이 그래프에 없습니다.</p>` : ''}
    <p class="graphify-summary">추출 유형: ${Object.entries(graph.summary.kinds).sort((a, b) => b[1] - a[1]).map(([kind, count]) => `${escapeHtml(kind)} ${count.toLocaleString()}`).join(' · ')}</p>
    <div class="graph-shell code-graph-shell">
      <section class="graph-stage graphify-stage" aria-label="Graphify 전체 소스 네트워크">
        <div data-source-graph-canvas role="img" aria-label="코드와 문서 개념이 커뮤니티별로 연결된 네트워크"></div>
        <div class="graphify-controls">
          <label><span class="sr-only">개념 검색</span><input type="search" data-source-graph-search placeholder="개념·파일 검색" autocomplete="off"></label>
          <button type="button" data-source-graph-fit>전체 보기</button>
        </div>
        <p class="graph-status" data-source-graph-status>점을 선택하면 출처와 연결 근거를 확인할 수 있습니다.</p>
      </section>
      <aside class="graph-sidebar code-graph-sidebar">
        <label for="source-graph-project">프로젝트</label>
        <select id="source-graph-project" data-source-graph-project>
          <option value="">전체 프로젝트</option>
          ${graph.projects.map(item => `<option value="${escapeHtml(item.id)}"${graph.scope === item.id ? ' selected' : ''}>${escapeHtml(item.id)} · ${item.nodes.toLocaleString()}</option>`).join('')}
        </select>
        <div data-source-graph-detail aria-live="polite"><h2>노드를 선택하세요</h2><p>색은 Graphify 커뮤니티를 뜻합니다. 프로젝트를 고르면 그 프로젝트의 연결을 자세히 볼 수 있습니다.</p></div>
        <div data-source-graph-results hidden></div>
        <h3>커뮤니티</h3>
        <div class="source-graph-communities"><label><input type="checkbox" data-source-graph-all checked> 전체 선택</label>
          ${graph.communities.slice(0, 36).map(item => `<label><input type="checkbox" data-source-graph-community="${escapeHtml(item.id)}" checked><span class="graph-swatch" style="--kind-color:${communityColors.get(item.id)}"></span>${escapeHtml(item.label)} <span>${item.nodes}</span></label>`).join('')}
        </div>
        <p class="code-graph-source">Graphify AST·문서 의미 추출 결과입니다. 파일별 적용 범위는 로컬 스캔 기록에 표시합니다. 원본 그래프는 로컬 서버에서만 제공합니다.</p>
      </aside>
    </div>
  </div>`;
}

function bindSourceGraph(root, state, navigate) {
  const graph = state.sourceGraph;
  if (!graph) return () => {};
  const container = root.querySelector('[data-source-graph-canvas]');
  const detail = root.querySelector('[data-source-graph-detail]');
  const status = root.querySelector('[data-source-graph-status]');
  const search = root.querySelector('[data-source-graph-search]');
  const results = root.querySelector('[data-source-graph-results]');
  const byId = new Map(graph.nodes.map(node => [node.id, node]));
  const select = id => {
    const node = byId.get(id);
    if (!node) return;
    const related = graph.edges.filter(edge => edge.source === id || edge.target === id);
    const neighborRows = related.slice(0, 16).map(edge => {
      const other = byId.get(edge.source === id ? edge.target : edge.source);
      if (!other) return '';
      return `<li><strong>${escapeHtml(edge.relation)}</strong> → ${escapeHtml(other.label)} <small>${escapeHtml(other.file)} · ${escapeHtml(edge.confidence)}${edge.score == null ? '' : ` ${Number(edge.score).toFixed(2)}`}</small></li>`;
    }).join('');
    detail.innerHTML = `<h2>${escapeHtml(node.label)}</h2><p>${escapeHtml(node.project)} · ${escapeHtml(node.format)} · ${escapeHtml(node.kind)}</p><p>${escapeHtml(node.file)}${node.location ? ` · ${escapeHtml(node.location)}` : ''}</p><p>커뮤니티 ${escapeHtml(node.community)} · 화면 내 연결 ${related.length}개</p>${neighborRows ? `<h3>연결 관계</h3><ul class="source-graph-relations">${neighborRows}</ul>` : ''}`;
    status.textContent = `${node.label} · 연결 ${related.length}개`;
  };
  const view = createSourceGraphView(container, graph, { onSelect: select, onReady: () => { status.textContent = `${graph.summary.visibleNodes.toLocaleString()}개 노드 표시 중`; } });
  const onProject = () => navigate({ view: 'graphify', project: root.querySelector('[data-source-graph-project]').value });
  const projectSelect = root.querySelector('[data-source-graph-project]');
  projectSelect.addEventListener('change', onProject);
  const onFit = () => view.fit();
  root.querySelector('[data-source-graph-fit]').addEventListener('click', onFit);
  const onSearch = () => {
    const query = search.value.trim().toLocaleLowerCase();
    const matches = query ? graph.nodes.filter(node => `${node.label} ${node.file}`.toLocaleLowerCase().includes(query)).slice(0, 20) : [];
    results.hidden = !query;
    results.innerHTML = query ? `<h3>검색 결과 ${matches.length}개</h3><ul>${matches.map(node => `<li><button type="button" data-source-graph-select="${escapeHtml(node.id)}">${escapeHtml(node.label)} <small>${escapeHtml(node.project)}</small></button></li>`).join('')}</ul>` : '';
  };
  search.addEventListener('input', onSearch);
  const onResult = event => { const button = event.target.closest('[data-source-graph-select]'); if (button) view.focus(button.dataset.sourceGraphSelect); };
  results.addEventListener('click', onResult);
  const all = root.querySelector('[data-source-graph-all]');
  const checks = [...root.querySelectorAll('[data-source-graph-community]')];
  const onFilter = event => {
    if (event.target === all) checks.forEach(input => { input.checked = all.checked; });
    else all.checked = checks.every(input => input.checked);
    const hidden = new Set(checks.filter(input => !input.checked).map(input => input.dataset.sourceGraphCommunity));
    view.filter(new Set(graph.communities.map(item => item.id).filter(id => !hidden.has(id))));
  };
  all.addEventListener('change', onFilter);
  checks.forEach(input => input.addEventListener('change', onFilter));
  return () => view.destroy();
}

function renderProjectConnections(state) {
  const map = buildProjectConnections(state.graph);
  return `<div class="content-shell wide graph-page">
    ${pageHeading("Graphify · 프로젝트 연결", "", "프로젝트 폴더에서 검토된 공개 프로필의 공통 주제와 기술을 비교합니다.")}
    ${graphifyScopeTabs("projects")}
    ${state.sourceGraphUnavailable ? '<p class="graphify-summary">전체 소스 그래프는 이 서버에 연결되지 않았습니다. 공개 프로젝트 연결 그래프를 표시합니다.</p>' : ''}
    <p class="graphify-summary">${map.stats.projects}개 프로젝트 · 공통 속성 2개 이상인 쌍 ${map.stats.sharedPairs}개 · 근거가 기록된 직접 관계 ${map.stats.directPairs}개 · 강한 공통 속성이 없는 프로젝트 ${map.stats.isolatedProjects}개</p>
    <div class="graph-shell code-graph-shell">
      <section class="graph-stage graphify-stage" aria-label="프로젝트 연결 네트워크">
        <div id="project-connections-graph" data-project-connections-canvas role="img" aria-label="프로젝트 간 공통 속성과 직접 관계를 나타낸 네트워크"></div>
        <div class="graphify-controls">
          <label><span class="sr-only">프로젝트 검색</span><input type="search" data-project-connections-search placeholder="프로젝트 검색" autocomplete="off"></label>
          <button type="button" data-project-connections-fit>전체 보기</button>
        </div>
        <p class="graph-status" data-project-connections-status>프로젝트를 선택하면 연결 근거를 볼 수 있습니다.</p>
      </section>
      <aside class="graph-sidebar code-graph-sidebar">
        <div data-project-connections-detail aria-live="polite"><h2>프로젝트를 선택하세요</h2><p>실선은 프로젝트 메모리에 근거가 기록된 직접 관계입니다. 점선은 드문 주제·기술을 둘 이상 공유하는 분석상 유사성입니다.</p></div>
        <div data-project-connections-results hidden></div>
        <h3>전체 프로젝트</h3>
        <ul class="code-graph-file-list">${map.nodes.map(node => `<li><button type="button" data-project-connections-select="${escapeHtml(node.id)}">${escapeHtml(node.label)}</button></li>`).join("")}</ul>
        <p class="code-graph-source">출처: 현재 프로젝트 프로필과 일치하는 Project Atlas 공개 번들. 공통 속성은 계승·재사용의 증거가 아닙니다.</p>
      </aside>
    </div>
  </div>`;
}

function bindProjectConnections(root, state) {
  const map = buildProjectConnections(state.graph);
  const container = root.querySelector("[data-project-connections-canvas]");
  const detail = root.querySelector("[data-project-connections-detail]");
  const search = root.querySelector("[data-project-connections-search]");
  const results = root.querySelector("[data-project-connections-results]");
  const status = root.querySelector("[data-project-connections-status]");
  if (!container || !detail || !search || !results || !status) return () => {};
  const nodes = new Map(map.nodes.map(node => [node.id, node]));
  const select = id => {
    const node = nodes.get(id);
    if (!node) return;
    const links = map.edges.filter(edge => edge.source === id || edge.target === id)
      .sort((a, b) => (b.kind === "DIRECT") - (a.kind === "DIRECT") || b.score - a.score);
    detail.innerHTML = `<h2>${escapeHtml(node.label)}</h2><p>${escapeHtml(node.summary)}</p>
      <p>${links.length}개 연결 · <a href="${escapeHtml(toSafePublicHref(node.url, { allowRelative: true }) || "#")}" data-route-link>프로젝트 보기</a></p>
      <ul>${links.map(edge => {
        const other = nodes.get(edge.source === id ? edge.target : edge.source);
        const basis = edge.shared.map(item => item.label).join(" · ");
        const direct = edge.directRelations.map(item => item.kind).join(" · ");
        const evidence = edge.directRelations.flatMap(item => item.evidence_links || []).map(item => {
          const href = toSafePublicHref(item.url, { allowRelative: true });
          return href ? `<a href="${escapeHtml(href)}" data-route-link>${escapeHtml(item.label)}</a>` : "";
        }).join(" ");
        return `<li><button type="button" data-project-connections-select="${escapeHtml(other.id)}">${escapeHtml(other.label)}</button><span>${edge.kind === "DIRECT" ? `직접 관계 ${escapeHtml(direct)} ${evidence}` : `공통 속성 ${escapeHtml(basis)}`}</span></li>`;
      }).join("")}</ul>`;
    status.textContent = `${node.label} 선택됨`;
  };
  let view = null;
  try {
    view = createProjectConnectionsView(container, map, { onSelect: select, onReady: () => { status.textContent = "네트워크 준비 완료. 프로젝트를 선택하세요."; } });
  } catch {
    container.hidden = true;
    status.textContent = "네트워크를 표시할 수 없습니다. 오른쪽 프로젝트 목록에서 탐색할 수 있습니다.";
  }
  const onClick = event => {
    const button = event.target.closest("[data-project-connections-select]");
    if (!button) return;
    if (view) view.focus(button.dataset.projectConnectionsSelect);
    else select(button.dataset.projectConnectionsSelect);
  };
  const onSearch = () => {
    const query = search.value.trim().toLocaleLowerCase();
    if (!query) { results.hidden = true; results.innerHTML = ""; return; }
    const matches = map.nodes.filter(node => node.label.toLocaleLowerCase().includes(query) || node.id.includes(query));
    results.hidden = false;
    results.innerHTML = `<h3>검색 결과 ${matches.length}개</h3><ul>${matches.map(node => `<li><button type="button" data-project-connections-select="${escapeHtml(node.id)}">${escapeHtml(node.label)}</button></li>`).join("")}</ul>`;
  };
  const onFit = () => view?.fit();
  root.addEventListener("click", onClick);
  search.addEventListener("input", onSearch);
  root.querySelector("[data-project-connections-fit]").addEventListener("click", onFit);
  return () => {
    root.removeEventListener("click", onClick);
    search.removeEventListener("input", onSearch);
    view?.destroy();
  };
}

function bindCodeGraph(root, state) {
  const graph = state.codeGraph;
  const container = root.querySelector("[data-code-graph-canvas]");
  const detail = root.querySelector("[data-code-graph-detail]");
  if (!graph || !container || !detail) return () => {};
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  const search = root.querySelector("[data-code-graph-search]");
  const results = root.querySelector("[data-code-graph-results]");
  const status = root.querySelector("[data-code-graph-status]");
  const select = (id) => {
    const node = nodes.get(id);
    if (!node) return;
    const connections = graph.edges.filter(edge => edge.kind === "relation" && (edge.source === id || edge.target === id));
    const contained = node.kind === "folder" ? graph.nodes.filter(item => item.kind === "file" && item.folder === node.folder) : [];
    detail.innerHTML = `<h2>${escapeHtml(node.id)}</h2><p>${node.kind === "folder" ? `${contained.length}개 분석 파일` : `${node.symbols}개 Graphify 심벌 · ${connections.length}개 파일 간 연결`}</p>
      <ul>${(node.kind === "folder" ? contained.slice(0, 40).map(item => `<li><button type="button" data-code-graph-select="${escapeHtml(item.id)}">${escapeHtml(item.label)}</button></li>`) : connections.slice(0, 40).map(edge => {
        const other = edge.source === id ? edge.target : edge.source;
        return `<li><button type="button" data-code-graph-select="${escapeHtml(other)}">${escapeHtml(other)}</button> <span>${escapeHtml(edge.relations.join(" · "))}</span></li>`;
      })).join("")}</ul>`;
    status.textContent = `${node.id} 선택됨`;
  };
  let view = null;
  try {
    view = createGraphifyView(container, graph, { onSelect: select, onReady: () => { status.textContent = "네트워크 준비 완료. 점을 클릭하거나 파일을 검색하세요."; } });
  } catch {
    container.hidden = true;
    status.textContent = "네트워크를 표시할 수 없습니다. 오른쪽 폴더 목록에서 파일을 탐색할 수 있습니다.";
  }
  const onClick = event => {
    const button = event.target.closest("[data-code-graph-select]");
    if (button) {
      if (view) view.focus(button.dataset.codeGraphSelect);
      else select(button.dataset.codeGraphSelect);
    }
  };
  const onSearch = () => {
    const query = search.value.trim().toLocaleLowerCase();
    if (!query) { results.hidden = true; results.innerHTML = ""; return; }
    const matches = graph.nodes.filter(node => node.id.toLocaleLowerCase().includes(query)).slice(0, 20);
    results.hidden = false;
    results.innerHTML = `<h3>검색 결과 ${matches.length}개${matches.length === 20 ? "+" : ""}</h3><ul>${matches.map(node => `<li><button type="button" data-code-graph-select="${escapeHtml(node.id)}">${escapeHtml(node.id)}</button></li>`).join("")}</ul>`;
  };
  const onFit = () => view?.fit();
  root.addEventListener("click", onClick);
  search.addEventListener("input", onSearch);
  root.querySelector("[data-code-graph-fit]").addEventListener("click", onFit);
  return () => {
    root.removeEventListener("click", onClick);
    search.removeEventListener("input", onSearch);
    view?.destroy();
  };
}

export function bindGraph(root, state, {
  createView = createGraphView,
  canRender = supportsSvg,
} = {}) {
  const container = root.querySelector("#knowledge-graph");
  if (!container || !state.graph) return () => {};
  const index = createGraphIndex(state.graph);
  let graphState = initialGraphState(index);
  let view = null;
  const shell = root.querySelector("[data-graph-shell]");
  const stage = root.querySelector("[data-graph-stage]");
  const fallback = root.querySelector("[data-graph-fallback]");
  const detail = root.querySelector("[data-graph-detail-content]");
  const nodeCount = root.querySelector("[data-graph-node-count]");
  const status = root.querySelector("[data-graph-status]");
  const graphSearch = root.querySelector("[data-graph-search]");
  const graphSearchResults = root.querySelector("[data-graph-search-results]");
  const fallbackSearch = root.querySelector("[data-graph-fallback-search]");

  const update = () => {
    const projected = visibleGraph(graphState, index);
    projected.nodes = projected.nodes.map((node) => ({
      ...node,
      projectCount: node.kind === "KnowledgeTag"
        ? new Set((index.adjacency.get(node.id) || [])
          .filter((edge) => edge.kind === "HAS_TAG" && edge.target === node.id)
          .map((edge) => edge.source)
          .filter((nodeId) => index.nodes.get(nodeId)?.kind === "Project")).size
        : undefined,
    }));
    view?.update(projected);
    nodeCount.textContent = String(projected.nodes.length);
    status.setAttribute("aria-label", `${projected.nodes.length}개 노드, ${projected.links.length}개 관계`);
    detail.innerHTML = renderGraphDetail(graphState, index);
    try { window.lucide?.createIcons(); } catch { /* Keep graph fallback usable without SVG icons. */ }
    const checkedCount = root.querySelectorAll("[data-graph-relation-filter]:checked").length;
    const relationCount = root.querySelector("[data-graph-relation-count]");
    if (relationCount) relationCount.textContent = String(checkedCount);
  };

  const selectNode = (nodeId, rendererNode = null, reveal = false) => {
    if (!index.nodes.has(nodeId)) return;
    if (reveal) graphState = revealPath(graphState, nodeId, index);
    graphState = expandNode(graphState, nodeId, index);
    update();
    if (rendererNode) view?.focus(rendererNode);
    else view?.fit();
  };

  const renderSearchResults = (value) => {
    const query = value.trim().toLocaleLowerCase("ko");
    const matches = query ? [...index.nodes.values()]
      .filter((node) => `${node.label} ${node.kind}`.toLocaleLowerCase("ko").includes(query))
      .sort((left, right) => left.label.localeCompare(right.label, "ko")) : [];
    graphSearchResults.innerHTML = matches.map((node) => `<button type="button" role="option" data-graph-search-result="${escapeHtml(node.id)}"><strong>${escapeHtml(node.label)}</strong><span>${escapeHtml(GRAPH_KIND_LABELS[node.kind] || node.kind)}</span></button>`).join("");
    graphSearchResults.hidden = matches.length === 0;
    graphSearch.setAttribute("aria-expanded", String(matches.length > 0));
  };

  const filterFallback = (value) => {
    const query = value.trim().toLocaleLowerCase("ko");
    const items = [...fallback.querySelectorAll("[data-fallback-item]")];
    const branches = [...fallback.querySelectorAll(".graph-fallback-tree > details")];
    let matches = 0;
    items.forEach((item) => {
      const matched = !query || item.dataset.fallbackLabel.includes(query);
      item.hidden = !matched;
      if (query && matched) matches += 1;
    });
    branches.forEach((branch) => {
      const rootMatched = !query || branch.querySelector("summary")?.dataset.fallbackLabel?.includes(query);
      const childMatched = items.some((item) => !item.hidden && branch.contains(item));
      branch.hidden = !rootMatched && !childMatched;
      if (query && rootMatched) matches += 1;
    });
    if (query) {
      for (const item of items.filter((candidate) => !candidate.hidden)) {
        let parent = item.parentElement?.closest("[data-fallback-item]");
        while (parent) {
          parent.hidden = false;
          parent = parent.parentElement?.closest("[data-fallback-item]");
        }
      }
      branches.filter((branch) => !branch.hidden).forEach((branch) => { branch.open = true; });
    }
    const empty = fallback.querySelector("[data-graph-fallback-empty]");
    if (empty) empty.hidden = !query || matches > 0;
  };

  const activateFallback = () => {
    const failedView = view;
    view = null;
    failedView?.destroy();
    stage.hidden = true;
    fallback.hidden = false;
    shell.dataset.graphMode = "fallback";
  };
  const onReducedMotionChange = (event) => {
    view?.setReducedMotion(Boolean(event.detail));
  };

  if (canRender(document)) {
    try {
      view = createView(container, visibleGraph(graphState, index), {
        onSelect(node) {
          selectNode(node.id, node);
        },
        onFailure: activateFallback,
        reducedMotion: root.dataset.reducedMotion === "true",
      });
    } catch {
      activateFallback();
    }
  } else {
    activateFallback();
  }

  if (view?.inspect) {
    Object.defineProperty(container, "__atlasGraphInspector", {
      configurable: true,
      value: () => view?.inspect() || null,
      writable: false,
    });
  }

  const onClick = (event) => {
    if (event.target.closest("[data-graph-fit]")) {
      view?.fit();
      return;
    }
    if (event.target.closest("[data-graph-reset]")) {
      graphState = initialGraphState(index);
      root.querySelectorAll("[data-graph-relation-filter]").forEach((input) => { input.checked = true; });
      graphSearch.value = "";
      renderSearchResults("");
      update();
      view?.reset();
      return;
    }
    const result = event.target.closest("[data-graph-search-result]");
    if (result) {
      const node = index.nodes.get(result.dataset.graphSearchResult);
      graphSearch.value = node?.label || "";
      renderSearchResults("");
      selectNode(result.dataset.graphSearchResult, null, true);
      return;
    }
    const fallbackNode = event.target.closest("[data-fallback-select]");
    if (fallbackNode) selectNode(fallbackNode.dataset.fallbackSelect, null, true);
  };
  const onChange = (event) => {
    if (!event.target.matches("[data-graph-relation-filter]")) return;
    const selectedKinds = [...root.querySelectorAll("[data-graph-relation-filter]:checked")].map((input) => input.value);
    graphState = setRelationFilters(graphState, selectedKinds);
    update();
  };
  const onInput = (event) => {
    if (event.target === graphSearch) renderSearchResults(graphSearch.value);
    if (event.target === fallbackSearch) filterFallback(fallbackSearch.value);
  };

  root.addEventListener("click", onClick);
  root.addEventListener("change", onChange);
  root.addEventListener("input", onInput);
  root.addEventListener("atlas:reduced-motion-change", onReducedMotionChange);
  update();
  return () => {
    root.removeEventListener("click", onClick);
    root.removeEventListener("change", onChange);
    root.removeEventListener("input", onInput);
    root.removeEventListener("atlas:reduced-motion-change", onReducedMotionChange);
    delete container.__atlasGraphInspector;
    view?.destroy();
  };
}

function projectTabs(project, currentTab) {
  return [...PROJECT_TABS].map((tab) => `<a id="project-tab-${tab}" class="tab-button" role="tab" aria-controls="project-tabpanel" aria-selected="${tab === currentTab}" tabindex="${tab === currentTab ? "0" : "-1"}" data-route-link href="${toRouteHref({ view: "project", projectId: project.id, tab })}">${TAB_LABELS[tab]}</a>`).join("");
}

function contentStateMessage(readiness, fallback) {
  if (readiness === "review-required") return "공개 전 검토가 필요합니다.";
  if (readiness === "insufficient-evidence") return "확인 가능한 공개 근거가 부족합니다.";
  return fallback;
}

function renderEmptyState(message) {
  return { html: `<p class="empty-state">${escapeHtml(message)}</p>`, headings: [] };
}

function renderArticleFigure(diagram, visuals) {
  if (!diagram?.id) return "";
  const svg = sanitizeSvg(visuals?.[diagram.id]);
  if (!svg) return "";
  const alt = escapeHtml(diagram.alt || diagram.caption || diagram.id);
  return `<figure class="article-figure" data-article-figure>
    <div class="article-figure-media" role="img" aria-label="${alt}">${svg}</div>
    <figcaption>${escapeHtml(diagram.caption || diagram.id)}</figcaption>
  </figure>`;
}

function renderSectionType(value) {
  const label = SECTION_TYPE_LABELS[value] || value;
  return `<p class="section-type">${escapeHtml(label)}</p>`;
}

export function renderArticle(project) {
  const article = project?.article;
  const readiness = article?.readiness;
  if (!article || readiness === "insufficient-evidence") {
    return renderEmptyState(contentStateMessage(readiness, "확인 가능한 공개 근거가 부족합니다."));
  }
  if (readiness === "review-required") {
    return renderEmptyState(contentStateMessage(readiness, "공개 전 검토가 필요합니다."));
  }

  const headings = [];
  const intro = [];
  if (article.summary) {
    intro.push(`<div class="markdown-body article-summary">${renderMarkdown(article.summary)}</div>`);
  }
  if (article.orientation) {
    intro.push(`<div class="markdown-body article-orientation" data-article-orientation>${renderMarkdown(article.orientation)}</div>`);
  }
  if (article.prior_context) {
    headings.push({ id: "prior-context", label: "이전 단계" });
    intro.push(`<section id="prior-context" data-article-section="prior-context">
      <h2>이전 단계</h2>
      <div class="markdown-body">${renderMarkdown(article.prior_context)}</div>
    </section>`);
  }
  const sections = Array.isArray(article.sections) ? article.sections.map((section) => {
    headings.push({ id: section.id, label: section.title });
    const figures = Array.isArray(section.diagrams)
      ? section.diagrams.map((diagram) => renderArticleFigure(diagram, project.visuals)).join("")
      : "";
    return `<section id="${escapeHtml(section.id)}" data-article-section="${escapeHtml(section.id)}">
      ${renderSectionType(section.section_type)}
      <h2>${escapeHtml(section.title)}</h2>
      <div class="markdown-body">${renderMarkdown(section.body)}</div>
      ${figures}
    </section>`;
  }).join("") : "";

  if (!sections && !intro.length) {
    return renderEmptyState("공개된 결정 본문이 아직 없습니다.");
  }

  return {
    html: `<article class="decision-article" data-project-reader>${intro.join("")}${sections}</article>`,
    headings
  };
}

export function renderProjectCaptures(project) {
  const captures = Array.isArray(project?.captures)
    ? project.captures
    : project?.cover?.src
      ? [{ id: "cover", src: project.cover.src, alt: project.cover.alt, caption: project.cover.caption, role: "overview" }]
      : [];
  if (!captures.length) return "";
  return `<section id="project-captures" class="project-captures" data-project-captures>
    <h2>구현 화면</h2>
    <div class="project-capture-grid">${captures.map((capture) => {
      const src = capture.src || `/api/atlas/projects/${encodeURIComponent(project.id)}/captures/${encodeURIComponent(capture.id)}`;
      return `<figure class="project-capture" data-capture-id="${escapeHtml(capture.id)}">
        <img src="${escapeHtml(src)}" alt="${escapeHtml(capture.alt)}" loading="lazy" decoding="async">
        <figcaption><strong>${escapeHtml(capture.caption)}</strong><span>${escapeHtml(capture.role || "구현 화면")}</span></figcaption>
      </figure>`;
    }).join("")}</div>
  </section>`;
}

export function renderSystemMap(project) {
  const svg = sanitizeSvg(project?.systemMap);
  const data = project?.systemMapData;
  if (!svg || !data) return renderEmptyState(contentStateMessage(project?.article?.readiness, "공개된 시스템 맵이 없습니다."));
  const nodes = Array.isArray(data.nodes) ? data.nodes : [];
  const decisions = Array.isArray(data.decision_links) ? data.decision_links : [];
  const mapType = Object.entries(SYSTEM_MAP_FAMILY_TYPES).find(([, types]) => types.has(data.map_type))?.[0] || "데이터 흐름";
  const headings = [{ id: "system-map-components", label: "맵 구성 요소" }];
  if (decisions.length) headings.push({ id: "system-map-decisions", label: "연결된 결정" });
  const decisionSection = decisions.length ? `<section id="system-map-decisions" class="system-map-section" data-article-section="system-map-decisions">
    <h2>이 구조와 연결된 결정</h2>
    <ul class="system-map-decisions">${decisions.map((decision) => `<li>
      <a href="?tab=decisions#${escapeHtml(decision.section_id)}" data-route-link>${escapeHtml(decision.label)}</a>
      <span>${(decision.node_ids || []).map((nodeId) => escapeHtml(nodes.find((node) => node.id === nodeId)?.label || nodeId)).join(" · ")}</span>
    </li>`).join("")}</ul>
  </section>` : "";
  return {
    html: `<article class="system-map-article" data-system-map>
      <header class="system-map-intro"><p class="system-map-type">${escapeHtml(mapType)}</p><h2>${escapeHtml(data.title)}</h2><div class="markdown-body">${renderMarkdown(data.summary)}</div></header>
      <div class="project-map" role="img" aria-label="${escapeHtml(data.title)}">${svg}</div>
      <section id="system-map-components" class="system-map-section" data-article-section="system-map-components">
        <h2>구성 요소</h2>
        <dl class="system-map-components">${nodes.map((node) => `<div><dt>${escapeHtml(node.label)}<span>${escapeHtml(node.kind)}</span></dt><dd>${escapeHtml(node.description)}</dd></div>`).join("")}</dl>
      </section>
      ${decisionSection}
    </article>`,
    headings
  };
}

function timelineItems(records = []) {
  return records
    .map((record, index) => ({ ...record, __index: index }))
    .sort((left, right) => {
      const leftDate = typeof left.date === "string" ? left.date : "";
      const rightDate = typeof right.date === "string" ? right.date : "";
      if (leftDate && rightDate) return leftDate.localeCompare(rightDate) || left.__index - right.__index;
      if (leftDate) return -1;
      if (rightDate) return 1;
      return left.__index - right.__index;
    });
}

function timelineDetail(label, value) {
  return value ? `<p><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</p>` : "";
}

export function renderTimeline(project) {
  const records = Array.isArray(project?.timeline) ? project.timeline : [];
  if (!records.length) return renderEmptyState(contentStateMessage(project?.article?.readiness, "공개된 빌드 타임라인이 없습니다."));
  return {
    html: `<div class="timeline-list">${timelineItems(records).map((event) => `<article class="timeline-entry" data-timeline-event="${escapeHtml(event.event_id || "")}">
      <p class="timeline-meta"><span>${escapeHtml(event.date || "날짜 미확인")}</span><span>${escapeHtml(event.stage || "")}</span></p>
      <h2>${escapeHtml(event.title || "Untitled event")}</h2>
      <div class="markdown-body">
        ${timelineDetail("Context", event.context)}
        ${timelineDetail("Decision", event.decision)}
        ${timelineDetail("Outcome", event.outcome)}
      </div>
    </article>`).join("")}</div>`,
    headings: []
  };
}

function evidenceItems(records = []) {
  return records.reduce((groups, record) => {
    const type = typeof record?.source_type === "string" ? record.source_type : "other";
    if (!groups.has(type)) groups.set(type, []);
    groups.get(type).push(record);
    return groups;
  }, new Map());
}

function renderEvidenceLink(url) {
  const href = toSafePublicHref(url);
  return href ? `<a href="${href}" target="_blank" rel="noreferrer noopener">Open source</a>` : "";
}

export function renderEvidence(project) {
  const records = Array.isArray(project?.evidence) ? project.evidence : [];
  if (!records.length) return renderEmptyState(contentStateMessage(project?.article?.readiness, "공개된 근거 목록이 없습니다."));
  const groups = evidenceItems(records);
  return {
    html: `<div class="evidence-groups">${[...groups.entries()].map(([type, items]) => `<section class="evidence-group" data-evidence-group="${escapeHtml(type)}">
      <h2>${escapeHtml(EVIDENCE_TYPE_LABELS[type] || type)}</h2>
      <ul>${items.map((record) => {
        const link = renderEvidenceLink(record?.url);
        return `<li data-evidence-id="${escapeHtml(record?.id || "")}">
          <strong>${escapeHtml(record?.label || record?.id || "Evidence")}</strong>
          <span>${escapeHtml(record?.observed_at || "")}</span>
          ${link ? `<span>${link}</span>` : ""}
        </li>`;
      }).join("")}</ul>
    </section>`).join("")}</div>`,
    headings: []
  };
}

export function renderProjectContent(project, tab) {
  if (tab === "decisions") {
    const article = renderArticle(project);
    if (typeof article === "string") return article;
    const captures = renderProjectCaptures(project);
    return {
      ...article,
      html: `${article.html}${captures}`,
      headings: captures ? [...article.headings, { id: "project-captures", label: "구현 화면" }] : article.headings,
    };
  }
  if (tab === "system-map") return renderSystemMap(project);
  if (tab === "build-timeline") return renderTimeline(project);
  if (tab === "evidence") return renderEvidence(project);
  return renderEmptyState("공개된 프로젝트 탭을 찾지 못했습니다.");
}

function projectContent(project, tab) {
  if (!PROJECT_TABS.has(tab)) {
    return renderEmptyState("공개된 프로젝트 탭을 찾지 못했습니다.");
  }
  return renderProjectContent(project, tab);
}

function tocItems(headings) {
  return headings.map((heading) => `<li><a href="#${encodeURIComponent(heading.id)}">${escapeHtml(heading.label)}</a></li>`).join("");
}

export function renderProjectToc(headings) {
  if (!Array.isArray(headings) || !headings.length) return "";
  const items = tocItems(headings);
  return `
    <div class="project-desktop-toc-slot" data-project-toc-desktop>
      <nav class="aside-section project-desktop-toc" data-project-toc aria-label="현재 프로젝트 목차">
        <h2>On this page</h2><ul>${items}</ul>
      </nav>
    </div>
    <div class="project-mobile-toc-slot" data-project-toc-mobile>
      <details class="project-mobile-toc">
        <summary>On this page</summary>
        <nav data-project-toc aria-label="현재 프로젝트 목차"><ul>${items}</ul></nav>
      </details>
    </div>`;
}

export function renderProjectCover(project) {
  const expected = `/api/atlas/projects/${encodeURIComponent(project?.id || "")}/cover`;
  if (project?.cover?.src !== expected || !project.cover.alt) return "";
  return `<figure class="project-cover">
    <img src="${escapeHtml(expected)}" alt="${escapeHtml(project.cover.alt)}" loading="eager" decoding="async">
    ${project.cover.caption ? `<figcaption>${escapeHtml(project.cover.caption)}</figcaption>` : ""}
  </figure>`;
}

function renderProject(state) {
  const project = state.project;
  if (!project) return `<div class="content-shell"><div class="error-state"><h1>프로젝트를 찾지 못했습니다.</h1><p>공개 목록에서 제거됐거나 주소가 변경됐습니다.</p></div></div>`;
  const route = state.route;
  const content = projectContent(project, route.tab);
  const projects = state.bootstrap.projects || [];
  const index = projects.findIndex((item) => item.id === project.id);
  const previous = index > 0 ? projects[index - 1] : null;
  const next = index >= 0 && index < projects.length - 1 ? projects[index + 1] : null;
  const tags = flattenTags(project).slice(0, 8);
  return `
    <div class="content-shell">
      <header class="project-header">
        <a class="project-back" data-route-link href="/projects"><i data-lucide="arrow-left" aria-hidden="true"></i>Projects</a>
        <div class="project-title-row">
          <div><p class="eyebrow">${escapeHtml(project.lifecycle)}</p><h1>${escapeHtml(project.name || project.id)}</h1><p class="project-summary">${escapeHtml(project.summary)}</p></div>
        </div>
        <div class="tag-row">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
      </header>
      <nav class="project-tabs project-tab-rail" data-project-tab-rail role="tablist" aria-label="프로젝트 문서">${projectTabs(project, route.tab)}</nav>
      <div class="project-layout">
        <section id="project-tabpanel" class="project-article" role="tabpanel" aria-labelledby="project-tab-${route.tab}">${content.html}
          <nav class="project-pager" aria-label="이전 및 다음 프로젝트">
            ${previous ? `<a data-project-prev data-route-link href="/projects/${encodeURIComponent(previous.id)}"><span>Previous</span><strong>${escapeHtml(previous.name || previous.id)}</strong></a>` : "<span></span>"}
            ${next ? `<a data-project-next data-route-link href="/projects/${encodeURIComponent(next.id)}"><span>Next</span><strong>${escapeHtml(next.name || next.id)}</strong></a>` : ""}
          </nav>
        </section>
        <aside class="project-aside"><div class="project-aside-inner">
          <section class="aside-section"><h2>Project ID</h2><code>${escapeHtml(project.id)}</code></section>
          ${renderProjectToc(content.headings)}
        </div></aside>
      </div>
    </div>`;
}

function bindProjectTabs(root, navigate) {
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  if (!tabs.length) return () => {};
  const onKeydown = (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const current = tabs.indexOf(event.currentTarget);
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    Promise.resolve(navigate(tabs[nextIndex].getAttribute("href"), { focus: false })).then(() => {
      root.querySelector('[role="tab"][aria-selected="true"]')?.focus();
    });
  };
  tabs.forEach((tab) => tab.addEventListener("keydown", onKeydown));
  return () => tabs.forEach((tab) => tab.removeEventListener("keydown", onKeydown));
}

function updateNavigation(route) {
  const current = route.view === "project" ? "projects" : route.view;
  document.querySelectorAll("[data-view]").forEach((link) => {
    if (link.dataset.view === current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function cleanupActiveRoute(root) {
  const cleanup = root.__atlasCleanup;
  root.__atlasCleanup = null;
  if (typeof cleanup === "function") cleanup();
}

export function renderRoute(state, root, { navigate = () => {} } = {}) {
  cleanupActiveRoute(root);
  if (!state.bootstrap) {
    root.innerHTML = '<div class="loading-state" role="status"><span class="loading-line"></span><span class="loading-line short"></span></div>';
    return;
  }
  const renderers = {
    home: renderHome,
    projects: renderProjects,
    topics: renderTopics,
    graph: renderGraph,
    graphify: state.route.scope === "code" ? renderCodeGraph : state.route.scope === "projects" || state.sourceGraphUnavailable ? renderProjectConnections : renderSourceGraph,
    changelog: renderChangelog,
    project: renderProject,
    search: renderProjects
  };
  root.innerHTML = (renderers[state.route.view] || renderHome)(state);
  updateNavigation(state.route);
  try { window.lucide?.createIcons(); } catch { /* Keep text controls usable without SVG icons. */ }
  const cleanup = [];
  if (state.route.view === "projects" || state.route.view === "search") cleanup.push(bindProjectFilters(root, state));
  if (state.route.view === "graph") cleanup.push(bindGraph(root, state, navigate));
  if (state.route.view === "graphify") cleanup.push(state.route.scope === "code" ? bindCodeGraph(root, state) : state.route.scope === "projects" || state.sourceGraphUnavailable ? bindProjectConnections(root, state) : bindSourceGraph(root, state, navigate));
  if (state.route.view === "project") cleanup.push(bindProjectTabs(root, navigate));
  const inlineSearch = root.querySelector("[data-search-trigger-inline]");
  if (inlineSearch) {
    const open = () => document.querySelector("[data-search-trigger]")?.click();
    inlineSearch.addEventListener("click", open);
    cleanup.push(() => inlineSearch.removeEventListener("click", open));
  }
  root.__atlasCleanup = () => cleanup.forEach((dispose) => dispose());
}

export function renderError(root, error) {
  cleanupActiveRoute(root);
  root.innerHTML = `<div class="content-shell"><div class="error-state" role="alert"><h1>Atlas를 불러오지 못했습니다.</h1><p>${escapeHtml(error?.code || error?.message || "unknown_error")}</p></div></div>`;
}
