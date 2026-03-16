const state = {
  bootstrap: null,
  analytics: null,
  filters: {
    query: "",
    status: "all",
    category: "all"
  },
  currentProjectId: null,
  commentsByProject: new Map(),
  trackedProjects: new Set()
};

const elements = {
  brandLabel: document.getElementById("brand-label"),
  ownerPrimary: document.getElementById("owner-primary"),
  ownerHeadline: document.getElementById("owner-headline"),
  externalLink: document.getElementById("external-link"),
  authArea: document.getElementById("auth-area"),
  newProjectButton: document.getElementById("new-project-button"),
  heroBadge: document.getElementById("hero-badge"),
  heroTitle: document.getElementById("hero-title"),
  heroDescription: document.getElementById("hero-description"),
  heroNote: document.getElementById("hero-note"),
  heroMiniStats: document.getElementById("hero-mini-stats"),
  ownerSummary: document.getElementById("owner-summary"),
  focusTags: document.getElementById("focus-tags"),
  valueProps: document.getElementById("value-props"),
  careerTimeline: document.getElementById("career-timeline"),
  skillGroups: document.getElementById("skill-groups"),
  caseGrid: document.getElementById("case-grid"),
  searchInput: document.getElementById("search-input"),
  searchReset: document.getElementById("search-reset"),
  statusFilters: document.getElementById("status-filters"),
  categoryFilters: document.getElementById("category-filters"),
  collectionMeta: document.getElementById("collection-meta"),
  projectGrid: document.getElementById("project-grid"),
  adminPanel: document.getElementById("admin-panel"),
  detailModal: document.getElementById("detail-modal"),
  detailModalBody: document.getElementById("detail-modal-body"),
  editorModal: document.getElementById("editor-modal"),
  editorForm: document.getElementById("project-editor-form")
};

document.addEventListener("DOMContentLoaded", () => {
  init().catch((error) => {
    console.error(error);
    elements.projectGrid.innerHTML = `<article class="empty-state">앱 로딩 실패: ${escapeHtml(error.message)}</article>`;
  });
});

async function init() {
  bindEvents();
  await refreshApp();
  void recordVisit("home");
}

function bindEvents() {
  elements.searchInput.addEventListener("input", () => {
    state.filters.query = elements.searchInput.value.trim().toLowerCase();
    renderProjects();
  });

  elements.searchReset.addEventListener("click", () => {
    elements.searchInput.value = "";
    state.filters.query = "";
    renderProjects();
  });

  elements.statusFilters.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-status-filter]");
    if (!chip) return;
    state.filters.status = chip.dataset.statusFilter;
    renderFilters();
    renderProjects();
  });

  elements.categoryFilters.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-category-filter]");
    if (!chip) return;
    state.filters.category = chip.dataset.categoryFilter;
    renderFilters();
    renderProjects();
  });

  elements.projectGrid.addEventListener("click", (event) => {
    const actionButton = event.target.closest("[data-card-action]");
    if (actionButton) {
      const projectId = actionButton.closest(".project-card")?.dataset.projectId;
      if (!projectId) return;
      if (actionButton.dataset.cardAction === "edit") {
        openEditor(findProject(projectId));
      }
      if (actionButton.dataset.cardAction === "delete") {
        void deleteProject(projectId);
      }
      return;
    }

    const card = event.target.closest(".project-card");
    if (!card) return;
    openDetail(card.dataset.projectId);
  });

  elements.projectGrid.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest(".project-card");
    if (!card) return;
    event.preventDefault();
    openDetail(card.dataset.projectId);
  });

  elements.projectGrid.addEventListener("mouseover", handlePreviewHover);
  elements.projectGrid.addEventListener("mouseout", stopPreviewHover);
  elements.projectGrid.addEventListener("focusin", handlePreviewHover);
  elements.projectGrid.addEventListener("focusout", stopPreviewHover);

  elements.detailModal.addEventListener("click", (event) => {
    if (event.target.matches("[data-close-modal]")) {
      closeDetail();
      return;
    }

    const actionButton = event.target.closest("[data-detail-action]");
    if (!actionButton) return;
    const projectId = state.currentProjectId;
    if (!projectId) return;
    if (actionButton.dataset.detailAction === "edit") {
      openEditor(findProject(projectId));
    }
    if (actionButton.dataset.detailAction === "delete") {
      void deleteProject(projectId);
    }
  });

  elements.detailModalBody.addEventListener("submit", (event) => {
    if (event.target.matches("#comment-form")) {
      event.preventDefault();
      void submitComment();
    }
  });

  elements.editorModal.addEventListener("click", (event) => {
    if (event.target.matches("[data-close-editor]")) {
      closeEditor();
    }
  });

  elements.editorForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveProject();
  });

  elements.newProjectButton.addEventListener("click", () => openEditor(null));

  elements.authArea.addEventListener("click", (event) => {
    const logoutButton = event.target.closest("[data-auth-action='logout']");
    if (logoutButton) {
      void logout();
      return;
    }

    const devLoginButton = event.target.closest("[data-auth-action='dev-login']");
    if (devLoginButton) {
      void loginWithDev();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDetail();
      closeEditor();
    }
  });
}

