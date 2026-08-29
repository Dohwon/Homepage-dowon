import { toRouteHref, PROJECT_TABS } from "./router.js";
import { renderMarkdown, sanitizeSvg } from "./markdown.js";
import { toSafePublicHref } from "./public-url.js";
import { createGraphView } from "./graph-view.js";

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
  project: "var(--project)",
  domain: "var(--domain)",
  problem: "var(--problem)",
  pattern: "var(--pattern)",
  technology: "var(--technology)",
  outcome: "var(--outcome)"
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
  return `
    <a class="project-card" data-project-card data-route-link href="${toRouteHref({ view: "project", projectId: project.id })}">
      <div class="project-card-top">
        <span class="project-index">${String(index + 1).padStart(2, "0")}</span>
        <span class="status-dot ${project.lifecycle === "active" ? "active" : ""}" aria-label="${project.lifecycle === "active" ? "진행 중" : "완료"}"></span>
      </div>
      <h2>${escapeHtml(project.name || project.id)}</h2>
      <p>${escapeHtml(project.summary)}</p>
      <div class="tag-row">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
    </a>`;
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
  const featured = [...projects].sort((left, right) => Number(Boolean(right.pinned)) - Number(Boolean(left.pinned))).slice(0, 6);
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
      <div class="project-grid">${featured.map(projectCard).join("")}</div>
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
      <div class="project-grid" data-project-grid>${projects.map(projectCard).join("")}</div>
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
    grid.innerHTML = filtered.map(projectCard).join("");
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

function renderGraph(state) {
  const kinds = [...new Set((state.graph?.nodes || []).map((node) => node.kind))];
  return `
    <div class="content-shell wide">
      ${pageHeading("Knowledge graph", "", "프로젝트와 공통 주제를 연결해 반복되는 문제와 작업 패턴을 보여줍니다.")}
      <div class="graph-shell">
        <div class="graph-stage">
          <svg id="knowledge-graph" role="group" aria-label="프로젝트 지식 그래프"></svg>
          <div class="graph-toolbar">
            <button class="icon-button" type="button" data-graph-fit aria-label="그래프 전체 보기" title="전체 보기"><i data-lucide="scan" aria-hidden="true"></i></button>
          </div>
        </div>
        <aside class="graph-sidebar">
          <h2>Node types</h2>
          <div class="graph-filter-list">
            ${kinds.map((kind) => `<label class="graph-filter" style="--kind-color: ${GRAPH_KIND_COLORS[kind] || "var(--muted)"}"><input type="checkbox" value="${escapeHtml(kind)}" checked data-graph-filter><span class="graph-swatch"></span><span>${escapeHtml(KIND_LABELS[kind] || kind)}</span></label>`).join("")}
          </div>
          <p class="graph-status" data-graph-status>전체 보기 · ${state.graph?.nodes?.length || 0} nodes</p>
        </aside>
      </div>
    </div>`;
}

function bindGraph(root, state, navigate) {
  const svg = root.querySelector("#knowledge-graph");
  if (!svg || !state.graph) return () => {};
  const status = root.querySelector("[data-graph-status]");
  const view = createGraphView(svg, state.graph, {
    onSelect(node) {
      if (node.kind === "project") navigate({ view: "project", projectId: node.id.replace(/^project:/, ""), tab: "decisions" });
      else {
        view.focus(node.id);
        status.textContent = node.label;
      }
    }
  });
  const onClick = (event) => {
    if (!event.target.closest("[data-graph-fit]")) return;
    view.fit();
    status.textContent = `전체 보기 · ${state.graph.nodes.length} nodes`;
  };
  const onChange = () => {
    const selected = [...root.querySelectorAll("[data-graph-filter]:checked")].map((input) => input.value);
    view.setKinds(selected);
    status.textContent = `${selected.length} types · ${state.graph.nodes.filter((node) => selected.includes(node.kind)).length} nodes`;
  };
  root.addEventListener("click", onClick);
  root.addEventListener("change", onChange);
  return () => {
    root.removeEventListener("click", onClick);
    root.removeEventListener("change", onChange);
    view.destroy();
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

export function renderSystemMap(project) {
  const svg = sanitizeSvg(project?.systemMap);
  if (!svg) return renderEmptyState(contentStateMessage(project?.article?.readiness, "공개된 시스템 맵이 없습니다."));
  return { html: `<div class="project-map" data-system-map>${svg}</div>`, headings: [] };
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
  if (tab === "decisions") return renderArticle(project);
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

export function renderRoute(state, root, { navigate = () => {} } = {}) {
  const previousCleanup = root.__atlasCleanup;
  if (typeof previousCleanup === "function") previousCleanup();
  if (!state.bootstrap) {
    root.innerHTML = '<div class="loading-state" role="status"><span class="loading-line"></span><span class="loading-line short"></span></div>';
    return;
  }
  const renderers = {
    home: renderHome,
    projects: renderProjects,
    topics: renderTopics,
    graph: renderGraph,
    changelog: renderChangelog,
    project: renderProject,
    search: renderProjects
  };
  root.innerHTML = (renderers[state.route.view] || renderHome)(state);
  updateNavigation(state.route);
  window.lucide?.createIcons();
  const cleanup = [];
  if (state.route.view === "projects" || state.route.view === "search") cleanup.push(bindProjectFilters(root, state));
  if (state.route.view === "graph") cleanup.push(bindGraph(root, state, navigate));
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
  root.innerHTML = `<div class="content-shell"><div class="error-state" role="alert"><h1>Atlas를 불러오지 못했습니다.</h1><p>${escapeHtml(error?.code || error?.message || "unknown_error")}</p></div></div>`;
}
