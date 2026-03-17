const state = {
  bootstrap: null,
  analytics: null,
  filters: {
    query: "",
    status: "all",
    category: "all"
  },
  currentProjectId: null,
  currentTimelineProjectId: null,
  currentBlogId: null,
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
  aboutTitle: document.getElementById("about-title"),
  ownerSummary: document.getElementById("owner-summary"),
  aboutMetrics: document.getElementById("about-metrics"),
  aboutLinks: document.getElementById("about-links"),
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
  inProgressCount: document.getElementById("in-progress-count"),
  activeCount: document.getElementById("active-count"),
  inProgressBoard: document.getElementById("in-progress-board"),
  activeBoard: document.getElementById("active-board"),
  categoryOverview: document.getElementById("category-overview"),
  timelineLegend: document.getElementById("timeline-legend"),
  projectTimelineMap: document.getElementById("project-timeline-map"),
  timelineFocus: document.getElementById("timeline-focus"),
  adminPanel: document.getElementById("admin-panel"),
  newBlogButton: document.getElementById("new-blog-button"),
  blogGrid: document.getElementById("blog-grid"),
  blogModal: document.getElementById("blog-modal"),
  blogModalBody: document.getElementById("blog-modal-body"),
  blogEditorModal: document.getElementById("blog-editor-modal"),
  blogEditorForm: document.getElementById("blog-editor-form"),
  detailModal: document.getElementById("detail-modal"),
  detailModalBody: document.getElementById("detail-modal-body"),
  editorModal: document.getElementById("editor-modal"),
  editorForm: document.getElementById("project-editor-form")
};

const PROJECT_TITLE_OVERRIDES = {
  "calc-stt-cer-colab": "STT 오차를 숫자로 추적하는 진단실",
  "morpheme-analysis-notebook": "말버릇을 쪼개보는 형태소 분석 노트",
  "mood-tracker": "감정의 흐름을 기록하는 무드 트래커",
  "260218-ope-log-anlayze": "로그 속 숨은 운영 이슈를 건져낸 분석기",
  "260315-moe-prompt-routing": "질문마다 맞는 프롬프트를 고르는 라우팅 엔진",
  "dowon-codex-manager-memory-work-summary-v4": "에이전트 작업기억을 한 장으로 묶는 실험",
  "gemini-multiturn-tester-v3": "멀티턴 LLM을 끝까지 흔드는 테스트 벤치",
  "operation-log-analyzer": "운영 로그에서 원인을 역추적하는 워크벤치",
  "project-naming-rule": "이름이 인상을 바꾸는 프로젝트 네이밍 룰",
  "prompt-auto-evaluation": "프롬프트 승자를 자동으로 가려내는 평가 파이프라인",
  "scripts": "반복 작업을 덜어주는 자동화 툴박스",
  "semantic-verb-schema": "한국어 동사를 기능 스키마로 재구성한 실험",
  "todack": "토닥, 감정을 다루는 작은 회복 인터페이스",
  "work-summary-versions": "일의 흔적을 버전으로 축적한 아카이브",
  "utterance-similarity-notebook": "비슷한 발화의 차이를 잡아내는 분석 노트"
};

const ABOUT_VALUE_PROPS = [
  "기획에서 끝내지 않고 로그, 지표, 룰, 운영정책까지 연결해 실제 개선으로 닫습니다.",
  "모호한 문제를 조건-관측-가설-검증 구조로 쪼개 팀이 바로 움직일 수 있는 언어로 바꿉니다.",
  "음성인식, 챗봇, LLM Agent 프로젝트에서 품질과 사용자 경험을 함께 올리는 실행형 PM입니다."
];

const ABOUT_METRIC_OVERRIDES = [
  {
    label: "프로젝트 수행/지원",
    value: "30건+",
    note: "다양한 도메인의 챗봇·AI 프로젝트를 직접 리드하거나 지원"
  },
  {
    label: "KPI 목표 달성률",
    value: "평균 105%+",
    note: "정답률·주제분류율 등 주요 KPI 평균 기준"
  },
  {
    label: "룰베이스 튜닝",
    value: "56.24% -> 74.22%",
    note: "비-19 판정 성능을 룰 보강과 weak label 정리로 개선"
  },
  {
    label: "음성인식 관련 출원",
    value: "5건",
    note: "2025년 기준 음성인식 관련 임시 출원"
  }
];

const CAREER_HIGHLIGHT_OVERRIDES = {
  "SK인텔릭스": ["State Machine Agent", "On-device/Cloud Chaining", "평가 체계 구축"],
  "올거나이즈코리아": ["RAG 서비스 기획", "정확도 개선", "PoC to 운영"],
  "와이즈버즈": ["정책 설계", "운영 프로세스 개선", "광고 플랫폼 기획"],
  "와이즈넛": ["공공 챗봇 구축", "다국어 QA", "시나리오 품질 개선"]
};