async function refreshApp() {
  state.bootstrap = await api("/api/bootstrap");
  if (state.bootstrap.viewer?.role === "admin") {
    state.analytics = await api("/api/analytics/summary").catch(() => null);
  } else {
    state.analytics = null;
  }
  renderAll();
  initializeGoogleButton();
}

function renderAll() {
  renderTopbar();
  renderHero();
  renderFilters();
  renderProfile();
  renderTimeline();
  renderSkills();
  renderCases();
  renderAdminPanel();
  renderProjects();
  renderAuthArea();
  renderOpenDetail();
}

function renderTopbar() {
  const { site, owner, links } = state.bootstrap;
  elements.brandLabel.textContent = site.brandLabel || "";
  elements.ownerPrimary.textContent = site.ownerPrimary || owner.name || "";
  elements.ownerHeadline.textContent = owner.headline || "";

  if (site.externalLink || links.notion) {
    elements.externalLink.classList.remove("hidden");
    elements.externalLink.href = site.externalLink || links.notion;
    elements.externalLink.textContent = "Notion";
  } else {
    elements.externalLink.classList.add("hidden");
  }

  elements.newProjectButton.classList.toggle("hidden", state.bootstrap.viewer?.role !== "admin");
}

function renderHero() {
  const { site, owner, projects } = state.bootstrap;
  const stats = computeStats(projects);

  elements.heroBadge.textContent = site.heroBadge || "";
  elements.heroTitle.textContent = site.heroTitle || "";
  elements.heroDescription.textContent = site.heroDescription || "";
  elements.heroNote.textContent = site.heroNote || "";
  elements.ownerSummary.textContent = owner.careerSummary || "";
  elements.searchInput.placeholder = site.searchPlaceholder || "검색";

  elements.focusTags.innerHTML = arrayOrEmpty(owner.focusAreas)
    .map((item) => `<span class="tag-pill">${escapeHtml(item)}</span>`)
    .join("");

  const statItems = [
    { label: "프로젝트", value: String(stats.total) },
    { label: "진행중", value: String(stats.inProgress) },
    { label: "운영/완료", value: String(stats.active) },
    { label: "카테고리", value: String(stats.categories) }
  ];

  elements.heroMiniStats.innerHTML = statItems
    .map(
      (item) => `
        <article class="mini-stat-card">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
        </article>
      `
    )
    .join("");
}

function renderFilters() {
  const categories = ["all", ...new Set(state.bootstrap.projects.map((project) => project.category))];
  const statusItems = [
    { key: "all", label: "전체" },
    { key: "active", label: "완료/운영" },
    { key: "in-progress", label: "진행중" }
  ];

  elements.statusFilters.innerHTML = statusItems
    .map(
      (item) => `
        <button
          type="button"
          class="chip-button ${state.filters.status === item.key ? "active" : ""}"
          data-status-filter="${escapeHtml(item.key)}"
        >
          ${escapeHtml(item.label)}
        </button>
      `
    )
    .join("");

  elements.categoryFilters.innerHTML = categories
    .map(
      (category) => `
        <button
          type="button"
          class="chip-button subtle ${state.filters.category === category ? "active" : ""}"
          data-category-filter="${escapeHtml(category)}"
        >
          ${escapeHtml(category === "all" ? "전체 카테고리" : category)}
        </button>
      `
    )
    .join("");
}

function renderProfile() {
  const profile = state.bootstrap.profile || {};
  elements.valueProps.innerHTML = arrayOrEmpty(profile.valueProposition)
    .map((item) => `<article class="value-card">${escapeHtml(item)}</article>`)
    .join("");
}

function renderTimeline() {
  const profile = state.bootstrap.profile || {};
  const metrics = arrayOrEmpty(profile.coreMetrics)
    .map(
      (metric) => `
        <article class="metric-pill">
          <span>${escapeHtml(metric.label || "")}</span>
          <strong>${escapeHtml(metric.value || "")}</strong>
        </article>
      `
    )
    .join("");

  const timeline = arrayOrEmpty(profile.careerTimeline)
    .map(
      (item) => `
        <article class="timeline-item">
          <p class="timeline-period">${escapeHtml(item.period || "")}</p>
          <div class="timeline-title">${escapeHtml(item.company || "")} · ${escapeHtml(item.role || "")}</div>
          <p class="timeline-copy">${escapeHtml(item.summary || "")}</p>
        </article>
      `
    )
    .join("");

  elements.careerTimeline.innerHTML = `
    <div class="metric-strip">${metrics}</div>
    <div class="timeline-track">${timeline}</div>
  `;
}

function renderSkills() {
  const profile = state.bootstrap.profile || {};
  const skills = Object.entries(profile.skillMatrix || {});
  const softSkills = arrayOrEmpty(profile.softSkills)
    .map((item) => `<span class="soft-pill">${escapeHtml(item)}</span>`)
    .join("");
  const certs = arrayOrEmpty(profile.certifications)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  const highlights = arrayOrEmpty(profile.highlights)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  elements.skillGroups.innerHTML = `
    <div class="skill-cluster-grid">
      ${skills
        .map(
          ([key, values]) => `
            <article class="skill-card">
              <h3>${escapeHtml(key)}</h3>
              <div class="skill-chip-wrap">
                ${arrayOrEmpty(values).map((item) => `<span class="skill-chip">${escapeHtml(item)}</span>`).join("")}
              </div>
            </article>
          `
        )
        .join("")}
    </div>
    <div class="support-grid">
      <article class="support-card">
        <p class="panel-kicker">Soft Skills</p>
        <div class="soft-pill-wrap">${softSkills}</div>
      </article>
      <article class="support-card">
        <p class="panel-kicker">Certifications</p>
        <ul class="support-list">${certs}</ul>
      </article>
      <article class="support-card">
        <p class="panel-kicker">Highlights</p>
        <ul class="support-list">${highlights}</ul>
      </article>
    </div>
  `;
}

function renderCases() {
  const cases = arrayOrEmpty(state.bootstrap.cases);
  elements.caseGrid.innerHTML = cases.length
    ? cases
        .map(
          (item) => `
            <article class="case-card">
              <div class="case-head">
                <h3>${escapeHtml(item.title || "")}</h3>
                <span class="case-badge">Case</span>
              </div>
              <p><strong>문제</strong> ${escapeHtml(item.problem || "")}</p>
              <p><strong>시도</strong></p>
              <ul class="support-list tight">
                ${arrayOrEmpty(item.attempts).map((attempt) => `<li>${escapeHtml(attempt)}</li>`).join("")}
              </ul>
              <p><strong>결과</strong> ${escapeHtml(item.result || "")}</p>
              <div class="flow-track">
                ${arrayOrEmpty(item.flow).map((step) => `<span class="flow-node">${escapeHtml(step)}</span>`).join("")}
              </div>
            </article>
          `
        )
        .join("")
    : `<article class="empty-state">문제 해결 사례 데이터가 없습니다.</article>`;
}