const CATEGORY_GROUPS = [
  {
    label: "AI Product & UX",
    match: ["Wellness Product", "General"]
  },
  {
    label: "LLM & Prompt",
    match: ["LLM Evaluation Tooling", "Prompt Evaluation"]
  },
  {
    label: "NLU & Data",
    match: ["NLU Data Analysis", "NLU Similarity Analysis", "NLU Schema Engineering"]
  },
  {
    label: "Speech & Ops",
    match: ["Speech Quality Metrics", "Operational Analytics"]
  }
];

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

  [elements.inProgressBoard, elements.activeBoard, elements.categoryOverview].filter(Boolean).forEach((container) => {
    container.addEventListener("click", (event) => {
      const item = event.target.closest("[data-project-id]");
      if (!item) return;
      openDetail(item.dataset.projectId);
    });
    container.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const item = event.target.closest("[data-project-id]");
      if (!item) return;
      event.preventDefault();
      openDetail(item.dataset.projectId);
    });
  });

  elements.projectTimelineMap.addEventListener("click", (event) => {
    const action = event.target.closest("[data-timeline-action]");
    if (action) {
      const projectId = action.dataset.projectId || state.currentTimelineProjectId;
      if (!projectId) return;
      if (action.dataset.timelineAction === "open") {
        openDetail(projectId);
        return;
      }
      if (action.dataset.timelineAction === "edit") {
        openEditor(findProject(projectId));
        return;
      }
      return;
    }
    const timelineItem = event.target.closest("[data-timeline-project]");
    if (!timelineItem) return;
    openDetail(timelineItem.dataset.timelineProject);
  });

  elements.projectTimelineMap.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const timelineItem = event.target.closest("[data-timeline-project]");
    if (!timelineItem) return;
    event.preventDefault();
    openDetail(timelineItem.dataset.timelineProject);
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
  elements.newBlogButton?.addEventListener("click", () => openBlogEditor(null));

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

  elements.blogGrid?.addEventListener("click", (event) => {
    const actionButton = event.target.closest("[data-blog-action]");
    if (actionButton) {
      const blogId = actionButton.dataset.blogId;
      if (!blogId) return;
      if (actionButton.dataset.blogAction === "edit") {
        openBlogEditor(findBlogPost(blogId));
      }
      if (actionButton.dataset.blogAction === "delete") {
        void deleteBlogPost(blogId);
      }
      return;
    }

    const card = event.target.closest("[data-blog-id]");
    if (!card) return;
    openBlogDetail(card.dataset.blogId);
  });

  elements.blogGrid?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest("[data-blog-id]");
    if (!card) return;
    event.preventDefault();
    openBlogDetail(card.dataset.blogId);
  });

  elements.blogModal?.addEventListener("click", (event) => {
    if (event.target.matches("[data-close-blog]")) {
      closeBlogDetail();
      return;
    }

    const actionButton = event.target.closest("[data-blog-detail-action]");
    if (!actionButton) return;
    const blogId = actionButton.dataset.blogId || state.currentBlogId;
    if (!blogId) return;
    if (actionButton.dataset.blogDetailAction === "edit") {
      openBlogEditor(findBlogPost(blogId));
    }
    if (actionButton.dataset.blogDetailAction === "delete") {
      void deleteBlogPost(blogId);
    }
  });

  elements.blogEditorModal?.addEventListener("click", (event) => {
    if (event.target.matches("[data-close-blog-editor]")) {
      closeBlogEditor();
    }
  });

  elements.blogEditorForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveBlogPost();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDetail();
      closeEditor();
      closeBlogDetail();
      closeBlogEditor();
    }
  });
}

async function refreshApp() {
  state.bootstrap = await api("/api/bootstrap");
  const timelineProjects = getTimelineProjects();
  if (!findProject(state.currentTimelineProjectId)) {
    state.currentTimelineProjectId = timelineProjects[0]?.id || null;
  }
  if (!findBlogPost(state.currentBlogId)) {
    state.currentBlogId = null;
  }
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
  renderCareerTimeline();
  renderSkills();
  renderCases();
  renderProjectSnapshot();
  renderProjectTimeline();
  renderAdminPanel();
  renderProjects();
  renderBlog();
  renderAuthArea();
  renderOpenDetail();
  renderOpenBlog();
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
  elements.newBlogButton?.classList.toggle("hidden", state.bootstrap.viewer?.role !== "admin");
}

function renderHero() {
  const { site, owner, projects } = state.bootstrap;
  const stats = computeStats(projects);

  elements.heroBadge.textContent = site.heroBadge || "";
  elements.heroTitle.textContent = "프로젝트 라이브러리";
  elements.heroDescription.textContent = "";
  if (elements.heroNote) {
    elements.heroNote.textContent = site.heroNote || "";
  }
  elements.ownerSummary.textContent = owner.careerSummary || "";
  elements.searchInput.placeholder = site.searchPlaceholder || "검색";

  elements.focusTags.innerHTML = arrayOrEmpty(owner.focusAreas)
    .map((item) => `<span class="tag-pill">${escapeHtml(item)}</span>`)
    .join("");

  const statItems = [
    { label: "프로젝트", value: String(stats.total), ratio: 1, tone: "neutral" },
    { label: "진행중", value: String(stats.inProgress), ratio: stats.inProgress / Math.max(1, stats.total), tone: "warning" },
    { label: "운영/완료", value: String(stats.active), ratio: stats.active / Math.max(1, stats.total), tone: "success" },
    { label: "카테고리", value: String(stats.categories), ratio: stats.categories / Math.max(1, stats.total), tone: "accent" }
  ];

  elements.heroMiniStats.innerHTML = statItems
    .map(
      (item) => `
        <article class="mini-stat-card radial ${escapeHtml(item.tone)}">
          <div class="radial-stat-ring" style="--progress:${Math.max(0.14, item.ratio)};">
            <div class="radial-stat-core">
              <strong>${escapeHtml(item.value)}</strong>
              <span>${escapeHtml(item.label)}</span>
            </div>
          </div>
        </article>
      `
    )
    .join("");
}

function renderFilters() {
  const categories = ["all", ...new Set(state.bootstrap.projects.map((project) => getProjectCategory(project)))];
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
  const links = state.bootstrap.links || {};
  const site = state.bootstrap.site || {};
  const aboutSignature = buildAboutSignature();
  const valueProps = getAboutValueProps(profile);
  const aboutMetrics = getAboutMetrics(profile);

  elements.aboutTitle.textContent = aboutSignature.title;
  elements.ownerSummary.textContent = aboutSignature.summary;
  elements.valueProps.innerHTML = valueProps
    .map((item) => `<article class="value-card">${escapeHtml(item)}</article>`)
    .join("");

  elements.aboutMetrics.innerHTML = aboutMetrics
    .map(
      (metric) => `
        <article class="metric-pill">
          <span>${escapeHtml(metric.label || "")}</span>
          <strong>${escapeHtml(metric.value || "")}</strong>
          ${metric.note ? `<small>${escapeHtml(metric.note)}</small>` : ""}
        </article>
      `
    )
    .join("");

  const linkItems = [
    links.notion
      ? `<a class="about-link-card" href="${escapeHtml(links.notion)}" target="_blank" rel="noreferrer noopener">
          <strong>Notion</strong>
          <span>프로젝트/문서 모음 열기</span>
        </a>`
      : "",
    site.externalLink
      ? `<a class="about-link-card" href="${escapeHtml(site.externalLink)}" target="_blank" rel="noreferrer noopener">
          <strong>External</strong>
          <span>외부 포트폴리오 링크</span>
        </a>`
      : "",
    `<article class="about-link-card muted">
        <strong>Persona</strong>
        <span>문제를 수치로 설명하고 팀을 움직이는 실행형 AI PM</span>
      </article>`
  ].filter(Boolean);

  elements.aboutLinks.innerHTML = linkItems.join("");
}