function renderAdminPanel() {
  const viewer = state.bootstrap.viewer;
  if (viewer?.role !== "admin") {
    elements.adminPanel.classList.add("hidden");
    elements.adminPanel.innerHTML = "";
    return;
  }

  elements.adminPanel.classList.remove("hidden");
  const analytics = state.analytics || {
    totalVisits: 0,
    uniqueVisitors: 0,
    authenticatedVisits: 0,
    anonymousVisits: 0,
    last7Days: [],
    topProjects: [],
    surfaces: []
  };

  const summaryCards = [
    { label: "총 방문", value: analytics.totalVisits },
    { label: "고유 방문자", value: analytics.uniqueVisitors },
    { label: "로그인 방문", value: analytics.authenticatedVisits },
    { label: "비로그인 방문", value: analytics.anonymousVisits }
  ];

  const maxVisits = Math.max(1, ...analytics.last7Days.map((item) => item.visits || 0));

  elements.adminPanel.innerHTML = `
    <div class="panel-header">
      <div>
        <p class="panel-kicker">Admin</p>
        <h2>운영 대시보드</h2>
      </div>
      <div class="permission-pills">
        <span class="soft-pill">비로그인: 읽기</span>
        <span class="soft-pill">로그인: 댓글</span>
        <span class="soft-pill admin">관리자: 카드 관리/통계</span>
      </div>
    </div>
    <div class="metric-strip">
      ${summaryCards
        .map(
          (item) => `
            <article class="metric-pill">
              <span>${escapeHtml(String(item.label))}</span>
              <strong>${escapeHtml(String(item.value))}</strong>
            </article>
          `
        )
        .join("")}
    </div>
    <div class="analytics-layout">
      <article class="analytics-card">
        <p class="panel-kicker">Last 7 Days</p>
        <div class="analytics-bars">
          ${analytics.last7Days
            .map(
              (item) => `
                <div class="bar-col">
                  <div class="bar-track">
                    <span class="bar-fill" style="height:${Math.max(12, Math.round((item.visits / maxVisits) * 100))}%"></span>
                  </div>
                  <strong>${escapeHtml(String(item.visits))}</strong>
                  <span>${escapeHtml(item.label)}</span>
                </div>
              `
            )
            .join("")}
        </div>
      </article>
      <article class="analytics-card">
        <p class="panel-kicker">Most Viewed Projects</p>
        <ul class="ranking-list">
          ${analytics.topProjects.length
            ? analytics.topProjects
                .map(
                  (item) => `
                    <li>
                      <span>${escapeHtml(item.name)}</span>
                      <strong>${escapeHtml(String(item.visits))}</strong>
                    </li>
                  `
                )
                .join("")
            : "<li><span>아직 데이터가 없습니다.</span><strong>0</strong></li>"}
        </ul>
      </article>
    </div>
  `;
}

function renderProjects() {
  const projects = getVisibleProjects();
  const total = state.bootstrap.projects.length;
  elements.collectionMeta.innerHTML = `
    <span class="collection-pill">노출 ${escapeHtml(String(projects.length))} / 전체 ${escapeHtml(String(total))}</span>
    <span class="collection-pill subtle">실제 영상 파일 연결 시 자동 재생</span>
  `;

  if (!projects.length) {
    elements.projectGrid.innerHTML = `<article class="empty-state">현재 필터에 맞는 프로젝트가 없습니다.</article>`;
    return;
  }

  elements.projectGrid.innerHTML = projects.map(renderProjectCard).join("");
}

function renderProjectCard(project) {
  const counts = state.bootstrap.commentCounts || {};
  const commentCount = counts[project.id] || 0;
  const viewer = state.bootstrap.viewer;

  return `
    <article class="project-card" tabindex="0" data-project-id="${escapeHtml(project.id)}">
      <div class="card-topline">
        <span class="badge category">${escapeHtml(project.category)}</span>
        <span class="badge ${project.status === "in-progress" ? "warning" : "success"}">
          ${project.status === "in-progress" ? "진행중" : "완료/운영"}
        </span>
      </div>

      ${renderPreviewMarkup(project, "card")}

      <div class="card-body">
        <div class="card-heading">
          ${renderDisplayTitle(project, "card")}
          <span class="comment-pill">댓글 ${escapeHtml(String(commentCount))}</span>
        </div>
        <p class="card-summary">${escapeHtml(project.summary)}</p>
        <div class="tag-row">
          ${arrayOrEmpty(project.tags).slice(0, 4).map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
        </div>
        <div class="card-footer">
          <span>${escapeHtml(arrayOrEmpty(project.stack).slice(0, 3).join(" · "))}</span>
          <span>${escapeHtml(project.path || "")}</span>
        </div>
      </div>

      ${
        viewer?.role === "admin"
          ? `
            <div class="card-actions">
              <button type="button" class="icon-button" data-card-action="edit">편집</button>
              <button type="button" class="icon-button danger" data-card-action="delete">삭제</button>
            </div>
          `
          : ""
      }
    </article>
  `;
}

function renderPreviewMarkup(project, variant) {
  const preview = project.preview || {};
  const isVideo = preview.mode === "video" && preview.video;
  const steps = arrayOrEmpty(preview.steps).slice(0, 3);

  return `
    <div class="preview-surface ${variant === "detail" ? "detail" : ""}">
      ${
        preview.poster
          ? `<img class="preview-poster ${isVideo ? "" : "ghosted"}" src="${escapeHtml(preview.poster)}" alt="${escapeHtml(project.name)} preview poster" />`
          : ""
      }
      ${
        isVideo
          ? `<video class="preview-video" muted loop playsinline preload="metadata" src="${escapeHtml(preview.video)}"></video>`
          : ""
      }
      <div class="preview-overlay">
        <div class="preview-pill-row">
          <span class="preview-pill">${escapeHtml(preview.eyebrow || project.category)}</span>
          <span class="preview-pill subtle">${escapeHtml(project.status === "in-progress" ? "Build" : "Live")}</span>
        </div>
        <div class="mock-screen ${isVideo ? "video-mode" : ""}">
          <div class="mock-header">
            <span class="mock-dot"></span>
            <span class="mock-dot"></span>
            <span class="mock-dot"></span>
          </div>
          <div class="mock-body">
            ${steps
              .map(
                (step, index) => `
                  <div class="mock-step step-${index + 1}">
                    <small>${escapeHtml(step.label || "")}</small>
                    <strong>${escapeHtml(step.value || "")}</strong>
                  </div>
                `
              )
              .join("")}
            <div class="mock-bars">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderDisplayTitle(project, variant) {
  const parts = splitDisplayTitle(project.name);
  const titleTag = variant === "detail" ? "h2" : "h3";
  const projectIndex = state.bootstrap.projects.findIndex((item) => item.id === project.id) + 1;
  const supportCopy =
    arrayOrEmpty(project.highlights)[0] ||
    arrayOrEmpty(project.tags)[0] ||
    project.category ||
    project.summary;
  const statusCopy = project.status === "in-progress" ? "Currently Building" : "Live Archive";

  return `
    <div class="display-title ${variant}">
      <div class="display-title-meta">
        <span class="display-title-index">Project ${escapeHtml(String(projectIndex).padStart(2, "0"))}</span>
        <span class="display-title-status">${escapeHtml(statusCopy)}</span>
      </div>
      <${titleTag} class="display-title-text">
        <span class="title-lead">${escapeHtml(parts.lead)}</span>
        ${parts.rest ? `<span class="title-rest">${escapeHtml(parts.rest)}</span>` : ""}
      </${titleTag}>
      <p class="display-title-sub">${escapeHtml(supportCopy)}</p>
    </div>
  `;
}

function splitDisplayTitle(name) {
  const clean = String(name || "").trim().replace(/\s+/g, " ");
  if (!clean) {
    return { lead: "Project", rest: "" };
  }

  if (clean.startsWith("(")) {
    const closing = clean.indexOf(")");
    if (closing > 0 && closing < 18) {
      const lead = clean.slice(0, closing + 1);
      const rest = clean.slice(closing + 1).trim();
      return { lead, rest };
    }
  }

  const words = clean.split(" ");
  if (words.length === 1) {
    return { lead: words[0], rest: "" };
  }

  const asciiStart = /^[A-Za-z0-9]+$/.test(words[0]);
  const leadCount = asciiStart && words.length > 2 ? 2 : 1;

  return {
    lead: words.slice(0, leadCount).join(" "),
    rest: words.slice(leadCount).join(" ")
  };
}

function openDetail(projectId) {
  const project = findProject(projectId);
  if (!project) return;
  state.currentProjectId = projectId;
  elements.detailModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  renderOpenDetail();
  void loadComments(projectId);
  if (!state.trackedProjects.has(projectId)) {
    state.trackedProjects.add(projectId);
    void recordVisit("project-detail", projectId);
  }
}

function closeDetail() {
  state.currentProjectId = null;
  elements.detailModal.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function renderOpenDetail() {
  if (!state.currentProjectId) {
    elements.detailModalBody.innerHTML = "";
    return;
  }

  const project = findProject(state.currentProjectId);
  if (!project) {
    elements.detailModalBody.innerHTML = "";
    return;
  }

  const detail = project.detail || {};
  const comments = state.commentsByProject.get(project.id) || [];
  const viewer = state.bootstrap.viewer;

  elements.detailModalBody.innerHTML = `
    <div class="detail-layout">
      <div class="detail-preview-column">
        ${renderPreviewMarkup(project, "detail")}
        <div class="detail-chip-wrap">
          ${arrayOrEmpty(project.tags).map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
        </div>
        <div class="detail-meta-card">
          <p class="panel-kicker">Files</p>
          <div class="file-chip-wrap">
            ${arrayOrEmpty(detail.keyFiles).map((file) => `<code>${escapeHtml(file)}</code>`).join("")}
          </div>
          <p class="detail-caption">${escapeHtml(detail.diagramCaption || "")}</p>
          ${
            viewer?.role === "admin"
              ? `
                <div class="detail-admin-actions">
                  <button type="button" class="ghost-button" data-detail-action="edit">편집</button>
                  <button type="button" class="ghost-button danger" data-detail-action="delete">삭제</button>
                </div>
              `
              : ""
          }
        </div>
      </div>

      <div class="detail-content-column">
        <div class="detail-header">
          <div>
            <div class="detail-badges">
              <span class="badge category">${escapeHtml(project.category)}</span>
              <span class="badge ${project.status === "in-progress" ? "warning" : "success"}">
                ${project.status === "in-progress" ? "진행중" : "완료/운영"}
              </span>
            </div>
            <div id="detail-title-anchor">
              ${renderDisplayTitle(project, "detail")}
            </div>
            <p class="panel-summary">${escapeHtml(project.summary)}</p>
          </div>
        </div>

        <section class="detail-section">
          <p class="panel-kicker">Summary</p>
          <ul class="support-list">
            ${arrayOrEmpty(detail.readmeSummary).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}
          </ul>
        </section>

        <section class="detail-section">
          <p class="panel-kicker">Workflow</p>
          <div class="workflow-track">
            ${arrayOrEmpty(detail.workflow)
              .map(
                (item) => `
                  <article class="workflow-card">
                    <strong>${escapeHtml(item.step || "")}</strong>
                    <p>${escapeHtml(item.desc || "")}</p>
                  </article>
                `
              )
              .join("")}
          </div>
        </section>

        <section class="detail-section">
          <div class="comment-section-head">
            <div>
              <p class="panel-kicker">Comments</p>
              <h3>방문자 코멘트</h3>
            </div>
          </div>
          ${
            viewer
              ? `
                <form id="comment-form" class="comment-form">
                  <textarea name="message" rows="3" maxlength="1000" placeholder="프로젝트를 보고 느낀 점이나 질문을 남겨보세요"></textarea>
                  <button type="submit" class="primary-button">댓글 등록</button>
                </form>
              `
              : `
                <article class="comment-locked">
                  <strong>댓글은 구글 로그인 후 작성할 수 있습니다.</strong>
                  <p>비로그인 방문자는 읽기만 가능하고, 로그인 사용자는 댓글 권한이 열립니다.</p>
                </article>
              `
          }
          <div class="comment-list">
            ${
              comments.length
                ? comments
                    .map(
                      (comment) => `
                        <article class="comment-card">
                          <div class="comment-author">
                            <div class="avatar-circle">${escapeHtml((comment.authorName || "?").slice(0, 1).toUpperCase())}</div>
                            <div>
                              <strong>${escapeHtml(comment.authorName || "Visitor")}</strong>
                              <span>${formatDate(comment.createdAt)}</span>
                            </div>
                          </div>
                          <p>${escapeHtml(comment.message || "")}</p>
                        </article>
                      `
                    )
                    .join("")
                : `<article class="empty-state small">아직 댓글이 없습니다.</article>`
            }
          </div>
        </section>
      </div>
    </div>
  `;

  const detailVideo = elements.detailModalBody.querySelector(".preview-video");
  if (detailVideo) {
    void detailVideo.play().catch(() => {});
  }
}

async function loadComments(projectId) {
  try {
    const data = await api(`/api/comments?projectId=${encodeURIComponent(projectId)}`);
    state.commentsByProject.set(projectId, data.comments || []);
    if (state.currentProjectId === projectId) {
      renderOpenDetail();
    }
  } catch (error) {
    console.error(error);
  }
}

function renderAuthArea() {
  const viewer = state.bootstrap.viewer;
  if (viewer) {
    elements.authArea.innerHTML = `
      <div class="viewer-pill">
        <div class="avatar-circle">${escapeHtml((viewer.name || viewer.email || "?").slice(0, 1).toUpperCase())}</div>
        <div class="viewer-copy">
          <strong>${escapeHtml(viewer.name || viewer.email)}</strong>
          <span>${escapeHtml(viewer.role === "admin" ? "관리자" : "로그인 사용자")}</span>
        </div>
        <button type="button" class="ghost-button" data-auth-action="logout">로그아웃</button>
      </div>
    `;
    return;
  }

  const devLoginButton = state.bootstrap.config.devLoginEnabled
    ? `<button type="button" class="ghost-button" data-auth-action="dev-login">개발 로그인</button>`
    : "";

  elements.authArea.innerHTML = `
    <div class="login-box">
      <div id="google-button-slot" class="google-button-slot"></div>
      ${devLoginButton}
    </div>
  `;
}

function initializeGoogleButton() {
  const slot = document.getElementById("google-button-slot");
  if (!slot) return;

  if (!state.bootstrap.config.googleClientId) {
    slot.innerHTML = `<span class="login-hint">GOOGLE_CLIENT_ID 설정 후 로그인 버튼이 활성화됩니다.</span>`;
    return;
  }

  if (!window.google?.accounts?.id) {
    window.setTimeout(initializeGoogleButton, 350);
    return;
  }

  slot.innerHTML = "";
  window.google.accounts.id.initialize({
    client_id: state.bootstrap.config.googleClientId,
    callback: handleGoogleCredential
  });
  window.google.accounts.id.renderButton(slot, {
    theme: "outline",
    size: "large",
    shape: "pill",
    text: "signin_with",
    locale: "ko"
  });
}

async function handleGoogleCredential(response) {
  try {
    await api("/api/auth/google", {
      method: "POST",
      body: { credential: response.credential }
    });
    await refreshApp();
  } catch (error) {
    window.alert(`구글 로그인 실패: ${error.message}`);
  }
}

async function loginWithDev() {
  try {
    await api("/api/auth/dev", {
      method: "POST",
      body: {}
    });
    await refreshApp();
  } catch (error) {
    window.alert(`개발 로그인 실패: ${error.message}`);
  }
}

async function logout() {
  await api("/api/logout", { method: "POST", body: {} });
  state.commentsByProject.clear();
  await refreshApp();
  closeDetail();
}

function openEditor(project) {
  if (state.bootstrap.viewer?.role !== "admin") return;
  elements.editorModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  fillEditor(project);
}

function closeEditor() {
  elements.editorModal.classList.add("hidden");
  if (!state.currentProjectId) {
    document.body.classList.remove("modal-open");
  }
}

function fillEditor(project) {
  const form = elements.editorForm;
  form.reset();

  const source = project || {
    id: "",
    name: "",
    category: "",
    status: "active",
    summary: "",
    tags: [],
    stack: [],
    highlights: [],
    path: "",
    readme: "",
    detail: {
      readmeSummary: [],
      workflow: [],
      keyFiles: [],
      diagramCaption: ""
    },
    preview: {
      video: "",
      poster: "",
      eyebrow: "",
      caption: "",
      steps: []
    }
  };

  setField(form, "id", source.id);
  setField(form, "name", source.name);
  setField(form, "category", source.category);
  setField(form, "status", source.status);
  setField(form, "summary", source.summary);
  setField(form, "tags", arrayOrEmpty(source.tags).join(", "));
  setField(form, "stack", arrayOrEmpty(source.stack).join(", "));
  setField(form, "highlights", arrayOrEmpty(source.highlights).join("\n"));
  setField(form, "path", source.path || "");
  setField(form, "readme", source.readme || "");
  setField(form, "previewVideo", source.preview?.video || "");
  setField(form, "previewPoster", source.preview?.poster || "");
  setField(form, "previewEyebrow", source.preview?.eyebrow || "");
  setField(form, "previewCaption", source.preview?.caption || "");
  setField(
    form,
    "previewSteps",
    arrayOrEmpty(source.preview?.steps)
      .map((item) => `${item.label || ""}|${item.value || ""}`)
      .join("\n")
  );
  setField(form, "readmeSummary", arrayOrEmpty(source.detail?.readmeSummary).join("\n"));
  setField(
    form,
    "workflow",
    arrayOrEmpty(source.detail?.workflow)
      .map((item) => `${item.step || ""}|${item.desc || ""}`)
      .join("\n")
  );
  setField(form, "keyFiles", arrayOrEmpty(source.detail?.keyFiles).join("\n"));
  setField(form, "diagramCaption", source.detail?.diagramCaption || "");
}

function setField(form, name, value) {
  const field = form.elements.namedItem(name);
  if (field) {
    field.value = value;
  }
}

async function saveProject() {
  const formData = new FormData(elements.editorForm);
  const project = {
    id: formData.get("id"),
    name: formData.get("name"),
    category: formData.get("category"),
    status: formData.get("status"),
    summary: formData.get("summary"),
    tags: splitComma(formData.get("tags")),
    stack: splitComma(formData.get("stack")),
    highlights: splitLines(formData.get("highlights")),
    path: formData.get("path"),
    readme: formData.get("readme"),
    preview: {
      video: formData.get("previewVideo"),
      poster: formData.get("previewPoster"),
      eyebrow: formData.get("previewEyebrow"),
      caption: formData.get("previewCaption"),
      steps: splitPairs(formData.get("previewSteps"))
    },
    detail: {
      readmeSummary: splitLines(formData.get("readmeSummary")),
      workflow: splitPairs(formData.get("workflow")),
      keyFiles: splitLines(formData.get("keyFiles")),
      diagramCaption: formData.get("diagramCaption")
    }
  };

  try {
    await api("/api/projects", {
      method: "POST",
      body: { project }
    });
    await refreshApp();
    closeEditor();
  } catch (error) {
    window.alert(`저장 실패: ${error.message}`);
  }
}

async function deleteProject(projectId) {
  const project = findProject(projectId);
  if (!project) return;
  const confirmed = window.confirm(`${project.name} 카드를 삭제할까요? 댓글도 함께 삭제됩니다.`);
  if (!confirmed) return;

  try {
    await api(`/api/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
    state.commentsByProject.delete(projectId);
    if (state.currentProjectId === projectId) {
      closeDetail();
    }
    await refreshApp();
  } catch (error) {
    window.alert(`삭제 실패: ${error.message}`);
  }
}