function renderCareerTimeline() {
  const profile = state.bootstrap.profile || {};
  const timeline = arrayOrEmpty(profile.careerTimeline)
    .map(
      (item) => `
        <article class="career-line-item">
          <span class="career-line-dot"></span>
          <div class="career-period-pill">${escapeHtml(item.period || "")}</div>
          <div class="career-line-card">
            <div class="career-title-row">
              <div>
                <h3>${escapeHtml(item.company || "")}</h3>
                <p class="career-role">${escapeHtml(item.role || "")}</p>
              </div>
            </div>
            <p class="timeline-copy">${escapeHtml(item.summary || "")}</p>
          </div>
        </article>
      `
    )
    .join("");

  elements.careerTimeline.innerHTML = `
    <div class="career-line-scroll">
      <div class="career-line-track">${timeline}</div>
    </div>
  `;
}

function renderProjectTimeline() {
  const projects = getTimelineProjects();
  if (!projects.length) {
    elements.timelineLegend.innerHTML = "";
    elements.projectTimelineMap.innerHTML = `<article class="empty-state">타임라인 데이터가 없습니다.</article>`;
    return;
  }

  const enriched = projects
    .map((project) => buildTimelineEntry(project))
    .sort((left, right) => left.start.getTime() - right.start.getTime());

  elements.timelineLegend.innerHTML = `
    <span class="timeline-legend-pill"><i class="legend-dot active"></i>프로젝트 진행</span>
    <span class="timeline-legend-pill"><i class="legend-dot difficulty"></i>난관 구간</span>
    <span class="timeline-legend-pill"><i class="legend-dot milestone"></i>해결 힌트</span>
  `;

  elements.projectTimelineMap.innerHTML = renderTimelineChronicle(enriched);
}

function renderTimelineChronicle(entries) {
  return `
    <div class="timeline-chronicle-shell">
      <div class="timeline-chronicle-track">
        ${entries.map((entry) => renderChronicleItem(entry)).join("")}
      </div>
    </div>
  `;
}