async function submitComment() {
  const form = elements.detailModalBody.querySelector("#comment-form");
  const textarea = form?.elements.namedItem("message");
  if (!textarea) return;
  const message = textarea.value.trim();
  if (!message) return;

  try {
    await api("/api/comments", {
      method: "POST",
      body: {
        projectId: state.currentProjectId,
        message
      }
    });
    textarea.value = "";
    await loadComments(state.currentProjectId);
    await refreshCommentCounts();
  } catch (error) {
    window.alert(`댓글 등록 실패: ${error.message}`);
  }
}

async function refreshCommentCounts() {
  const data = await api("/api/bootstrap");
  state.bootstrap.commentCounts = data.commentCounts;
  renderProjects();
}

async function recordVisit(surface, projectId = "") {
  try {
    await api("/api/analytics/visit", {
      method: "POST",
      body: {
        surface,
        projectId
      }
    });
  } catch (_error) {
    // Analytics failure should not block the UI.
  }
}

function handlePreviewHover(event) {
  const card = event.target.closest(".project-card");
  if (!card) return;
  if (event.type === "mouseover" && card.contains(event.relatedTarget)) return;
  card.classList.add("is-playing");
  const video = card.querySelector(".preview-video");
  if (video) {
    void video.play().catch(() => {});
  }
}