function renderChronicleItem(entry) {
  const story = entry.story;
  const difficultyCopy = entry.difficulties[0]?.label || "핵심 이슈 정리";
  const impactCopy = arrayOrEmpty(story.impact)[0] || arrayOrEmpty(entry.project.highlights)[0] || entry.project.summary;
  return `
    <article class="chronicle-item ${entry.project.status === "in-progress" ? "warning" : "success"}" tabindex="0" data-timeline-project="${escapeHtml(entry.project.id)}">
      <span class="chronicle-stem"></span>
      <span class="chronicle-node ${entry.project.status === "in-progress" ? "warning" : "success"}"></span>
      <div class="chronicle-date">${escapeHtml(entry.label)}</div>
      <div class="chronicle-card">
        <div class="chronicle-head">
          <span class="badge ${entry.project.status === "in-progress" ? "warning" : "success"}">
            ${entry.project.status === "in-progress" ? "진행중" : "완료/운영"}
          </span>
          <span class="chronicle-category">${escapeHtml(getProjectCategory(entry.project))}</span>
        </div>
        <h3>${escapeHtml(getProjectDisplayName(entry.project))}</h3>
        <p>${escapeHtml(story.challenge || entry.project.summary)}</p>
        <div class="chronicle-meta">
          <span class="chronicle-pill difficulty">${escapeHtml(truncate(difficultyCopy, 42))}</span>
          <span class="chronicle-pill">${escapeHtml(truncate(impactCopy, 42))}</span>
        </div>
      </div>
    </article>
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

function getTimelineProjects() {
  return [...(state.bootstrap?.projects || [])].sort((left, right) => {
    const leftDate = parseTimelineDate(left.timeline?.start || left.createdAt)?.getTime() || 0;
    const rightDate = parseTimelineDate(right.timeline?.start || right.createdAt)?.getTime() || 0;
    return rightDate - leftDate;
  });
}

function buildTimelineEntry(project) {
  const story = buildProjectStory(project);
  const start = parseTimelineDate(project.timeline?.start || project.createdAt) || new Date();
  const end = parseTimelineDate(project.timeline?.end || start) || start;
  const difficulties = arrayOrEmpty(project.timeline?.difficultyWindows).length
    ? project.timeline.difficultyWindows.map((item) => normalizeDifficultyWindow(item, start, end))
    : synthesizeDifficultyWindows(project, story, start, end);
  const milestones = arrayOrEmpty(project.timeline?.milestones).length
    ? project.timeline.milestones.map((item) => normalizeMilestone(item, end))
    : synthesizeMilestones(story, end);

  return {
    project,
    story,
    start,
    end: end < start ? start : end,
    label: project.timeline?.label || formatTimelineLabel(start, end),
    difficulties,
    milestones
  };
}

function buildTimelineRange(entries) {
  const points = [];
  entries.forEach((entry) => {
    points.push(monthStart(entry.start), monthStart(entry.end));
    entry.difficulties.forEach((item) => {
      points.push(monthStart(item.start), monthStart(item.end));
    });
    entry.milestones.forEach((item) => {
      points.push(monthStart(item.date));
    });
  });

  const minPoint = points.reduce((current, value) => (value && (!current || value < current) ? value : current), null);
  const maxPoint = points.reduce((current, value) => (value && (!current || value > current) ? value : current), null);
  const start = minPoint || monthStart(new Date());
  const end = maxPoint || monthStart(new Date());
  const monthCount = Math.max(1, diffMonths(start, end) + 1);
  const labels = [];
  for (let index = 0; index < monthCount; index += 1) {
    labels.push(addMonths(start, index));
  }
  return { start, end, monthCount, labels };
}

function renderTimelineRow(entry, range, isActive) {
  const viewer = state.bootstrap.viewer;
  const left = monthOffset(entry.start, range);
  const width = Math.max(6, monthSpan(entry.start, entry.end, range));
  const displayName = getProjectDisplayName(entry.project);
  const difficultyMarkup = entry.difficulties
    .map((item) => {
      const diffLeft = monthOffset(item.start, range);
      const diffWidth = Math.max(4, monthSpan(item.start, item.end, range));
      return `<span class="timeline-difficulty ${escapeHtml(item.severity)}" style="left:${diffLeft}%; width:${diffWidth}%;" title="${escapeHtml(item.label)}"></span>`;
    })
    .join("");
  const milestoneMarkup = entry.milestones
    .map((item) => {
      const markerLeft = monthOffset(item.date, range);
      return `<span class="timeline-milestone ${escapeHtml(item.tone)}" style="left:${markerLeft}%;" title="${escapeHtml(item.label)}"></span>`;
    })
    .join("");

  return `
    <article class="timeline-project-row ${isActive ? "active" : ""}" tabindex="0" data-timeline-project="${escapeHtml(entry.project.id)}">
      <div class="timeline-row-copy">
        <div class="timeline-row-top">
          <span class="badge ${entry.project.status === "in-progress" ? "warning" : "success"}">
            ${entry.project.status === "in-progress" ? "진행중" : "완료/운영"}
          </span>
          <span class="timeline-row-label">${escapeHtml(entry.label)}</span>
        </div>
        <h3>${escapeHtml(displayName)}</h3>
        <p>${escapeHtml(entry.story.challenge || entry.project.summary)}</p>
        <div class="timeline-row-tags">
          ${arrayOrEmpty(entry.project.tags).slice(0, 3).map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
        </div>
      </div>
      <div class="timeline-row-track-wrap">
        <div class="timeline-row-scale">
          ${range.labels.map((label) => `<span>${escapeHtml(label.toISOString().slice(2, 7).replace("-", "."))}</span>`).join("")}
        </div>
        <div class="timeline-row-track">
          <div class="timeline-grid-lines">
            ${range.labels.map(() => `<span></span>`).join("")}
          </div>
          <span class="timeline-project-bar ${entry.project.status === "in-progress" ? "warning" : "success"}" style="left:${left}%; width:${width}%;">
            <strong>${escapeHtml(getProjectCategory(entry.project))}</strong>
          </span>
          ${difficultyMarkup}
          ${milestoneMarkup}
        </div>
        ${
          viewer?.role === "admin"
            ? `<div class="timeline-row-actions"><button type="button" class="ghost-button compact" data-timeline-action="edit" data-project-id="${escapeHtml(entry.project.id)}">수정</button></div>`
            : ""
        }
      </div>
      ${
        isActive
          ? `
            <div class="timeline-row-expanded">
              ${renderTimelineFocus(entry)}
            </div>
          `
          : ""
      }
    </article>
  `;
}

function renderTimelineFocus(entry) {
  const viewer = state.bootstrap.viewer;
  const project = entry.project;
  const story = entry.story;
  const impactList = arrayOrEmpty(story.impact).length ? story.impact : arrayOrEmpty(project.highlights);
  const displayName = getProjectDisplayName(project);

  return `
    <div class="timeline-focus-shell inline">
      <div class="panel-header timeline-focus-head">
        <div>
          <p class="panel-kicker">Timeline Focus</p>
          <h2>${escapeHtml(displayName)}</h2>
          <p class="panel-summary">${escapeHtml(story.narrative || project.summary)}</p>
        </div>
        <div class="timeline-focus-actions">
          <button type="button" class="primary-button" data-timeline-action="open" data-project-id="${escapeHtml(project.id)}">상세 보기</button>
          ${
            viewer?.role === "admin"
              ? `<button type="button" class="ghost-button" data-timeline-action="edit" data-project-id="${escapeHtml(project.id)}">타임라인 수정</button>`
              : ""
          }
        </div>
      </div>

      <div class="timeline-focus-grid">
        <div class="timeline-focus-column">
          <section class="focus-block challenge">
            <p class="panel-kicker">Difficulty</p>
            <article class="focus-highlight-card">
              <h3>${escapeHtml(story.challenge || "핵심 어려움 입력 필요")}</h3>
              <p>${escapeHtml(project.summary)}</p>
            </article>
          </section>

          <section class="focus-block support-stack">
            <div class="focus-support-card">
              <p class="panel-kicker">Impact</p>
              <div class="focus-impact-list">
                ${impactList.map((item) => `<span class="focus-impact-pill">${escapeHtml(item)}</span>`).join("")}
              </div>
            </div>
            <div class="focus-support-card">
              <p class="panel-kicker">Memory Mapping</p>
              <div class="memory-chip-row">
                ${
                  story.relatedCases.length
                    ? story.relatedCases.map((item) => `<span class="memory-chip">${escapeHtml(item.title)}</span>`).join("")
                    : `<span class="memory-chip muted">관련 메모 정리중</span>`
                }
              </div>
            </div>
          </section>
        </div>

        <section class="focus-block timeline-flow-block">
          <p class="panel-kicker">Resolution Flow</p>
          <div class="resolution-graph">
            <article class="resolution-node problem">
              <small>Problem</small>
              <strong>${escapeHtml(truncate(story.challenge || project.summary, 70))}</strong>
            </article>
            ${arrayOrEmpty(story.attempts)
              .slice(0, 3)
              .map(
                (item, index) => `
                  <article class="resolution-node attempt">
                    <small>Try ${index + 1}</small>
                    <strong>${escapeHtml(truncate(item, 56))}</strong>
                  </article>
                `
              )
              .join("")}
            <article class="resolution-node result">
              <small>Resolve</small>
              <strong>${escapeHtml(truncate(story.resolution || project.detail?.readmeSummary?.[0] || project.summary, 70))}</strong>
            </article>
          </div>
        </section>
      </div>
    </div>
  `;
}

function buildAboutSignature() {
  return {
    title: "문제를 끝까지 수치로 증명하는 AI Product Manager",
    summary:
      "기획만 하는 PM이 아니라, 로그를 읽고 지표를 다시 세우고 룰과 운영정책까지 연결해 실제 품질 개선으로 닫는 사람입니다. 음성인식, 챗봇, LLM Agent 영역에서 '왜 안 되는지'를 근거로 설명하고 '어떻게 좋아질지'를 바로 실험으로 옮깁니다."
  };
}

function getAboutValueProps(profile) {
  const values = arrayOrEmpty(profile.valueProposition);
  return ABOUT_VALUE_PROPS.length ? ABOUT_VALUE_PROPS : values;
}

function getAboutMetrics(profile) {
  const metrics = ABOUT_METRIC_OVERRIDES.length ? ABOUT_METRIC_OVERRIDES : arrayOrEmpty(profile.coreMetrics);
  return metrics.slice(0, 4);
}

function buildCareerHighlights(item) {
  const presets = CAREER_HIGHLIGHT_OVERRIDES[item.company];
  if (presets?.length) {
    return presets;
  }

  return arrayOrEmpty(item.summary?.split(/[,.]/))
    .map((entry) => entry.trim())
    .filter(Boolean)
    .slice(0, 3);
}

function buildCareerIndexLabel(item) {
  if ((item.period || "").includes("현재")) {
    return "Current";
  }
  const firstYear = String(item.period || "").slice(0, 4);
  return firstYear ? `${firstYear} Archive` : "Career";
}

function buildProjectStory(project) {
  const explicitStory = project.story || {};
  const relatedCases = getRelatedCases(project);
  const primaryCase = relatedCases[0];
  const fallbackAttempts = primaryCase?.attempts || arrayOrEmpty(project.detail?.workflow).map((item) => item.desc || item.step);

  return {
    narrative: explicitStory.narrative || project.summary,
    challenge: explicitStory.challenge || primaryCase?.problem || project.summary,
    attempts: arrayOrEmpty(explicitStory.attempts).length ? explicitStory.attempts : fallbackAttempts.slice(0, 4),
    resolution: explicitStory.resolution || primaryCase?.result || arrayOrEmpty(project.detail?.readmeSummary)[0] || project.summary,
    impact: arrayOrEmpty(explicitStory.impact).length ? explicitStory.impact : arrayOrEmpty(project.highlights),
    caseIds: arrayOrEmpty(explicitStory.caseIds),
    relatedCases
  };
}

function getRelatedCases(project) {
  const cases = arrayOrEmpty(state.bootstrap.cases);
  const explicitIds = new Set(arrayOrEmpty(project.story?.caseIds));
  const text = [
    project.id,
    project.name,
    project.category,
    project.summary,
    ...arrayOrEmpty(project.tags),
    ...arrayOrEmpty(project.stack)
  ]
    .join(" ")
    .toLowerCase();

  const scored = cases
    .map((item) => {
      if (explicitIds.has(item.id)) {
        return { item, score: 100 };
      }
      let score = 0;
      const keywords = buildCaseKeywords(item.id);
      keywords.forEach((keyword) => {
        if (text.includes(keyword)) score += 2;
      });
      if (text.includes("stt") && item.id === "stt-physical-explainability") score += 4;
      if ((text.includes("nlu") || text.includes("형태소") || text.includes("schema")) && item.id === "nlu-robustness") score += 4;
      if ((text.includes("prompt") || text.includes("eval") || text.includes("judge") || text.includes("gemini")) && item.id === "tooling-bottleneck") score += 4;
      if ((text.includes("log") || text.includes("ops") || text.includes("operation")) && item.id === "log-driven-debug") score += 4;
      return { item, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, 2)
    .map((entry) => entry.item);

  return scored.length ? scored : cases.slice(0, 1);
}

function buildCaseKeywords(caseId) {
  const keywordMap = {
    "stt-physical-explainability": ["stt", "speech", "cer", "robot", "voice", "인식"],
    "utterance-spec-expansion": ["발화", "spec", "schema", "nlu", "intent"],
    "nlu-robustness": ["nlu", "형태소", "유사도", "intent", "schema", "corpus"],
    "log-driven-debug": ["log", "ops", "operation", "analytics", "debug"],
    "tooling-bottleneck": ["prompt", "eval", "judge", "script", "automation", "tooling", "gemini"],
    "tone-and-copy": ["copy", "tone", "prompt", "text", "ux"]
  };
  return keywordMap[caseId] || [];
}

function synthesizeDifficultyWindows(project, story, start, end) {
  const totalDays = Math.max(1, Math.round((end - start) / (1000 * 60 * 60 * 24)));
  const firstPoint = new Date(start.getTime() + totalDays * 0.2 * 24 * 60 * 60 * 1000);
  const secondPoint = new Date(start.getTime() + totalDays * 0.55 * 24 * 60 * 60 * 1000);
  return [
    {
      label: truncate(story.relatedCases[0]?.title || "핵심 난관", 24),
      start: firstPoint,
      end: secondPoint,
      severity: project.status === "in-progress" ? "high" : "medium"
    }
  ];
}

function synthesizeMilestones(story, end) {
  return arrayOrEmpty(story.attempts)
    .slice(0, 2)
    .map((item, index) => ({
      label: truncate(item, 28),
      date: new Date(end.getTime() - (index + 1) * 10 * 24 * 60 * 60 * 1000),
      tone: index === 0 ? "success" : "warning"
    }));
}

function normalizeDifficultyWindow(item, fallbackStart, fallbackEnd) {
  return {
    label: item.label || item.name || "난관",
    start: parseTimelineDate(item.start) || fallbackStart,
    end: parseTimelineDate(item.end) || fallbackEnd || fallbackStart,
    severity: ["low", "medium", "high"].includes(item.severity) ? item.severity : "medium"
  };
}

function normalizeMilestone(item, fallbackDate) {
  return {
    label: item.label || item.name || "",
    date: parseTimelineDate(item.date) || fallbackDate,
    tone: ["warning", "success", "neutral"].includes(item.tone) ? item.tone : "neutral"
  };
}

function parseTimelineDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function monthStart(date) {
  if (!date) return null;
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function diffMonths(start, end) {
  return (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth());
}

function addMonths(base, offset) {
  return new Date(base.getFullYear(), base.getMonth() + offset, 1);
}

function monthOffset(date, range) {
  const baseDiff = diffMonths(range.start, monthStart(date));
  return (baseDiff / range.monthCount) * 100;
}

function monthSpan(start, end, range) {
  const span = diffMonths(monthStart(start), monthStart(end)) + 1;
  return (span / range.monthCount) * 100;
}

function formatTimelineLabel(start, end) {
  const startLabel = `${start.getFullYear()}.${String(start.getMonth() + 1).padStart(2, "0")}`;
  const endLabel = `${end.getFullYear()}.${String(end.getMonth() + 1).padStart(2, "0")}`;
  return startLabel === endLabel ? startLabel : `${startLabel} - ${endLabel}`;
}

function truncate(value, maxLength) {
  const text = String(value || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
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

function renderProjectSnapshot() {
  const projects = state.bootstrap.projects.slice();
  const inProgressProjects = projects.filter((project) => project.status === "in-progress");
  const activeProjects = projects.filter((project) => project.status === "active");

  elements.inProgressCount.textContent = `${inProgressProjects.length}개`;
  elements.activeCount.textContent = `${activeProjects.length}개`;

  elements.inProgressBoard.innerHTML = inProgressProjects.length
    ? inProgressProjects.map((project) => renderSnapshotItem(project, "warning")).join("")
    : `<article class="empty-state small">진행중 프로젝트가 없습니다.</article>`;

  elements.activeBoard.innerHTML = activeProjects.length
    ? activeProjects.map((project) => renderSnapshotItem(project, "success")).join("")
    : `<article class="empty-state small">완료/운영 프로젝트가 없습니다.</article>`;

  const categoryMap = new Map();
  for (const project of projects) {
    const category = getProjectCategory(project);
    if (!categoryMap.has(category)) {
      categoryMap.set(category, []);
    }
    categoryMap.get(category).push(project);
  }

  if (elements.categoryOverview) {
    elements.categoryOverview.innerHTML = [...categoryMap.entries()]
      .sort((left, right) => right[1].length - left[1].length || left[0].localeCompare(right[0]))
      .map(([category, items]) => {
        return `
          <article class="category-cluster">
            <div class="category-cluster-head">
              <div>
                <h3>${escapeHtml(category)}</h3>
                <p>${escapeHtml(String(items.length))}개 프로젝트</p>
              </div>
            </div>
            <div class="category-link-list">
              ${items
                .map(
                  (project) => `
                    <button type="button" class="category-link" data-project-id="${escapeHtml(project.id)}">
                      <span>${escapeHtml(getProjectDisplayName(project))}</span>
                      <small>${project.status === "in-progress" ? "진행중" : "완료/운영"}</small>
                    </button>
                  `
                )
                .join("")}
            </div>
          </article>
        `;
      })
      .join("");
  }
}

function renderSnapshotItem(project, tone) {
  const displayName = getProjectDisplayName(project);
  const badgeText = project.status === "in-progress" ? "진행중" : "완료/운영";
  const supportCopy =
    arrayOrEmpty(project.highlights)[0] ||
    arrayOrEmpty(project.tags).slice(0, 2).join(" · ") ||
    project.summary;

  return `
    <article class="snapshot-item ${tone}" tabindex="0" data-project-id="${escapeHtml(project.id)}">
      <div class="snapshot-top">
        <span class="badge ${tone}">${escapeHtml(badgeText)}</span>
        <span class="snapshot-category">${escapeHtml(getProjectCategory(project))}</span>
      </div>
      <h3>${escapeHtml(displayName)}</h3>
      <p>${escapeHtml(project.summary)}</p>
      <div class="snapshot-tags">
        ${arrayOrEmpty(project.tags).slice(0, 3).map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="snapshot-foot">${escapeHtml(supportCopy)}</div>
    </article>
  `;
}

function renderProjects() {
  const projects = getVisibleProjects();
  const total = state.bootstrap.projects.length;
  elements.collectionMeta.innerHTML = `
    <span class="collection-pill">프로젝트 ${escapeHtml(String(projects.length))} / ${escapeHtml(String(total))}</span>
  `;

  if (!projects.length) {
    elements.projectGrid.innerHTML = `<article class="empty-state">현재 필터에 맞는 프로젝트가 없습니다.</article>`;
    return;
  }

  elements.projectGrid.innerHTML = projects.map(renderProjectCard).join("");
}

function renderBlog() {
  if (!elements.blogGrid) return;
  const posts = arrayOrEmpty(state.bootstrap.blogPosts)
    .filter((post) => post.status === "published" || state.bootstrap.viewer?.role === "admin")
    .sort((left, right) => String(right.updatedAt || "").localeCompare(String(left.updatedAt || "")));

  if (!posts.length) {
    elements.blogGrid.innerHTML = `<article class="empty-state">아직 공개된 글이 없습니다.</article>`;
    return;
  }

  elements.blogGrid.innerHTML = posts.map(renderBlogCard).join("");
}

function renderBlogCard(post) {
  const viewer = state.bootstrap.viewer;
  return `
    <article class="blog-card" tabindex="0" data-blog-id="${escapeHtml(post.id)}">
      <div class="blog-card-head">
        <div class="blog-card-meta">
          <span class="badge category">${escapeHtml(post.status === "draft" ? "Draft" : "Published")}</span>
          <span class="blog-date">${escapeHtml(formatBlogDate(post.updatedAt || post.createdAt))}</span>
        </div>
        ${
          viewer?.role === "admin"
            ? `
              <div class="blog-card-actions">
                <button type="button" class="icon-button" data-blog-action="edit" data-blog-id="${escapeHtml(post.id)}">편집</button>
                <button type="button" class="icon-button danger" data-blog-action="delete" data-blog-id="${escapeHtml(post.id)}">삭제</button>
              </div>
            `
            : ""
        }
      </div>
      <h3>${escapeHtml(post.title)}</h3>
      <p class="blog-excerpt">${escapeHtml(post.excerpt || "")}</p>
      <div class="tag-row">
        ${arrayOrEmpty(post.tags).map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
      </div>
    </article>
  `;
}

function renderProjectCard(project) {
  const counts = state.bootstrap.commentCounts || {};
  const commentCount = counts[project.id] || 0;
  const viewer = state.bootstrap.viewer;
  const leadHighlight =
    arrayOrEmpty(project.highlights)[0] ||
    arrayOrEmpty(project.tags)[0] ||
    project.summary;

  return `
    <article class="project-card" tabindex="0" data-project-id="${escapeHtml(project.id)}">
      <div class="card-topline">
        <span class="badge category">${escapeHtml(getProjectCategory(project))}</span>
        <span class="badge ${project.status === "in-progress" ? "warning" : "success"}">
          ${project.status === "in-progress" ? "진행중" : "완료/운영"}
        </span>
      </div>

      ${renderPreviewMarkup(project, "card")}

      <div class="card-body">
        <div class="card-heading">
          ${renderDisplayTitle(project, "card")}
        </div>
        <p class="card-summary">${escapeHtml(project.summary)}</p>
        <div class="card-proof-line">
          <strong>이 프로젝트가 한 일</strong>
          <span>${escapeHtml(leadHighlight)}</span>
        </div>
        <div class="tag-row compact">
          ${arrayOrEmpty(project.tags).slice(0, 2).map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
        </div>
        <div class="card-footer">
          <span>${escapeHtml(arrayOrEmpty(project.stack).slice(0, 3).join(" · "))}</span>
          <span>댓글 ${escapeHtml(String(commentCount))}</span>
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
  const displayName = getProjectDisplayName(project);

  return `
    <div class="preview-surface ${variant === "detail" ? "detail" : ""}">
      ${
        preview.poster
          ? `<img class="preview-poster ${isVideo ? "" : "ghosted"}" src="${escapeHtml(preview.poster)}" alt="${escapeHtml(displayName)} preview poster" />`
          : ""
      }
      ${
        isVideo
          ? `<video class="preview-video" muted loop playsinline preload="metadata" src="${escapeHtml(preview.video)}"></video>`
          : ""
      }
      <div class="preview-overlay">
        <div class="preview-pill-row">
          <span class="preview-pill">${escapeHtml(preview.eyebrow || getProjectCategory(project))}</span>
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
  const parts = splitDisplayTitle(getProjectDisplayName(project));
  const titleTag = variant === "detail" ? "h2" : "h3";
  const projectIndex = state.bootstrap.projects.findIndex((item) => item.id === project.id) + 1;
  const supportCopy =
    arrayOrEmpty(project.highlights)[0] ||
    arrayOrEmpty(project.tags)[0] ||
    getProjectCategory(project) ||
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
  const koreanLead = words.length > 2 && words[0].length >= 4 && !/[,:]/.test(words[0]);
  const leadCount = asciiStart && words.length > 2 ? 2 : koreanLead ? 2 : 1;

  return {
    lead: words.slice(0, leadCount).join(" "),
    rest: words.slice(leadCount).join(" ")
  };
}

function getProjectDisplayName(project) {
  if (!project) return "Project";
  const override = PROJECT_TITLE_OVERRIDES[project.id];
  if (override) return override;
  return prettifyProjectName(project.name || project.id || "Project");
}

function prettifyProjectName(name) {
  const clean = String(name || "")
    .replace(/\.[a-z0-9]+$/i, "")
    .replace(/^[0-9]{6,8}[_-]*/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (!clean) return "Project";
  return clean;
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
  const story = buildProjectStory(project);
  const timelineEntry = buildTimelineEntry(project);
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
          <p class="panel-kicker">Project Info</p>
          <div class="timeline-inline-pills">
            <span class="collection-pill">${escapeHtml(timelineEntry.label)}</span>
            <span class="collection-pill subtle">${escapeHtml(getProjectCategory(project))}</span>
          </div>
          <div class="memory-chip-row">
            ${story.relatedCases.map((item) => `<span class="memory-chip">${escapeHtml(item.title)}</span>`).join("")}
          </div>
          <p class="panel-kicker detail-file-kicker">Files</p>
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
              <span class="badge category">${escapeHtml(getProjectCategory(project))}</span>
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
          <p class="panel-kicker">Difficulty</p>
          <article class="focus-highlight-card in-modal">
            <h3>${escapeHtml(story.challenge || project.summary)}</h3>
            <p>${escapeHtml(story.narrative || project.summary)}</p>
          </article>
        </section>

        <section class="detail-section">
          <p class="panel-kicker">How I Solved It</p>
          <div class="workflow-track challenge-track">
            ${arrayOrEmpty(story.attempts)
              .map(
                (item, index) => `
                  <article class="workflow-card">
                    <strong>Try ${escapeHtml(String(index + 1).padStart(2, "0"))}</strong>
                    <p>${escapeHtml(item)}</p>
                  </article>
                `
              )
              .join("")}
          </div>
        </section>

        <section class="detail-section">
          <p class="panel-kicker">Resolved / Impact</p>
          <article class="detail-result-card">
            <strong>${escapeHtml(story.resolution || project.summary)}</strong>
            <div class="focus-impact-list">
              ${arrayOrEmpty(story.impact).map((item) => `<span class="focus-impact-pill">${escapeHtml(item)}</span>`).join("")}
            </div>
          </article>
        </section>

        <section class="detail-section">
          <p class="panel-kicker">Timeline View</p>
          <div class="detail-timeline-card">
            <div class="detail-timeline-track">
              <span class="detail-timeline-bar"></span>
              ${timelineEntry.difficulties
                .map(
                  (item) => `
                    <article class="detail-timeline-window ${escapeHtml(item.severity)}">
                      <strong>${escapeHtml(item.label)}</strong>
                      <span>${escapeHtml(formatTimelineLabel(item.start, item.end))}</span>
                    </article>
                  `
                )
                .join("")}
            </div>
          </div>
        </section>

        <section class="detail-section">
          <p class="panel-kicker">Project Notes</p>
          <ul class="support-list">
            ${arrayOrEmpty(detail.readmeSummary).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}
          </ul>
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

function openBlogDetail(blogId) {
  const post = findBlogPost(blogId);
  if (!post) return;
  state.currentBlogId = blogId;
  elements.blogModal?.classList.remove("hidden");
  document.body.classList.add("modal-open");
  renderOpenBlog();
  void recordVisit("blog-detail", blogId);
}

function closeBlogDetail() {
  state.currentBlogId = null;
  elements.blogModal?.classList.add("hidden");
  if (!state.currentProjectId) {
    document.body.classList.remove("modal-open");
  }
}

function renderOpenBlog() {
  if (!elements.blogModalBody) return;
  const post = findBlogPost(state.currentBlogId);
  if (!post) {
    elements.blogModalBody.innerHTML = "";
    return;
  }

  const viewer = state.bootstrap.viewer;
  elements.blogModalBody.innerHTML = `
    <article class="blog-detail-shell">
      <div class="blog-detail-head">
        <div>
          <div class="detail-badges">
            <span class="badge category">${escapeHtml(post.status === "draft" ? "Draft" : "Published")}</span>
            <span class="collection-pill">${escapeHtml(formatBlogDate(post.updatedAt || post.createdAt))}</span>
          </div>
          <h2 id="blog-detail-title">${escapeHtml(post.title)}</h2>
          <p class="panel-summary">${escapeHtml(post.excerpt || "")}</p>
        </div>
        ${
          viewer?.role === "admin"
            ? `
              <div class="detail-admin-actions">
                <button type="button" class="ghost-button" data-blog-detail-action="edit" data-blog-id="${escapeHtml(post.id)}">편집</button>
                <button type="button" class="ghost-button danger" data-blog-detail-action="delete" data-blog-id="${escapeHtml(post.id)}">삭제</button>
              </div>
            `
            : ""
        }
      </div>
      <div class="tag-row">
        ${arrayOrEmpty(post.tags).map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="blog-markdown-body">${renderMarkdown(post.markdown || "")}</div>
    </article>
  `;
}

function openBlogEditor(post) {
  if (state.bootstrap.viewer?.role !== "admin" || !elements.blogEditorForm) return;
  const source = post || {
    id: "",
    title: "",
    excerpt: "",
    status: "published",
    tags: [],
    markdown: ""
  };
  setField(elements.blogEditorForm, "id", source.id || "");
  setField(elements.blogEditorForm, "title", source.title || "");
  setField(elements.blogEditorForm, "excerpt", source.excerpt || "");
  setField(elements.blogEditorForm, "status", source.status || "published");
  setField(elements.blogEditorForm, "tags", arrayOrEmpty(source.tags).join(", "));
  setField(elements.blogEditorForm, "markdown", source.markdown || "");
  elements.blogEditorModal?.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeBlogEditor() {
  elements.blogEditorModal?.classList.add("hidden");
  if (!state.currentProjectId && !state.currentBlogId) {
    document.body.classList.remove("modal-open");
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
    story: {
      narrative: "",
      challenge: "",
      attempts: [],
      resolution: "",
      impact: [],
      caseIds: []
    },
    timeline: {
      start: "",
      end: "",
      label: "",
      difficultyWindows: [],
      milestones: []
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
  setField(form, "storyNarrative", source.story?.narrative || "");
  setField(form, "storyChallenge", source.story?.challenge || "");
  setField(form, "storyAttempts", arrayOrEmpty(source.story?.attempts).join("\n"));
  setField(form, "storyResolution", source.story?.resolution || "");
  setField(form, "storyImpact", arrayOrEmpty(source.story?.impact).join("\n"));
  setField(form, "storyCaseIds", arrayOrEmpty(source.story?.caseIds).join(", "));
  setField(form, "timelineStart", source.timeline?.start || "");
  setField(form, "timelineEnd", source.timeline?.end || "");
  setField(form, "timelineLabel", source.timeline?.label || "");
  setField(
    form,
    "timelineDifficulty",
    arrayOrEmpty(source.timeline?.difficultyWindows)
      .map((item) => `${item.label || ""}|${item.start || ""}|${item.end || ""}|${item.severity || ""}`)
      .join("\n")
  );
  setField(
    form,
    "timelineMilestones",
    arrayOrEmpty(source.timeline?.milestones)
      .map((item) => `${item.label || ""}|${item.date || ""}|${item.tone || ""}`)
      .join("\n")
  );
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
    story: {
      narrative: formData.get("storyNarrative"),
      challenge: formData.get("storyChallenge"),
      attempts: splitLines(formData.get("storyAttempts")),
      resolution: formData.get("storyResolution"),
      impact: splitLines(formData.get("storyImpact")),
      caseIds: splitComma(formData.get("storyCaseIds"))
    },
    timeline: {
      start: formData.get("timelineStart"),
      end: formData.get("timelineEnd"),
      label: formData.get("timelineLabel"),
      difficultyWindows: splitTimelineWindows(formData.get("timelineDifficulty")),
      milestones: splitTimelineMilestones(formData.get("timelineMilestones"))
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
  const confirmed = window.confirm(`${getProjectDisplayName(project)} 카드를 삭제할까요? 댓글도 함께 삭제됩니다.`);
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

async function saveBlogPost() {
  if (!elements.blogEditorForm) return;
  const formData = new FormData(elements.blogEditorForm);
  const blogPost = {
    id: formData.get("id"),
    title: formData.get("title"),
    excerpt: formData.get("excerpt"),
    status: formData.get("status"),
    tags: splitComma(formData.get("tags")),
    markdown: formData.get("markdown")
  };

  try {
    await api("/api/blog", {
      method: "POST",
      body: { blogPost }
    });
    await refreshApp();
    closeBlogEditor();
  } catch (error) {
    window.alert(`블로그 저장 실패: ${error.message}`);
  }
}

async function deleteBlogPost(blogId) {
  const post = findBlogPost(blogId);
  if (!post) return;
  const confirmed = window.confirm(`${post.title} 글을 삭제할까요?`);
  if (!confirmed) return;

  try {
    await api(`/api/blog/${encodeURIComponent(blogId)}`, { method: "DELETE" });
    if (state.currentBlogId === blogId) {
      closeBlogDetail();
    }
    await refreshApp();
  } catch (error) {
    window.alert(`블로그 삭제 실패: ${error.message}`);
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
    if (state.filters.category !== "all" && getProjectCategory(project) !== state.filters.category) {
      return false;
    }
    if (!state.filters.query) {
      return true;
    }
    const haystack = [
      project.name,
      project.summary,
      project.category,
      getProjectCategory(project),
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

function findBlogPost(blogId) {
  return arrayOrEmpty(state.bootstrap.blogPosts).find((post) => post.id === blogId);
}

function computeStats(projects) {
  return {
    total: projects.length,
    inProgress: projects.filter((project) => project.status === "in-progress").length,
    active: projects.filter((project) => project.status === "active").length,
    categories: new Set(projects.map((project) => getProjectCategory(project))).size
  };
}

function getProjectCategory(project) {
  const raw = String(project?.category || "").trim();
  const matched = CATEGORY_GROUPS.find((group) => group.match.includes(raw));
  return matched ? matched.label : raw || "General";
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

function splitTimelineWindows(value) {
  return splitLines(value).map((line) => {
    const [label, start, end, severity] = line.split("|");
    return {
      label: (label || "").trim(),
      start: (start || "").trim(),
      end: (end || "").trim(),
      severity: (severity || "").trim().toLowerCase() || "medium"
    };
  });
}

function splitTimelineMilestones(value) {
  return splitLines(value).map((line) => {
    const [label, date, tone] = line.split("|");
    return {
      label: (label || "").trim(),
      date: (date || "").trim(),
      tone: (tone || "").trim().toLowerCase() || "neutral"
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

function renderMarkdown(value) {
  const source = String(value || "").replace(/\r/g, "");
  if (!source.trim()) {
    return `<p>아직 본문이 없습니다.</p>`;
  }

  const codeBlocks = [];
  let text = escapeHtml(source).replace(/```([\s\S]*?)```/g, (_match, code) => {
    const token = `__CODE_BLOCK_${codeBlocks.length}__`;
    codeBlocks.push(`<pre><code>${code.trim()}</code></pre>`);
    return token;
  });

  const lines = text.split("\n");
  const html = [];
  let listBuffer = [];

  const flushList = () => {
    if (!listBuffer.length) return;
    html.push(`<ul>${listBuffer.join("")}</ul>`);
    listBuffer = [];
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }
    if (/^__CODE_BLOCK_\d+__$/.test(trimmed)) {
      flushList();
      html.push(trimmed);
      return;
    }
    const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      flushList();
      const level = Math.min(4, headingMatch[1].length);
      html.push(`<h${level}>${renderMarkdownInline(headingMatch[2])}</h${level}>`);
      return;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      listBuffer.push(`<li>${renderMarkdownInline(trimmed.replace(/^[-*]\s+/, ""))}</li>`);
      return;
    }
    if (/^>\s+/.test(trimmed)) {
      flushList();
      html.push(`<blockquote>${renderMarkdownInline(trimmed.replace(/^>\s+/, ""))}</blockquote>`);
      return;
    }
    flushList();
    html.push(`<p>${renderMarkdownInline(trimmed)}</p>`);
  });

  flushList();
  return html
    .join("")
    .replace(/__CODE_BLOCK_(\d+)__/g, (_match, index) => codeBlocks[Number(index)] || "");
}

function renderMarkdownInline(value) {
  return String(value || "")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>');
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

function formatBlogDate(value) {
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      dateStyle: "long"
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