function stopPreviewHover(event) {
  const card = event.target.closest(".project-card");
  if (!card) return;
  if (event.type === "mouseout" && card.contains(event.relatedTarget)) return;
  card.classList.remove("is-playing");
  const video = card.querySelector(".preview-video");
  if (video) {
    video.pause();
    video.currentTime = 0;
  }
}

function getVisibleProjects() {
  return state.bootstrap.projects.filter((project) => {
    if (state.filters.status !== "all" && project.status !== state.filters.status) {
      return false;
    }
    if (state.filters.category !== "all" && project.category !== state.filters.category) {
      return false;
    }
    if (!state.filters.query) {
      return true;
    }
    const haystack = [
      project.name,
      project.summary,
      project.category,
      ...arrayOrEmpty(project.tags),
      ...arrayOrEmpty(project.stack),
      ...arrayOrEmpty(project.highlights)
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(state.filters.query);
  });
}

function findProject(projectId) {
  return state.bootstrap.projects.find((project) => project.id === projectId);
}

function computeStats(projects) {
  return {
    total: projects.length,
    inProgress: projects.filter((project) => project.status === "in-progress").length,
    active: projects.filter((project) => project.status === "active").length,
    categories: new Set(projects.map((project) => project.category)).size
  };
}

function arrayOrEmpty(value) {
  return Array.isArray(value) ? value : [];
}

function splitComma(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitLines(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitPairs(value) {
  return splitLines(value).map((line) => {
    const [first, ...rest] = line.split("|");
    return {
      step: (first || "").trim(),
      desc: rest.join("|").trim(),
      label: (first || "").trim(),
      value: rest.join("|").trim()
    };
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDate(value) {
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      dateStyle: "medium",
      timeStyle: "short"
    }).format(new Date(value));
  } catch {
    return value;
  }
}

async function api(url, options = {}) {
  const request = {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json"
    }
  };

  if (options.body !== undefined) {
    request.body = JSON.stringify(options.body);
  }

  const response = await fetch(url, request);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.detail || `HTTP ${response.status}`);
  }
  return data;
}
