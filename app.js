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
  currentTimelineMonthKey: null,
  currentBlogId: null,
  commentsByProject: new Map(),
  blogCommentsByPost: new Map(),
  trackedProjects: new Set(),
  carouselStartIndex: 0
};

const elements = {
  cursorHalo: document.getElementById("cursor-halo"),
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
  aboutContactList: document.getElementById("about-contact-list"),
  aboutMetrics: document.getElementById("about-metrics"),
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
  projectCarouselPrev: document.getElementById("project-carousel-prev"),
  projectCarouselNext: document.getElementById("project-carousel-next"),
  projectCarouselShell: document.querySelector(".project-carousel-shell"),
  projectGrid: document.getElementById("project-grid"),
  timelineLegend: document.getElementById("timeline-legend"),
  projectTimelineMap: document.getElementById("project-timeline-map"),
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
  "central-memory-prompt-kit": "Central Memory Prompt Kit",
  "morpheme-analysis-notebook": "말버릇을 쪼개보는 형태소 분석 노트",
  "mood-tracker": "감정의 흐름을 기록하는 무드 트래커",
  "260218-ope-log-anlayze": "로그 속 숨은 운영 이슈를 건져낸 분석기",
  "260315-moe-prompt-routing": "질문마다 맞는 프롬프트를 고르는 라우팅 엔진",
  "dowon-codex-manager-memory-work-summary-v4": "에이전트 작업기억을 한 장으로 묶는 실험",
  "gemini-multiturn-tester-v3": "멀티턴 LLM을 끝까지 흔드는 테스트 벤치",
  "a2a-family-classifier-experts": "Agent-to-Agent로 가기 위한 1차 분류기와 Expert 묶음",
  "operation-log-analyzer": "운영 로그에서 원인을 역추적하는 워크벤치",
  "project-naming-rule": "이름이 인상을 바꾸는 프로젝트 네이밍 룰",
  "prompt-auto-evaluation": "프롬프트 승자를 자동으로 가려내는 평가 파이프라인",
  "scripts": "반복 작업을 덜어주는 자동화 툴박스",
  "semantic-verb-schema": "한국어 동사를 기능 스키마로 재구성한 실험",
  "260317-desktop-scheduler": "바탕화면에서 바로 쓰는 데스크 스케줄러",
  "personal-essay-writer-ko": "감정을 글로 쓰는 에세이 라이터 스킬",
  "todack": "토닥, 감정을 다루는 작은 회복 인터페이스",
  "work-summary-versions": "일의 흔적을 버전으로 축적한 아카이브",
  "utterance-similarity-notebook": "비슷한 발화의 차이를 잡아내는 분석 노트"
};

const PROJECT_LINK_OVERRIDES = {
  "execution-harness-system": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260331_execution-harness-system"
    }
  ],
  "central-memory-prompt-kit": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260324_central_memory_prompt_kit"
    }
  ],
  "calc-stt-cer-colab": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/computing-Korean-STT-error-rates"
    },
    {
      label: "Colab",
      url: "https://colab.research.google.com/drive/1OHqEr4OaIbO67_xJQc8KYXb91wwUoDIz"
    }
  ],
  "morpheme-analysis-notebook": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/250731-morphology-utterance-similarity-analysis"
    }
  ],
  "utterance-similarity-notebook": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/250731-morphology-utterance-similarity-analysis"
    }
  ],
  "mood-tracker": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260212_feeling_traker"
    }
  ],
  "260218-ope-log-anlayze": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260218_ope_log_anlayze"
    }
  ],
  "260315-moe-prompt-routing": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260315-moe-prompt-routing-a2a"
    }
  ],
  "260317-desktop-scheduler": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260317_desktop_scheduler"
    }
  ],
  "gemini-multiturn-tester-v3": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260210_gemini_multiturn_tester_v3"
    }
  ],
  "operation-log-analyzer": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/251231_operation_log_analayzer"
    }
  ],
  "prompt-auto-evaluation": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/251104_prompt_auto_evaluation"
    }
  ],
  "semantic-verb-schema": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/251028_semantic_verb_schema"
    }
  ],
  "a2a-family-classifier-experts": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260315-moe-prompt-routing-a2a"
    }
  ],
  "260319-llm-tool-hub": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260319_llm_tool_hub"
    }
  ],
  "260321-memento-mori-archive": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260321_memento_mori_archive"
    }
  ],
  "dowon-codex-manager-memory-work-summary-v4": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260324_central_memory_prompt_kit"
    }
  ],
  "wine-cellar-scan": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260401-wine-cellar-scan"
    }
  ],
  "ideal-type-editorial": [
    {
      label: "GitHub",
      url: "https://github.com/Dohwon/260408_ideal_type_editorial"
    }
  ],
  "todack": [
  ],
  "personal-essay-writer-ko": [
  ]
};

const PROJECT_AUTO_LINK_BLOCKLIST = new Set([
  "project-naming-rule",
  "scripts",
  "work-summary-versions"
]);

const PROJECT_START_DATE_OVERRIDES = {
  "utterance-similarity-notebook": "2025-07-31",
  "morpheme-analysis-notebook": "2025-07-31",
  "semantic-verb-schema": "2025-10-28",
  "prompt-auto-evaluation": "2025-11-04",
  "operation-log-analyzer": "2025-12-31",
  "gemini-multiturn-tester-v3": "2026-02-10",
  "mood-tracker": "2026-02-12",
  "calc-stt-cer-colab": "2026-02-18",
  "project-naming-rule": "2026-02-28",
  "scripts": "2026-03-05",
  "work-summary-versions": "2026-03-10",
  "dowon-codex-manager-memory-work-summary-v4": "2026-03-24",
  "a2a-family-classifier-experts": "2026-03-15"
};

const DEFAULT_PROJECT_GITHUB_ROOT = "https://github.com/Dohwon/AI-Agent-Project";
const DEFAULT_PUBLIC_EMAIL = "dowonkim0612@naver.com";
const DEFAULT_PROFILE_GITHUB = "https://github.com/Dohwon";

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
    value: "56.24% → 74.22%",
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

const BLOG_EDITORIAL_OVERRIDES = {
  "stitch-figma-codex-design-workflow": {
    noteLabel: "Design In Progress",
    leadNote:
      "AI로 디자인 시스템을 구축하는 방법을 아직 찾아가는 중이다. Stitch로 화면의 첫 감을 잡고, Figma로 구조를 다듬고, Codex로 실제 서비스까지 연결하면서 개발자이던 내 역할은 디자이너의 영역까지 조금씩 넓어지고 있다."
  },
  "why-i-built-this-homepage": {
    noteLabel: "Working Archive",
    leadNote:
      "흩어진 프로젝트를 단순 전시가 아니라 작업 방식까지 읽히는 라이브러리로 다시 묶는 실험이다. 결국 이 사이트는 소개 페이지보다, 내가 문제를 다루는 방식을 남기는 기록 쪽에 가깝다."
  }
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

window.addEventListener(
  "load",
  () => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  },
  { once: true }
);

async function init() {
  window.history.scrollRestoration = "manual";
  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  bindEvents();
  await refreshApp();
  void recordVisit("home");
}

function bindEvents() {
  bindDecorativeMotion();
  bindRailNavigation();

  elements.searchInput.addEventListener("input", () => {
    state.filters.query = elements.searchInput.value.trim().toLowerCase();
    state.carouselStartIndex = 0;
    renderProjects();
  });

  elements.searchReset.addEventListener("click", () => {
    elements.searchInput.value = "";
    state.filters.query = "";
    state.carouselStartIndex = 0;
    renderProjects();
  });

  elements.statusFilters.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-status-filter]");
    if (!chip) return;
    state.filters.status = chip.dataset.statusFilter;
    state.carouselStartIndex = 0;
    renderFilters();
    renderProjects();
  });

  elements.categoryFilters.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-category-filter]");
    if (!chip) return;
    state.filters.category = chip.dataset.categoryFilter;
    state.carouselStartIndex = 0;
    renderFilters();
    renderProjects();
  });

  elements.projectCarouselPrev?.addEventListener("click", () => {
    scrollProjectCarousel(-1);
  });

  elements.projectCarouselNext?.addEventListener("click", () => {
    scrollProjectCarousel(1);
  });

  elements.projectGrid?.addEventListener(
    "wheel",
    (event) => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      if (elements.projectGrid.scrollWidth <= elements.projectGrid.clientWidth + 4) return;
      const nextLeft = elements.projectGrid.scrollLeft + event.deltaY;
      const maxLeft = elements.projectGrid.scrollWidth - elements.projectGrid.clientWidth;
      if (nextLeft < -4) {
        bumpProjectRail("left");
      } else if (nextLeft > maxLeft + 4) {
        bumpProjectRail("right");
      }
      event.preventDefault();
      elements.projectGrid.scrollBy({ left: event.deltaY, behavior: "auto" });
      syncProjectCarouselControls();
    },
    { passive: false }
  );

  elements.projectGrid?.addEventListener("scroll", () => {
    syncProjectCarouselControls();
  });

  window.addEventListener("resize", () => {
    syncProjectCarouselControls();
  });

  elements.projectGrid.addEventListener("click", (event) => {
    if (event.target.closest("a[href]")) {
      return;
    }
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
      if (actionButton.dataset.cardAction === "move-left") {
        void reorderProject(projectId, -1);
      }
      if (actionButton.dataset.cardAction === "move-right") {
        void reorderProject(projectId, 1);
      }
      if (actionButton.dataset.cardAction === "pin") {
        void toggleProjectPin(projectId);
      }
      return;
    }

    const card = event.target.closest(".project-card");
    if (!card) return;
    openDetail(card.dataset.projectId);
  });

  elements.projectGrid.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest("[data-card-action], a[href], button")) return;
    const card = event.target.closest(".project-card");
    if (!card) return;
    event.preventDefault();
    openDetail(card.dataset.projectId);
  });

  elements.projectTimelineMap.addEventListener("click", (event) => {
    const calendarAction = event.target.closest("[data-calendar-action]");
    if (calendarAction) {
      const groups = groupTimelineEntriesByMonth(
        getTimelineProjects()
          .map((project) => ({ project, start: getProjectStartDate(project) }))
          .sort((left, right) => left.start.getTime() - right.start.getTime())
      );
      if (!groups.length) return;
      const currentIndex = Math.max(0, groups.findIndex((group) => group.key === state.currentTimelineMonthKey));
      if (calendarAction.dataset.calendarAction === "prev-month") {
        const nextIndex = (currentIndex - 1 + groups.length) % groups.length;
        state.currentTimelineMonthKey = groups[nextIndex].key;
        renderProjectTimeline();
      }
      if (calendarAction.dataset.calendarAction === "next-month") {
        const nextIndex = (currentIndex + 1) % groups.length;
        state.currentTimelineMonthKey = groups[nextIndex].key;
        renderProjectTimeline();
      }
      return;
    }

    const calendarMonth = event.target.closest("[data-calendar-month]");
    if (calendarMonth) {
      state.currentTimelineMonthKey = calendarMonth.dataset.calendarMonth;
      renderProjectTimeline();
      return;
    }

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

  elements.projectTimelineMap.addEventListener("change", (event) => {
    const select = event.target.closest("[data-calendar-select]");
    if (!select) return;
    const groups = groupTimelineEntriesByMonth(
      getTimelineProjects()
        .map((project) => ({ project, start: getProjectStartDate(project) }))
        .sort((left, right) => left.start.getTime() - right.start.getTime())
    );
    if (!groups.length) return;

    const activeMonth = groups.find((group) => group.key === state.currentTimelineMonthKey) || groups.at(-1);
    const nextYear = select.dataset.calendarSelect === "year" ? Number(select.value) : activeMonth?.year;
    const nextMonth = select.dataset.calendarSelect === "month" ? Number(select.value) : activeMonth?.month;
    const matched = groups.find((group) => group.year === nextYear && group.month === nextMonth)
      || groups.find((group) => group.year === nextYear)
      || activeMonth;
    state.currentTimelineMonthKey = matched?.key || null;
    renderProjectTimeline();
  });

  elements.caseGrid?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-case-project]");
    if (!chip) return;
    openDetail(chip.dataset.caseProject);
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

    const navButton = event.target.closest("[data-blog-nav]");
    if (navButton) {
      const targetId = navButton.dataset.blogId;
      if (targetId) {
        openBlogDetail(targetId);
      }
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

  elements.blogModalBody?.addEventListener("submit", (event) => {
    if (event.target.matches("#blog-comment-form")) {
      event.preventDefault();
      void submitBlogComment();
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

function bindDecorativeMotion() {
  if (!elements.cursorHalo || !window.matchMedia("(pointer:fine)").matches) return;

  let fadeTimer = null;
  document.addEventListener("pointermove", (event) => {
    elements.cursorHalo.style.opacity = "1";
    elements.cursorHalo.style.transform = `translate3d(${event.clientX}px, ${event.clientY}px, 0)`;
    if (fadeTimer) {
      window.clearTimeout(fadeTimer);
    }
    fadeTimer = window.setTimeout(() => {
      elements.cursorHalo.style.opacity = "0.28";
    }, 180);
  });

  document.addEventListener("pointerleave", () => {
    elements.cursorHalo.style.opacity = "0";
  });
}

async function refreshApp() {
  state.bootstrap = await api("/api/bootstrap");
  const timelineProjects = getTimelineProjects();
  const timelineMonthGroups = groupTimelineEntriesByMonth(
    timelineProjects
      .map((project) => ({
        project,
        start: getProjectStartDate(project)
      }))
      .sort((left, right) => left.start.getTime() - right.start.getTime())
  );
  if (!findProject(state.currentTimelineProjectId)) {
    state.currentTimelineProjectId = timelineProjects[0]?.id || null;
  }
  if (!timelineMonthGroups.some((group) => group.key === state.currentTimelineMonthKey)) {
    state.currentTimelineMonthKey = timelineMonthGroups.at(-1)?.key || null;
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

  elements.heroBadge.textContent = "";
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
  const categories = [
    "all",
    ...[...new Set(state.bootstrap.projects.map((project) => getProjectCategory(project)))].sort((left, right) =>
      String(left).localeCompare(String(right), "ko")
    )
  ];
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
  const owner = state.bootstrap.owner || {};
  const links = state.bootstrap.links || {};
  const profile = state.bootstrap.profile || {};
  const aboutSignature = buildAboutSignature();
  const valueProps = getAboutValueProps(profile);
  const aboutMetrics = getAboutMetrics(profile);
  const aboutContacts = buildAboutContacts(owner, links);

  elements.aboutTitle.textContent = aboutSignature.title;
  elements.ownerSummary.textContent = aboutSignature.summary;
  elements.valueProps.innerHTML = valueProps
    .map((item) => `<article class="value-card">${escapeHtml(item)}</article>`)
    .join("");
  if (elements.aboutContactList) {
    elements.aboutContactList.innerHTML = aboutContacts.map(renderAboutContactCard).join("");
  }

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
}

function renderCareerTimeline() {
  const profile = state.bootstrap.profile || {};
  const timeline = arrayOrEmpty(profile.careerTimeline)
    .map(
      (item) => `
        <article class="career-wide-item">
          <span class="career-wide-dot"></span>
          <div class="career-wide-period">${escapeHtml(item.period || "")}</div>
          <div class="career-wide-card">
            <div class="career-title-row">
              <div>
                <h3>${escapeHtml(item.company || "")}</h3>
                <p class="career-role">${escapeHtml(item.role || "")}</p>
              </div>
              <span class="career-index">${escapeHtml(buildCareerIndexLabel(item))}</span>
            </div>
            <p class="timeline-copy">${escapeHtml(item.summary || "")}</p>
            <div class="career-proof-row">
              ${buildCareerHighlights(item).map((tag) => `<span class="career-proof-pill">${escapeHtml(tag)}</span>`).join("")}
            </div>
          </div>
        </article>
      `
    )
    .join("");

  elements.careerTimeline.innerHTML = `
    <div class="career-wide-track">${timeline}</div>
  `;
}

function renderProjectTimeline() {
  const projects = getTimelineProjects();
  if (!projects.length) {
    elements.timelineLegend.innerHTML = "";
    elements.projectTimelineMap.innerHTML = `<article class="empty-state">타임라인 데이터가 없습니다.</article>`;
    return;
  }

  elements.timelineLegend.innerHTML = `
    <span class="timeline-legend-pill"><i class="legend-dot active"></i>작업 시작일</span>
    <span class="timeline-legend-pill"><i class="legend-dot milestone"></i>완료/운영</span>
    <span class="timeline-legend-pill"><i class="legend-dot difficulty"></i>진행중</span>
  `;

  const entries = projects
    .map((project) => ({
      project,
      start: getProjectStartDate(project)
    }))
    .sort((left, right) => left.start.getTime() - right.start.getTime());

  const monthGroups = groupTimelineEntriesByMonth(entries);
  const activeMonth = monthGroups.find((group) => group.key === state.currentTimelineMonthKey) || monthGroups.at(-1);
  state.currentTimelineMonthKey = activeMonth?.key || null;

  elements.projectTimelineMap.innerHTML = renderProjectCalendar(monthGroups, activeMonth);
}

function getProjectStartDate(project) {
  return (
    parseTimelineDate(project.timeline?.start) ||
    parseTimelineDate(PROJECT_START_DATE_OVERRIDES[project.id]) ||
    parseTimelineDate(project.createdAt) ||
    new Date()
  );
}

function renderProjectCalendar(groups, activeMonth) {
  const years = [...new Set(groups.map((group) => group.year))].sort((left, right) => left - right);
  const months = groups
    .filter((group) => group.year === activeMonth?.year)
    .map((group) => group.month)
    .sort((left, right) => left - right);
  return `
    <div class="project-calendar-shell">
      <div class="project-calendar-toolbar">
        <button type="button" class="ghost-button compact" data-calendar-action="prev-month">‹</button>
        <div class="project-calendar-selects">
          <label class="project-calendar-select-wrap">
            <span>연도</span>
            <select data-calendar-select="year">
              ${years
                .map(
                  (year) => `
                    <option value="${escapeHtml(String(year))}" ${year === activeMonth?.year ? "selected" : ""}>
                      ${escapeHtml(String(year))}
                    </option>
                  `
                )
                .join("")}
            </select>
          </label>
          <label class="project-calendar-select-wrap">
            <span>월</span>
            <select data-calendar-select="month">
              ${months
                .map(
                  (month) => `
                    <option value="${escapeHtml(String(month))}" ${month === activeMonth?.month ? "selected" : ""}>
                      ${escapeHtml(String(month).padStart(2, "0"))}
                    </option>
                  `
                )
                .join("")}
            </select>
          </label>
        </div>
        <button type="button" class="ghost-button compact" data-calendar-action="next-month">›</button>
      </div>
      ${activeMonth ? renderProjectCalendarMonth(activeMonth) : ""}
    </div>
  `;
}

function groupTimelineEntriesByMonth(entries) {
  const grouped = new Map();

  entries.forEach((entry) => {
    const monthKey = `${entry.start.getFullYear()}-${String(entry.start.getMonth() + 1).padStart(2, "0")}`;
    if (!grouped.has(monthKey)) {
      grouped.set(monthKey, []);
    }
    grouped.get(monthKey).push(entry);
  });

  return [...grouped.entries()].map(([key, items]) => {
    const [year, month] = key.split("-").map(Number);
    return {
      key,
      year,
      month,
      items: items.sort((left, right) => left.start.getDate() - right.start.getDate())
    };
  });
}

function renderProjectCalendarMonth(group) {
  const firstDay = new Date(group.year, group.month - 1, 1);
  const lastDate = new Date(group.year, group.month, 0).getDate();
  const offset = (firstDay.getDay() + 6) % 7;
  const cells = [];

  for (let index = 0; index < offset; index += 1) {
    cells.push(`<div class="project-calendar-cell empty" aria-hidden="true"></div>`);
  }

  for (let day = 1; day <= lastDate; day += 1) {
    const items = group.items.filter((entry) => entry.start.getDate() === day);
    cells.push(renderProjectCalendarCell(group, day, items));
  }

  return `
    <article class="project-calendar-month">
      <div class="project-calendar-month-head">
        <p class="panel-kicker">Start Calendar</p>
        <h3>${escapeHtml(`${group.year}.${String(group.month).padStart(2, "0")}`)}</h3>
      </div>
      <div class="project-calendar-weekdays">
        <span>월</span>
        <span>화</span>
        <span>수</span>
        <span>목</span>
        <span>금</span>
        <span>토</span>
        <span>일</span>
      </div>
      <div class="project-calendar-grid">
        ${cells.join("")}
      </div>
    </article>
  `;
}

function renderProjectCalendarCell(group, day, entries) {
  const hasEntries = entries.length > 0;
  return `
    <div class="project-calendar-cell ${hasEntries ? "filled" : ""}">
      <span class="project-calendar-date">${escapeHtml(String(day))}</span>
      <div class="project-calendar-events">
        ${entries
          .map(
            (entry) => `
              <button
                type="button"
                class="project-calendar-chip ${entry.project.status === "in-progress" ? "warning" : "success"}"
                data-timeline-project="${escapeHtml(entry.project.id)}"
                title="${escapeHtml(getProjectDisplayName(entry.project))}"
              >
                ${escapeHtml(truncate(getProjectDisplayName(entry.project), 22))}
              </button>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderTimelineChronicle(entries) {
  const range = buildTimelineRange(entries);
  const width = Math.max(1480, entries.length * 164);
  const height = 430;
  const wavePoints = buildTimelineWavePoints(entries, range, width, height);
  const wavePath = buildSmoothPath(wavePoints);
  const areaPath = `${wavePath} L ${width - 52} ${height - 50} L 52 ${height - 50} Z`;
  const labelIndexes = range.labels
    .map((label, index) => ({ label, index }))
    .filter(({ index }) => index === 0 || index === range.labels.length - 1 || index % 2 === 0);

  return `
    <div class="timeline-wave-shell">
      <div class="timeline-wave-scroll">
        <div class="timeline-wave-board" style="width:${width}px; height:${height}px;">
          <svg class="timeline-wave-bg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
            <path class="timeline-wave-axis-line" d="M 52 ${height - 50} H ${width - 52}"></path>
            <path class="timeline-wave-area" d="${areaPath}"></path>
            <path class="timeline-wave-line" d="${wavePath}"></path>
          </svg>
          <div class="timeline-wave-axis">
            ${labelIndexes
              .map(({ label }) => {
                const ratio = graphRatio(label, range.start, range.end, 0.08, 0.92);
                return `<span style="left:${(ratio * width).toFixed(1)}px;">${escapeHtml(label.toISOString().slice(0, 7).replace("-", "."))}</span>`;
              })
              .join("")}
          </div>
          <div class="timeline-wave-events">
            ${entries.map((entry, index) => renderTimelineWaveEvent(entry, index, entries, range, width, height)).join("")}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderTimelineWaveEvent(entry, index, entries, range, width, height) {
  const ratio = graphRatio(entry.start, range.start, range.end, 0.08, 0.92);
  const x = ratio * width;
  const y = computeTimelineWaveY(ratio, entries, range, height);
  const direction = index % 2 === 0 ? "above" : "below";
  const cardTop = clampNumber(direction === "above" ? y - 150 : y + 36, 22, height - 148);
  const difficultyCopy = entry.difficulties[0]?.label || "핵심 이슈";
  const summaryCopy = arrayOrEmpty(entry.story.impact)[0] || entry.story.challenge || entry.project.summary;
  return `
    <button
      type="button"
      class="timeline-wave-event ${direction} ${entry.project.status === "in-progress" ? "warning" : "success"}"
      style="left:${x.toFixed(1)}px; top:${cardTop.toFixed(1)}px;"
      data-timeline-project="${escapeHtml(entry.project.id)}"
    >
      <span class="timeline-wave-date">${escapeHtml(entry.label)}</span>
      <strong>${escapeHtml(getProjectDisplayName(entry.project))}</strong>
      <span class="timeline-wave-copy">${escapeHtml(truncate(summaryCopy, 54))}</span>
      <span class="timeline-wave-foot">
        <span class="timeline-wave-chip ${entry.project.status === "in-progress" ? "warning" : "success"}">
          ${entry.project.status === "in-progress" ? "진행중" : "완료/운영"}
        </span>
        <span class="timeline-wave-chip subtle">${escapeHtml(truncate(difficultyCopy, 20))}</span>
      </span>
      <span class="timeline-wave-node"></span>
    </button>
  `;
}

function buildTimelineWavePoints(entries, range, width, height) {
  const points = [];
  for (let index = 0; index <= 72; index += 1) {
    const ratio = 0.08 + 0.84 * (index / 72);
    points.push({
      x: ratio * width,
      y: computeTimelineWaveY(ratio, entries, range, height)
    });
  }
  return points;
}

function computeTimelineWaveY(ratio, entries, range, height) {
  const baseY = height * 0.57;
  let y = baseY + Math.sin(ratio * Math.PI * 3.4) * 18;

  entries.forEach((entry, index) => {
    const entryRatio = graphRatio(entry.start, range.start, range.end, 0.08, 0.92);
    const distance = Math.abs(ratio - entryRatio);
    const severity =
      entry.difficulties.some((item) => item.severity === "high")
        ? 1.45
        : entry.difficulties.length
          ? 1.08
          : 0.82;
    const influence = Math.exp(-((distance * distance) / 0.0017));
    y -= influence * (22 * severity);
    y += Math.sin((ratio + index * 0.06) * Math.PI * 4.2) * influence * 4;
  });

  return clampNumber(y, height * 0.3, height * 0.74);
}

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function renderJourneyGraph(entry) {
  const width = 320;
  const height = 132;
  const points = buildJourneyGraphPoints(entry, width, height);
  const linePath = buildSmoothPath(points);
  const areaPath = `${linePath} L ${width - 14} ${height - 14} L 14 ${height - 14} Z`;
  const milestones = entry.milestones
    .slice(0, 3)
    .map((item) => {
      const x = graphRatio(item.date, entry.start, entry.end, 0.14, 0.9) * width;
      return `<circle class="journey-graph-marker ${escapeHtml(item.tone)}" cx="${x.toFixed(1)}" cy="102" r="5"></circle>`;
    })
    .join("");

  return `
    <svg class="journey-graph" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
      <path class="journey-graph-baseline" d="M 14 ${height - 14} H ${width - 14}"></path>
      <path class="journey-graph-area" d="${areaPath}"></path>
      <path class="journey-graph-line" d="${linePath}"></path>
      ${points
        .slice(1, -1)
        .map((point) => `<circle class="journey-graph-peak" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="5"></circle>`)
        .join("")}
      ${milestones}
    </svg>
  `;
}

function buildJourneyGraphPoints(entry, width, height) {
  const baseY = height - 30;
  const points = [{ x: 14, y: baseY - 6 }];

  arrayOrEmpty(entry.difficulties).forEach((item, index) => {
    const severityDepth = item.severity === "high" ? 58 : item.severity === "low" ? 24 : 40;
    const midpoint = new Date((item.start.getTime() + item.end.getTime()) / 2);
    const x = graphRatio(midpoint, entry.start, entry.end, 0.18, 0.86) * width;
    const y = Math.max(18, baseY - severityDepth - index * 4);
    points.push({ x, y });
  });

  if (points.length === 1) {
    points.push({ x: width * 0.42, y: baseY - (entry.project.status === "in-progress" ? 42 : 28) });
    points.push({ x: width * 0.72, y: baseY - 18 });
  }

  points.push({ x: width - 14, y: entry.project.status === "in-progress" ? baseY - 18 : baseY - 10 });
  return points.sort((left, right) => left.x - right.x);
}

function buildSmoothPath(points) {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  let pathData = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const curr = points[index];
    const midX = ((prev.x + curr.x) / 2).toFixed(1);
    pathData += ` Q ${midX} ${prev.y.toFixed(1)} ${curr.x.toFixed(1)} ${curr.y.toFixed(1)}`;
  }
  return pathData;
}

function graphRatio(date, start, end, min = 0, max = 1) {
  const total = Math.max(1, end.getTime() - start.getTime());
  const raw = (date.getTime() - start.getTime()) / total;
  const clamped = Math.min(1, Math.max(0, raw));
  return min + (max - min) * clamped;
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
  const cases = arrayOrEmpty(state.bootstrap.cases).slice(0, 3);
  elements.caseGrid.innerHTML = cases.length
    ? cases
        .map(
          (item) => {
            const relatedProjects = getCaseRelatedProjects(item);
            return `
            <article class="case-card">
              <div class="case-head">
                <h3>${escapeHtml(item.title || "")}</h3>
                <span class="case-badge">Solved</span>
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
              <div class="case-related-row">
                <strong>관련 프로젝트</strong>
                <div class="case-related-pills">
                  ${relatedProjects.length
                    ? relatedProjects
                        .map(
                          (project) => `
                            <button type="button" class="case-project-pill" data-case-project="${escapeHtml(project.id)}">
                              ${escapeHtml(getProjectDisplayName(project))}
                            </button>
                          `
                        )
                        .join("")
                    : `<span class="case-project-pill muted">연결 프로젝트 정리중</span>`}
                </div>
              </div>
            </article>
          `;
          }
        )
        .join("")
    : `<article class="empty-state">문제 해결 사례 데이터가 없습니다.</article>`;
}

function getCaseRelatedProjects(item) {
  const explicitIds = new Set(arrayOrEmpty(item.relatedProjectIds));
  const matched = state.bootstrap.projects.filter((project) => {
    if (explicitIds.has(project.id)) {
      return true;
    }
    return getRelatedCases(project).some((candidate) => candidate.id === item.id);
  });

  return matched.slice(0, 4);
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
              <strong>${escapeHtml(truncate(story.resolution || buildDerivedResolution(project) || project.summary, 70))}</strong>
            </article>
          </div>
        </section>
      </div>
    </div>
  `;
}

function buildAboutSignature() {
  return {
    title: "복잡한 AI 문제를 구조화해 팀이 움직이게 만드는 Product Builder",
    summary:
      "흐릿한 이슈를 그냥 감으로 넘기지 않고, 제품·운영·정책이 바로 움직일 수 있는 구조로 번역해 끝까지 밀어붙입니다. 로그, 룰베이스, 사용자 흐름, 품질 기준이 뒤엉킨 문제를 빠르게 쪼개고 실제 개선으로 닫는 실행형 빌더입니다."
  };
}

function buildAboutContacts(owner = {}, links = {}) {
  const email = String(owner.publicEmail || owner.email || DEFAULT_PUBLIC_EMAIL).trim();
  const notion = String(links.notion || state.bootstrap?.site?.externalLink || "").trim();
  const github = String(links.github || DEFAULT_PROFILE_GITHUB).trim();
  const roleCopy = String(owner.headline || "AI Product / LLM PM").split("|")[0].trim();

  return [
    {
      label: "Name",
      value: owner.name || "김도원",
      note: roleCopy
    },
    email
      ? {
          label: "Email",
          value: email,
          note: "문의 및 협업 연락",
          href: `mailto:${email}`
        }
      : null,
    notion
      ? {
          label: "Notion",
          value: "Portfolio Notes",
          note: "경력과 프로젝트 문서",
          href: notion
        }
      : null,
    github
      ? {
          label: "GitHub",
          value: github.replace(/^https?:\/\//, ""),
          note: "실험 코드와 노트북",
          href: github
        }
      : null
  ].filter(Boolean);
}

function renderAboutContactCard(item) {
  const tagName = item.href ? "a" : "article";
  const isLink = Boolean(item.href);
  const attrs = item.href
    ? ` class="about-contact-card is-link" href="${escapeHtml(item.href)}" target="_blank" rel="noreferrer noopener"`
    : ` class="about-contact-card"`;

  return `
    <${tagName}${attrs}>
      <div class="about-contact-top">
        <small>${escapeHtml(item.label || "")}</small>
        ${isLink ? `<span class="about-contact-open">LINK</span>` : ""}
      </div>
      <strong>${escapeHtml(item.value || "")}</strong>
      ${item.note ? `<span>${escapeHtml(item.note)}</span>` : ""}
    </${tagName}>
  `;
}

function getAboutValueProps(profile) {
  const values = arrayOrEmpty(profile.valueProposition);
  return values.length ? values : ABOUT_VALUE_PROPS;
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
    resolution: explicitStory.resolution || primaryCase?.result || buildDerivedResolution(project) || project.summary,
    impact: arrayOrEmpty(explicitStory.impact).length ? explicitStory.impact : arrayOrEmpty(project.highlights),
    caseIds: arrayOrEmpty(explicitStory.caseIds),
    relatedCases
  };
}

function buildDerivedResolution(project) {
  const notes = buildProjectNotes(project, null, null);
  return notes[notes.length - 1] || project.summary;
}

function buildProjectNotes(project, story = null, timelineEntry = null) {
  const resolvedStory = story || {
    challenge: project.story?.challenge || project.summary,
    resolution: project.story?.resolution || project.summary
  };
  const resolvedTimeline = timelineEntry || {
    label: project.timeline?.label || ""
  };
  const explicitNotes = arrayOrEmpty(project.detail?.readmeSummary).filter((line) => !isBoilerplateNote(line));
  const derivedNotes = [
    `이 프로젝트는 ${project.summary}`,
    buildEvidenceNote(project),
    resolvedStory.challenge ? `실제로 가장 크게 걸렸던 지점은 ${resolvedStory.challenge}` : "",
    resolvedStory.resolution ? `결과적으로 ${resolvedStory.resolution}` : "",
    resolvedTimeline?.label && !resolvedTimeline.label.includes("기간 입력 필요")
      ? `작업 흐름은 ${resolvedTimeline.label} 사이클로 이어졌고, 난관과 해결 시점을 타임라인에서 함께 읽을 수 있게 정리했다.`
      : ""
  ].filter(Boolean);

  return [...new Set([...explicitNotes, ...derivedNotes])].slice(0, 4);
}

function buildEvidenceNote(project) {
  const files = arrayOrEmpty(project.detail?.keyFiles).map((item) => item.toLowerCase());
  if (!files.length) {
    return "아이디어를 던지고 끝낸 작업이 아니라, 실제로 굴러가는 흐름과 결과물을 남기기 위해 끝까지 밀어붙인 프로젝트다.";
  }
  if (files.some((item) => item.endsWith(".ipynb"))) {
    return "탐색형 실험을 여러 번 돌리며 패턴을 찾고, 그 결과를 바로 개선 포인트와 판단 근거로 연결한 프로젝트다.";
  }
  if (files.some((item) => item.includes("judge") || item.includes("eval") || item.includes("workbook") || item.includes("xlsx"))) {
    return "한 번 데모로 끝낸 게 아니라, 회귀 검증과 비교 실험까지 돌려서 정답률과 품질을 계속 밀어올리려 한 프로젝트다.";
  }
  if (files.some((item) => item.includes("schema") || item.includes("corpus") || item.endsWith(".yaml") || item.endsWith(".yml"))) {
    return "기능을 감으로 붙인 게 아니라, 스키마와 사전 수준부터 다시 설계해서 규칙과 품질 기준을 함께 세운 프로젝트다.";
  }
  if (files.some((item) => item.includes("log") || item.includes("analytics") || item.includes("report"))) {
    return "로그를 읽고 끝낸 분석이 아니라, raw 데이터를 바로 개선 backlog와 운영 판단으로 이어붙이기 위해 만든 작업이다.";
  }
  if (files.some((item) => item.includes("server") || item.includes("app") || item.includes("run") || item.includes("cli"))) {
    return "실행과 운영까지 닿게 만드는 데 초점이 있어서, 아이디어 설명보다 실제 반복 실행과 유지 흐름이 더 강하게 남는 프로젝트다.";
  }
  return "핵심 흐름을 작은 단계로 쪼개 검증하면서 결과를 쌓아 올린, 시행착오가 그대로 자산으로 남는 프로젝트다.";
}

function isBoilerplateNote(line) {
  const text = String(line || "").trim();
  return (
    !text ||
    text.includes("README가 없어 파일/코드 구조 기반으로 요약했습니다.") ||
    text.includes("원본 프로젝트 폴더는 수정하지 않고 상태만 동기화했습니다.") ||
    text.includes("README 핵심 문장을 추출하지 못해 기본 요약으로 대체했습니다.") ||
    text.includes("README는 없지만") ||
    text.includes("파일 구성을 보면") ||
    text.includes("manager_memory를 보면") ||
    text.includes("산출물과 메모리 기준으로 보면")
  );
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

function renderProjects() {
  const projects = getVisibleProjects();
  elements.collectionMeta.innerHTML = `
    <span class="collection-pill">현재 ${escapeHtml(String(projects.length))}개</span>
    <span class="collection-pill subtle">카테고리 ${escapeHtml(String(new Set(projects.map((project) => getProjectCategory(project))).size))}개</span>
  `;

  if (!projects.length) {
    elements.projectGrid.innerHTML = `<article class="empty-state">현재 필터에 맞는 프로젝트가 없습니다.</article>`;
    syncProjectCarouselControls();
    return;
  }

  elements.projectGrid.innerHTML = projects.map(renderProjectCard).join("");
  requestAnimationFrame(() => {
    if (elements.projectGrid) {
      elements.projectGrid.scrollTo({ left: 0, top: 0, behavior: "auto" });
    }
    syncProjectCarouselControls();
  });
}

function syncProjectCarouselControls() {
  if (!elements.projectCarouselPrev || !elements.projectCarouselNext || !elements.projectGrid) return;
  const { scrollLeft, scrollWidth, clientWidth } = elements.projectGrid;
  const canScroll = scrollWidth > clientWidth + 4;
  elements.projectCarouselPrev.disabled = !canScroll || scrollLeft <= 4;
  elements.projectCarouselNext.disabled = !canScroll || scrollLeft + clientWidth >= scrollWidth - 4;
}

function scrollProjectCarousel(direction) {
  if (!elements.projectGrid) return;
  const maxLeft = elements.projectGrid.scrollWidth - elements.projectGrid.clientWidth;
  if (direction < 0 && elements.projectGrid.scrollLeft <= 4) {
    bumpProjectRail("left");
    return;
  }
  if (direction > 0 && elements.projectGrid.scrollLeft >= maxLeft - 4) {
    bumpProjectRail("right");
    return;
  }
  const amount = Math.max(320, Math.floor(elements.projectGrid.clientWidth * 0.88));
  elements.projectGrid.scrollBy({ left: amount * direction, behavior: "smooth" });
  window.setTimeout(() => {
    syncProjectCarouselControls();
  }, 220);
}

function bumpProjectRail(direction) {
  if (!elements.projectCarouselShell) return;
  const className = direction === "left" ? "is-bumping-left" : "is-bumping-right";
  elements.projectCarouselShell.classList.remove("is-bumping-left", "is-bumping-right");
  void elements.projectCarouselShell.offsetWidth;
  elements.projectCarouselShell.classList.add(className);
  window.setTimeout(() => {
    elements.projectCarouselShell?.classList.remove(className);
  }, 260);
}

function renderBlog() {
  if (!elements.blogGrid) return;
  const posts = getSortedBlogPosts();

  if (!posts.length) {
    elements.blogGrid.innerHTML = `<article class="empty-state">아직 공개된 글이 없습니다.</article>`;
    return;
  }

  elements.blogGrid.innerHTML = `
    <div class="blog-board">
      <div class="blog-board-head">
        <span>No</span>
        <span>제목 / 요약</span>
        <span>태그</span>
        <span>업데이트</span>
      </div>
      <div class="blog-board-body">
        ${posts.map((post, index) => renderBlogCard(post, index)).join("")}
      </div>
    </div>
  `;
}

function renderBlogCard(post, index) {
  const viewer = state.bootstrap.viewer;
  return `
    <article class="blog-row" tabindex="0" data-blog-id="${escapeHtml(post.id)}">
      <div class="blog-row-index">${escapeHtml(String(index + 1).padStart(2, "0"))}</div>
      <div class="blog-row-main">
        <div class="blog-card-meta">
          <span class="badge category">${escapeHtml(post.status === "draft" ? "Draft" : "Published")}</span>
        </div>
        <h3>${escapeHtml(post.title)}</h3>
        <p class="blog-excerpt">${escapeHtml(post.excerpt || "")}</p>
      </div>
      <div class="blog-row-tags">
        ${arrayOrEmpty(post.tags).map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="blog-row-side">
        <span class="blog-date">${escapeHtml(formatBlogDate(post.updatedAt || post.createdAt))}</span>
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
  const links = getProjectExternalLinks(project);
  const stackLine = arrayOrEmpty(project.stack).length
    ? arrayOrEmpty(project.stack).slice(0, 6).join(" · ")
    : "문서 산출물";

  return `
    <article class="project-card" tabindex="0" data-project-id="${escapeHtml(project.id)}">
      <div class="card-topline">
        <span class="badge category">${escapeHtml(getProjectCategory(project))}</span>
        <div class="card-status-group">
          ${project.pinned ? `<span class="badge pinned">📌 고정됨</span>` : ""}
          <span class="badge ${project.status === "in-progress" ? "warning" : "success"}">
            ${project.status === "in-progress" ? "진행중" : "완료/운영"}
          </span>
        </div>
      </div>

      <div class="card-tools-inline" title="${escapeHtml(stackLine)}">${escapeHtml(stackLine)}</div>

      <div class="card-heading card-heading-raised">
        ${renderDisplayTitle(project, "card")}
      </div>

      <div class="card-body">
        <section class="card-section card-section-summary">
          <strong class="card-section-label">설명</strong>
          <p class="card-summary">${escapeHtml(project.summary)}</p>
        </section>
        <section class="card-section card-section-diagram">
          <strong class="card-section-label">도식화</strong>
          ${renderPreviewMarkup(project, "card")}
        </section>
        <section class="card-section card-section-links">
          <strong class="card-section-label">관련 링크</strong>
          <div class="project-link-row">
            ${links.length
              ? links
                  .slice(0, 3)
                  .map(
                    (item) => `
                      <a class="project-link-chip" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer noopener">
                        <span>${escapeHtml(item.label)}</span>
                        <small>${escapeHtml(item.text)}</small>
                      </a>
                    `
                  )
                  .join("")
              : `<span class="project-link-chip muted">산출물 중심 카드</span>`}
          </div>
        </section>
        <section class="card-section card-section-proof">
          <strong class="card-section-label">이 프로젝트가 한 일</strong>
          <div class="card-proof-line">
            <span>${escapeHtml(leadHighlight)}</span>
          </div>
        </section>
        <div class="card-footer">
          <span>${escapeHtml(arrayOrEmpty(project.tags).slice(0, 3).join(" · "))}</span>
          <span>댓글 ${escapeHtml(String(commentCount))}</span>
        </div>
      </div>

      ${
        viewer?.role === "admin"
          ? `
            <div class="card-actions">
              <button type="button" class="icon-button subtle ${project.pinned ? "active" : ""}" data-card-action="pin">${project.pinned ? "📌 고정됨" : "📌 핀 고정"}</button>
              <button type="button" class="icon-button" data-card-action="move-left">◀</button>
              <button type="button" class="icon-button" data-card-action="move-right">▶</button>
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
  const diagram = !isVideo ? inferPreviewDiagram(project, preview, variant) : null;

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
        <div class="mock-screen ${isVideo ? "video-mode" : ""} ${diagram ? `diagram-screen diagram-${diagram.type}` : ""}">
          <div class="mock-body ${diagram ? "diagram-body" : ""}">
            ${
              diagram
                ? renderPreviewDiagram(diagram)
                : steps
                    .map(
                      (step, index) => `
                        <div class="mock-step step-${index + 1}">
                          <small>${escapeHtml(step.label || "")}</small>
                          <strong>${escapeHtml(step.value || "")}</strong>
                        </div>
                      `
                    )
                    .join("")
            }
            <p class="mock-caption">${escapeHtml(truncate(preview.caption || project.summary, variant === "detail" ? 120 : 72))}</p>
          </div>
        </div>
      </div>
    </div>
  `;
}

function inferPreviewDiagram(project, preview, variant) {
  const text = [
    project.id,
    project.name,
    project.category,
    project.summary,
    ...arrayOrEmpty(project.tags),
    ...arrayOrEmpty(project.highlights),
    ...arrayOrEmpty(preview.steps).map((step) => (typeof step === "string" ? step : step.value))
  ]
    .join(" ")
    .toLowerCase();

  const labels = pickDiagramTokens(project, preview, variant === "detail" ? 4 : 3);

  if (/(scheduler|desktop|calendar|달력|체크리스트|week|weekly)/.test(text)) {
    return { type: "calendar", labels };
  }
  if (/(todack|mood|feeling|emotion|wellness|감정|회복)/.test(text)) {
    return { type: "checklist", labels };
  }
  if (/(cer|stt|speech|voice|음성)/.test(text)) {
    return { type: "metrics", labels };
  }
  if (/(routing|prompt|judge|moe|family classifier|expert)/.test(text)) {
    return { type: "routing", labels };
  }
  if (/(log|ops|operation|analytics|failure|퍼널)/.test(text)) {
    return { type: "pipeline", labels };
  }
  if (/(nlu|morph|schema|semantic|형태소|유사도|intent|corpus)/.test(text)) {
    return { type: "nodes", labels };
  }
  if (/(gemini|tester|test|tool|script|summary|archive|version)/.test(text)) {
    return { type: "console", labels };
  }
  return { type: "stack", labels };
}

function pickDiagramTokens(project, preview, count) {
  const candidates = [
    ...arrayOrEmpty(preview.steps).map((step) => (typeof step === "string" ? step : step.value)),
    ...arrayOrEmpty(project.highlights),
    ...arrayOrEmpty(project.tags),
    project.summary
  ]
    .map((item) => compactDiagramLabel(item, 16))
    .filter(Boolean);

  return [...new Set(candidates)].slice(0, count);
}

function compactDiagramLabel(value, maxLength = 12) {
  const text = String(value || "")
    .replace(/[()]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return "";
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function previewMetricValue(projectId, index, min = 32, max = 92) {
  let hash = 0;
  const source = `${projectId}:${index}`;
  for (let i = 0; i < source.length; i += 1) {
    hash = (hash * 31 + source.charCodeAt(i)) % 9973;
  }
  return min + (hash % (max - min + 1));
}

function renderPreviewDiagram(diagram) {
  const labels = diagram.labels.length ? diagram.labels : ["Output", "Flow", "Signal"];

  switch (diagram.type) {
    case "calendar":
      return `
        <div class="diagram-board calendar">
          <div class="diagram-calendar-head">
            <span>Mon</span>
            <strong>DeskFlow</strong>
            <span>Week</span>
          </div>
          <div class="diagram-calendar-grid">
            ${Array.from({ length: 14 }, (_, index) => {
              const classes = [
                "diagram-day",
                index === 3 || index === 8 ? "active" : "",
                index === 10 ? "warning" : ""
              ]
                .filter(Boolean)
                .join(" ");
              return `<span class="${classes}">${escapeHtml(String((index % 7) + 1))}</span>`;
            }).join("")}
          </div>
          <div class="diagram-agenda-row">
            ${labels.map((label) => `<span class="diagram-agenda-chip">${escapeHtml(label)}</span>`).join("")}
          </div>
        </div>
      `;
    case "metrics":
      return `
        <div class="diagram-board metrics">
          <div class="diagram-bars">
            ${labels.map((label, index) => `
              <div class="diagram-bar-col">
                <span class="diagram-bar" style="height:${previewMetricValue(label, index)}%"></span>
                <small>${escapeHtml(compactDiagramLabel(label, 8))}</small>
              </div>
            `).join("")}
          </div>
          <div class="diagram-baseline"></div>
        </div>
      `;
    case "routing":
      return `
        <div class="diagram-board routing">
          <div class="diagram-node source">Query</div>
          <div class="diagram-route-line"></div>
          <div class="diagram-route-row">
            ${labels.map((label, index) => `
              <span class="diagram-node route route-${index + 1}">${escapeHtml(compactDiagramLabel(label, 8))}</span>
            `).join("")}
          </div>
          <div class="diagram-route-line short"></div>
          <div class="diagram-output-row">
            <span class="diagram-node output">Judge</span>
            <span class="diagram-node output accent">Best Path</span>
          </div>
        </div>
      `;
    case "pipeline":
      return `
        <div class="diagram-board pipeline">
          <div class="diagram-stage-row">
            ${labels.map((label, index) => `
              <span class="diagram-stage stage-${index + 1}">${escapeHtml(compactDiagramLabel(label, 9))}</span>
            `).join("")}
          </div>
          <div class="diagram-stage-links">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div class="diagram-signal-row">
            <i class="diagram-signal success"></i>
            <i class="diagram-signal warning"></i>
            <i class="diagram-signal neutral"></i>
          </div>
        </div>
      `;
    case "nodes":
      return `
        <div class="diagram-board nodes">
          <div class="diagram-node-cloud">
            <span class="diagram-node-chip anchor">${escapeHtml(compactDiagramLabel(labels[0], 10))}</span>
            ${labels.slice(1).map((label, index) => `
              <span class="diagram-node-chip orbit orbit-${index + 1}">${escapeHtml(compactDiagramLabel(label, 8))}</span>
            `).join("")}
          </div>
          <div class="diagram-node-links">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      `;
    case "checklist":
      return `
        <div class="diagram-board checklist">
          <div class="diagram-checklist-card">
            ${labels.map((label, index) => `
              <div class="diagram-check-row ${index === 1 ? "done" : ""}">
                <span class="diagram-check-box"></span>
                <strong>${escapeHtml(compactDiagramLabel(label, 12))}</strong>
              </div>
            `).join("")}
          </div>
          <div class="diagram-checklist-rail">
            <span class="rail-pill active">Now</span>
            <span class="rail-pill">Later</span>
            <span class="rail-pill muted">Someday</span>
          </div>
        </div>
      `;
    case "console":
      return `
        <div class="diagram-board console">
          <div class="diagram-console-head">
            <i></i><i></i><i></i>
          </div>
          <div class="diagram-console-lines">
            ${labels.map((label, index) => `
              <div class="diagram-console-line line-${index + 1}">
                <span></span>
                <strong>${escapeHtml(compactDiagramLabel(label, 12))}</strong>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    default:
      return `
        <div class="diagram-board stack">
          ${labels.map((label, index) => `
            <div class="diagram-stack-layer layer-${index + 1}">
              <small>Layer ${escapeHtml(String(index + 1).padStart(2, "0"))}</small>
              <strong>${escapeHtml(compactDiagramLabel(label, 14))}</strong>
            </div>
          `).join("")}
        </div>
      `;
  }
}

function renderDisplayTitle(project, variant) {
  const titleTag = variant === "detail" ? "h2" : "h3";
  const title = getProjectDisplayName(project);
  const supportCopy =
    arrayOrEmpty(project.highlights)[0] ||
    arrayOrEmpty(project.tags)[0] ||
    getProjectCategory(project) ||
    project.summary;

  return `
    <div class="display-title ${variant}">
      <${titleTag} class="display-title-text">
        ${variant === "card" ? buildHighlightedTitleMarkup(title) : escapeHtml(title)}
      </${titleTag}>
      <p class="display-title-sub">${escapeHtml(supportCopy)}</p>
    </div>
  `;
}

function buildHighlightedTitleMarkup(title) {
  const text = String(title || "").trim();
  if (!text) return escapeHtml("Project");

  const keywordPattern =
    /(LLM|AI|RAG|STT|CER|NLU|Agent|Prompt|Routing|Log|Archive|Notebook|Schema|Scheduler|Calendar|Toolkit|Morphology|Similarity|Metrics|Automation|Harness|Execution|형태소|감정|로그|프롬프트|라우팅|스키마|유사도|음성|기록|자동화|평가|달력|스케줄러|아카이브|툴박스|하네스)/gi;
  const segments = text.split(keywordPattern).filter(Boolean);

  return segments
    .map((segment) => {
      const isKeyword = keywordPattern.test(segment);
      keywordPattern.lastIndex = 0;
      return `<span class="${isKeyword ? "title-keyword" : "title-plain"}">${escapeHtml(segment)}</span>`;
    })
    .join("");
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

function bindRailNavigation() {
  const railButtons = Array.from(document.querySelectorAll(".rail-button"));
  if (!railButtons.length) return;

  const targets = railButtons
    .map((button) => {
      const href = button.getAttribute("href") || "";
      const section = href.startsWith("#") ? document.querySelector(href) : null;
      return section ? { button, section } : null;
    })
    .filter(Boolean);

  if (!targets.length) return;

  const activateRailButton = (sectionId) => {
    targets.forEach(({ button, section }) => {
      const isActive = section.id === sectionId;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-current", isActive ? "page" : "false");
    });
  };

  railButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const href = button.getAttribute("href") || "";
      if (href.startsWith("#")) {
        activateRailButton(href.slice(1));
      }
    });
  });

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (visible) activateRailButton(visible.target.id);
      },
      {
        rootMargin: "-18% 0px -52% 0px",
        threshold: [0.18, 0.35, 0.55]
      }
    );

    targets.forEach(({ section }) => observer.observe(section));
  }

  activateRailButton(targets[0].section.id);
}

function getProjectExternalLinks(project) {
  const links = [];
  const overrides = PROJECT_LINK_OVERRIDES[project.id] || [];

  if (project.links && typeof project.links === "object") {
    if (Array.isArray(project.links)) {
      project.links.forEach((item) => {
        if (!item?.url) return;
        links.push({
          label: item.label || "Link",
          text: item.text || summarizeLinkHost(item.url),
          url: item.url
        });
      });
    } else {
      const candidates = [
        project.links.github ? { label: "GitHub", url: project.links.github } : null,
        project.links.live ? { label: "Live", url: project.links.live } : null,
        project.links.docs ? { label: "Docs", url: project.links.docs } : null,
        project.links.notion ? { label: "Notion", url: project.links.notion } : null
      ].filter(Boolean);
      candidates.forEach((item) => {
        links.push({
          label: item.label,
          text: summarizeLinkHost(item.url),
          url: item.url
        });
      });
    }
  }

  overrides.forEach((item) => {
    links.push({
      label: item.label,
      text: item.text || summarizeLinkHost(item.url),
      url: item.url
    });
  });

  return links.filter((item, index, array) => array.findIndex((candidate) => candidate.url === item.url) === index);
}

function summarizeLinkHost(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");
    const path = parsed.pathname && parsed.pathname !== "/" ? parsed.pathname : "";
    return truncate(`${host}${path}`.replace(/\/$/, ""), 42);
  } catch {
    return truncate(String(url || "").replace(/^https?:\/\//, ""), 42);
  }
}

function buildDetailOverviewRows(project, timelineEntry) {
  const stackText = arrayOrEmpty(project.stack).slice(0, 3).join(", ");

  return [
    {
      label: "Status",
      value: project.status === "in-progress" ? "In Progress" : "Completed"
    },
    {
      label: "Period",
      value: timelineEntry.label || "기록 정리중"
    },
    {
      label: "Category",
      value: getProjectCategory(project)
    },
    stackText
      ? {
          label: "Core Stack",
          value: stackText
        }
      : null
  ].filter(Boolean);
}

function formatTimelinePoint(value) {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, "0")}.${String(date.getDate()).padStart(2, "0")}`;
}

function buildDetailTimelineItems(timelineEntry, story) {
  const difficultyItems = arrayOrEmpty(timelineEntry.difficulties).map((item) => ({
    order: item.start?.getTime?.() || 0,
    tone: item.severity === "high" ? "problem" : item.severity === "medium" ? "warning" : "neutral",
    eyebrow: "Difficulty",
    title: item.label || "핵심 난관",
    meta: formatTimelineLabel(item.start, item.end),
    description: truncate(story.challenge || "", 78)
  }));

  const milestoneItems = arrayOrEmpty(timelineEntry.milestones).map((item, index) => ({
    order: item.date?.getTime?.() || 0,
    tone: item.tone === "success" ? "success" : item.tone === "warning" ? "warning" : "neutral",
    eyebrow: "Milestone",
    title: item.label || "작업 마일스톤",
    meta: formatTimelinePoint(item.date),
    description: truncate(
      item.tone === "success"
        ? story.resolution || story.narrative || ""
        : arrayOrEmpty(story.attempts)[index] || story.narrative || "",
      78
    )
  }));

  return [...difficultyItems, ...milestoneItems]
    .filter((item) => item.title || item.description)
    .sort((left, right) => left.order - right.order)
    .slice(0, 6);
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
  const externalLinks = getProjectExternalLinks(project);
  const viewer = state.bootstrap.viewer;
  const overviewRows = buildDetailOverviewRows(project, timelineEntry);
  const timelineItems = buildDetailTimelineItems(timelineEntry, story);
  const impactItems = arrayOrEmpty(story.impact).length ? arrayOrEmpty(story.impact) : arrayOrEmpty(project.highlights);
  const attemptItems = arrayOrEmpty(story.attempts).length ? arrayOrEmpty(story.attempts) : [buildEvidenceNote(project)];
  const noteItems = buildProjectNotes(project, story, timelineEntry);

  elements.detailModalBody.innerHTML = `
    <article class="detail-shell">
      <header class="detail-hero-card">
        <div class="detail-hero-copy">
          <div class="detail-badges">
            <span class="badge category">${escapeHtml(getProjectCategory(project))}</span>
            <div class="card-status-group">
              ${project.pinned ? `<span class="badge pinned">📌 고정됨</span>` : ""}
              <span class="badge ${project.status === "in-progress" ? "warning" : "success"}">
                ${project.status === "in-progress" ? "진행중" : "완료/운영"}
              </span>
            </div>
          </div>
          <div id="detail-title-anchor">
            ${renderDisplayTitle(project, "detail")}
          </div>
          <p class="panel-summary">${escapeHtml(project.summary)}</p>
        </div>
        <div class="detail-hero-side">
          <span class="collection-pill">${escapeHtml(timelineEntry.label)}</span>
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
      </header>

      <div class="detail-body-grid">
        <aside class="detail-sidebar">
          <section class="detail-card-shell detail-visual-card">
            <div class="detail-card-head">
              <div>
                <p class="panel-kicker">Visual Snapshot</p>
                <h3>Interface Preview</h3>
              </div>
              <span class="detail-mini-badge">${escapeHtml(project.status === "in-progress" ? "BUILD" : "LIVE")}</span>
            </div>
            ${renderPreviewMarkup(project, "detail")}
            <p class="detail-visual-caption">${escapeHtml(detail.diagramCaption || "결과물의 성격이 바로 읽히도록 도식형 프리뷰로 정리했습니다.")}</p>
          </section>

          <section class="detail-card-shell">
            <div class="detail-card-head">
              <div>
                <p class="panel-kicker">Project Overview</p>
                <h3>핵심 정보</h3>
              </div>
            </div>
            <dl class="detail-overview-list">
              ${overviewRows
                .map(
                  (item) => `
                    <div class="detail-overview-row">
                      <dt>${escapeHtml(item.label)}</dt>
                      <dd>${escapeHtml(item.value)}</dd>
                    </div>
                  `
                )
                .join("")}
            </dl>
            <div class="detail-chip-cluster">
              ${arrayOrEmpty(project.stack).map((item) => `<span class="detail-mini-chip">${escapeHtml(item)}</span>`).join("")}
            </div>
            <div class="detail-chip-cluster muted">
              ${arrayOrEmpty(project.tags).map((tag) => `<span class="detail-mini-chip subtle">${escapeHtml(tag)}</span>`).join("")}
            </div>
          </section>

          <section class="detail-card-shell">
            <div class="detail-card-head">
              <div>
                <p class="panel-kicker">Resources</p>
                <h3>바로 열기</h3>
              </div>
            </div>
            <div class="detail-resource-list">
              ${
                externalLinks.length
                  ? externalLinks
                      .map(
                        (item) => `
                          <a class="detail-link-card" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer noopener">
                            <small>${escapeHtml(item.label)}</small>
                            <strong>${escapeHtml(item.text)}</strong>
                            <span>${escapeHtml(summarizeLinkHost(item.url))}</span>
                          </a>
                        `
                      )
                      .join("")
                  : `<article class="empty-state small">외부 리소스가 아직 없습니다.</article>`
              }
            </div>
          </section>

          <section class="detail-card-shell">
            <div class="detail-card-head">
              <div>
                <p class="panel-kicker">Timeline View</p>
                <h3>진행 흐름</h3>
              </div>
            </div>
            <div class="detail-mini-timeline">
              ${
                timelineItems.length
                  ? timelineItems
                      .map(
                        (item) => `
                          <article class="detail-timeline-item ${escapeHtml(item.tone)}">
                            <span class="detail-timeline-dot"></span>
                            <div class="detail-timeline-copy">
                              <small>${escapeHtml(item.eyebrow)}</small>
                              <strong>${escapeHtml(item.title)}</strong>
                              <span>${escapeHtml(item.meta)}</span>
                              ${item.description ? `<p>${escapeHtml(item.description)}</p>` : ""}
                            </div>
                          </article>
                        `
                      )
                      .join("")
                  : `<article class="empty-state small">타임라인 데이터가 아직 없습니다.</article>`
              }
            </div>
          </section>
        </aside>

        <div class="detail-main">
          <section class="detail-card-shell">
            <div class="detail-problem-solution-grid">
              <article class="detail-callout problem">
                <small>Problem Identified</small>
                <h3>${escapeHtml(story.challenge || project.summary)}</h3>
                <p>${escapeHtml(story.narrative || project.summary)}</p>
              </article>
              <article class="detail-callout solution">
                <small>Solution Resolved</small>
                <h3>${escapeHtml(story.resolution || project.summary)}</h3>
                <p>${escapeHtml(impactItems[0] || buildEvidenceNote(project))}</p>
              </article>
            </div>
          </section>

          <section class="detail-card-shell">
            <div class="detail-card-head">
              <div>
                <p class="panel-kicker">Execution Track</p>
                <h3>어떻게 풀었는지</h3>
              </div>
            </div>
            <div class="detail-attempt-list">
              ${attemptItems
                .map(
                  (item, index) => `
                    <article class="detail-attempt-item">
                      <span>TRY ${escapeHtml(String(index + 1).padStart(2, "0"))}</span>
                      <p>${escapeHtml(item)}</p>
                    </article>
                  `
                )
                .join("")}
            </div>
          </section>

          <section class="detail-card-shell">
            <div class="detail-card-head">
              <div>
                <p class="panel-kicker">Impact Signals</p>
                <h3>Resolved / Impact</h3>
              </div>
            </div>
            <div class="detail-impact-layout">
              <article class="detail-impact-summary">
                <small>Resolved</small>
                <strong>${escapeHtml(story.resolution || project.summary)}</strong>
              </article>
              <div class="detail-impact-pills">
                ${impactItems.map((item) => `<span class="focus-impact-pill">${escapeHtml(item)}</span>`).join("")}
              </div>
            </div>
          </section>

          <section class="detail-card-shell">
            <div class="detail-card-head">
              <div>
                <p class="panel-kicker">Project Notes</p>
                <h3>분석 메모</h3>
              </div>
              <span class="detail-section-hint">목적, 판단 근거, 결과 중심 정리</span>
            </div>
            <div class="detail-note-list">
              ${noteItems
                .map(
                  (line, index) => `
                    <article class="detail-note-card">
                      <small>NOTE ${escapeHtml(String(index + 1).padStart(2, "0"))}</small>
                      <p>${escapeHtml(line)}</p>
                    </article>
                  `
                )
                .join("")}
            </div>
          </section>

          <section class="detail-card-shell detail-comments-shell">
            <div class="detail-card-head">
              <div>
                <p class="panel-kicker">Comments</p>
                <h3>Visitor Comments</h3>
              </div>
              <span class="detail-section-hint">비회원도 작성 가능</span>
            </div>
            <form id="comment-form" class="detail-comment-form">
              ${
                viewer
                  ? `
                    <div class="detail-comment-meta logged-in">
                      <span class="comment-identity-pill">${escapeHtml(viewer.name || viewer.email || "로그인 사용자")}</span>
                      <input name="commentPassword" type="password" maxlength="32" placeholder="댓글 비밀번호 (선택)" />
                    </div>
                  `
                  : `
                    <div class="detail-comment-meta">
                      <input name="nickname" type="text" maxlength="24" placeholder="닉네임" />
                      <input name="commentPassword" type="password" maxlength="32" placeholder="댓글 비밀번호 (선택)" />
                    </div>
                  `
              }
              <textarea name="message" rows="3" maxlength="1000" placeholder="프로젝트를 보고 느낀 점이나 질문을 남겨보세요"></textarea>
              <div class="detail-comment-actions">
                <button type="submit" class="primary-button">댓글 등록</button>
              </div>
              <p class="detail-comment-hint">${
                viewer
                  ? "로그인 상태에선 현재 계정 이름으로 저장되고, 비밀번호는 선택값입니다."
                  : "비회원도 댓글을 남길 수 있고, 닉네임은 필수입니다. 비밀번호는 선택값이고 관리자는 확인할 수 있습니다."
              }</p>
            </form>
            <div class="comment-list detail-comment-list">
              ${
                comments.length
                  ? comments
                      .map(
                        (comment) => `
                          <article class="comment-card detail-comment-card">
                            <div class="comment-author">
                              <div class="avatar-circle">${escapeHtml((comment.authorName || "?").slice(0, 1).toUpperCase())}</div>
                              <div>
                                <strong>${escapeHtml(comment.authorName || "Visitor")}</strong>
                                <span>${formatDate(comment.createdAt)}</span>
                              </div>
                            </div>
                            ${
                              viewer?.role === "admin" && comment.password
                                ? `<div class="comment-password-pill">PW ${escapeHtml(comment.password)}</div>`
                                : ""
                            }
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
    </article>
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
  void loadBlogComments(blogId);
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
  const comments = state.blogCommentsByPost.get(post.id) || [];
  const posts = getSortedBlogPosts();
  const siblings = getAdjacentBlogPosts(post.id);
  const readMinutes = estimateBlogReadMinutes(post.markdown || post.excerpt || "");
  const editorialMeta = getBlogEditorialMeta(post);
  const heroChip = arrayOrEmpty(post.tags)[0] || (post.status === "draft" ? "Draft" : "Editorial");

  elements.blogModalBody.innerHTML = `
    <article class="blog-editorial-shell">
      <header class="blog-editorial-topbar">
        <div class="blog-editorial-topbar-mark">
          <span class="blog-editorial-mark-icon">✦</span>
          <span class="blog-editorial-mark-label">Editorial Series</span>
        </div>
        <button class="blog-editorial-close" data-close-blog type="button" aria-label="닫기">×</button>
      </header>

      <div class="blog-editorial-scroll">
        <article class="blog-editorial-article">
          <section class="blog-editorial-hero">
            <div class="blog-editorial-wrap">
              <div class="blog-editorial-kickers">
                <span class="blog-editorial-chip primary">${escapeHtml(heroChip)}</span>
              </div>

              <div class="blog-editorial-title-row">
                <div class="blog-editorial-title-copy">
                  <h2 id="blog-detail-title" class="blog-editorial-title">${escapeHtml(post.title)}</h2>
                  <p class="blog-editorial-excerpt">${escapeHtml(post.excerpt || "")}</p>
                </div>
                ${
                  viewer?.role === "admin"
                    ? `
                      <div class="blog-editorial-admin-actions">
                        <button type="button" class="ghost-button" data-blog-detail-action="edit" data-blog-id="${escapeHtml(post.id)}">편집</button>
                        <button type="button" class="ghost-button danger" data-blog-detail-action="delete" data-blog-id="${escapeHtml(post.id)}">삭제</button>
                      </div>
                    `
                    : ""
                }
              </div>

              <div class="blog-editorial-meta">
                <div class="blog-editorial-author">
                  <img class="blog-editorial-author-avatar" src="assets/about-memoji.png" alt="author avatar" />
                  <span class="blog-editorial-author-name">${escapeHtml(state.bootstrap.owner?.name || "김도원")}</span>
                </div>
                <span class="blog-editorial-meta-sep">•</span>
                <time datetime="${escapeHtml(post.updatedAt || post.createdAt)}">${escapeHtml(formatBlogDate(post.updatedAt || post.createdAt))}</time>
                <span class="blog-editorial-meta-sep">•</span>
                <span>${escapeHtml(String(readMinutes))} min read</span>
              </div>
            </div>

            <div class="blog-editorial-visual-shell">
              <div class="blog-editorial-visual">
                <div class="blog-editorial-visual-grid" aria-hidden="true"></div>
                <p class="blog-editorial-visual-label">${escapeHtml(editorialMeta.noteLabel)}</p>
                <p class="blog-editorial-visual-copy">${escapeHtml(editorialMeta.leadNote)}</p>
              </div>
            </div>

            <div class="blog-editorial-wrap">
              <div class="blog-editorial-body blog-markdown-body">${renderMarkdown(post.markdown || "")}</div>
            </div>
          </section>

          <section class="blog-editorial-comments">
            <div class="blog-editorial-wrap">
              <div class="blog-comments-head">
                <div class="blog-comments-title">
                  <span class="blog-comments-icon">✳</span>
                  <h3>Comments <span>(${escapeHtml(String(comments.length))})</span></h3>
                </div>
              </div>

              <form id="blog-comment-form" class="blog-comment-form">
                <div class="blog-comment-form-row">
                  <div class="blog-comment-form-avatar">
                    ${
                      viewer?.picture
                        ? `<img src="${escapeHtml(viewer.picture)}" alt="viewer avatar" />`
                        : `<img src="assets/about-memoji.png" alt="profile avatar" />`
                    }
                  </div>
                  <div class="blog-comment-form-main">
                    ${
                      viewer
                        ? `
                          <div class="blog-comment-meta logged-in">
                            <span class="blog-comment-identity">${escapeHtml(viewer.name || viewer.email || "로그인 사용자")}</span>
                            <input name="commentPassword" type="password" maxlength="32" placeholder="댓글 비밀번호 (선택)" />
                          </div>
                        `
                        : `
                          <div class="blog-comment-meta">
                            <input name="nickname" type="text" maxlength="24" placeholder="닉네임" />
                            <input name="commentPassword" type="password" maxlength="32" placeholder="댓글 비밀번호 (선택)" />
                          </div>
                        `
                    }
                    <textarea name="message" rows="4" maxlength="1000" placeholder="이 글을 보고 든 생각이나 질문을 남겨보세요"></textarea>
                    <div class="blog-comment-form-actions">
                      <p class="blog-comment-form-hint">${
                        viewer
                          ? "현재 계정 이름으로 저장됩니다. 비밀번호는 선택값입니다."
                          : "비회원도 댓글 작성 가능. 닉네임은 필수, 비밀번호는 선택값입니다."
                      }</p>
                      <button type="submit" class="blog-comment-submit">Post Comment</button>
                    </div>
                  </div>
                </div>
              </form>

              <div class="blog-comment-list">
                ${
                  comments.length
                    ? comments.map((comment) => renderBlogCommentCard(comment, viewer)).join("")
                    : `<article class="blog-comment-empty">아직 댓글이 없습니다. 첫 반응을 남겨주세요.</article>`
                }
              </div>
            </div>
          </section>

          <section class="blog-editorial-series">
            <div class="blog-editorial-wrap">
              <p class="blog-series-kicker">Next in Editorial Series</p>
              <div class="blog-series-grid">
                ${
                  siblings.previous
                    ? `
                      <button type="button" class="blog-series-card" data-blog-nav="previous" data-blog-id="${escapeHtml(siblings.previous.id)}">
                        <small>Previous</small>
                        <strong>${escapeHtml(siblings.previous.title)}</strong>
                        <span>${escapeHtml(truncate(siblings.previous.excerpt || "", 120))}</span>
                      </button>
                    `
                    : `<article class="blog-series-card muted"><small>Previous</small><strong>첫 글입니다</strong><span>이전 글이 없습니다.</span></article>`
                }
                ${
                  siblings.next
                    ? `
                      <button type="button" class="blog-series-card" data-blog-nav="next" data-blog-id="${escapeHtml(siblings.next.id)}">
                        <small>Next</small>
                        <strong>${escapeHtml(siblings.next.title)}</strong>
                        <span>${escapeHtml(truncate(siblings.next.excerpt || "", 120))}</span>
                      </button>
                    `
                    : `<article class="blog-series-card muted"><small>Next</small><strong>마지막 글입니다</strong><span>다음 글이 없습니다.</span></article>`
                }
              </div>
            </div>
          </section>
        </article>
      </div>

      <footer class="blog-editorial-footer">
        <button type="button" class="blog-footer-nav ${siblings.previous ? "" : "disabled"}" ${
          siblings.previous ? `data-blog-nav="previous" data-blog-id="${escapeHtml(siblings.previous.id)}"` : "disabled"
        }>
          <span class="blog-footer-kicker">Previous Post</span>
          <strong>${escapeHtml(siblings.previous?.title || "이전 글 없음")}</strong>
        </button>
        <div class="blog-footer-indicator">
          <span>${escapeHtml(String(posts.findIndex((item) => item.id === post.id) + 1).padStart(2, "0"))}</span>
          <span>/</span>
          <span>${escapeHtml(String(posts.length).padStart(2, "0"))}</span>
        </div>
        <button type="button" class="blog-footer-nav next ${siblings.next ? "" : "disabled"}" ${
          siblings.next ? `data-blog-nav="next" data-blog-id="${escapeHtml(siblings.next.id)}"` : "disabled"
        }>
          <span class="blog-footer-kicker">Next Post</span>
          <strong>${escapeHtml(siblings.next?.title || "다음 글 없음")}</strong>
        </button>
      </footer>
    </article>
  `;
}

function renderBlogCommentCard(comment, viewer) {
  return `
    <article class="blog-comment-card">
      <div class="blog-comment-avatar">${escapeHtml((comment.authorName || "?").slice(0, 1).toUpperCase())}</div>
      <div class="blog-comment-copy">
        <div class="blog-comment-meta-line">
          <strong>${escapeHtml(comment.authorName || "Visitor")}</strong>
          <span>${escapeHtml(formatRelativeTime(comment.createdAt))}</span>
          ${
            viewer?.role === "admin" && comment.password
              ? `<span class="blog-comment-password">PW ${escapeHtml(comment.password)}</span>`
              : ""
          }
        </div>
        <p>${escapeHtml(comment.message || "")}</p>
      </div>
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

async function loadBlogComments(blogId) {
  try {
    const data = await api(`/api/blog-comments?blogId=${encodeURIComponent(blogId)}`);
    state.blogCommentsByPost.set(blogId, data.comments || []);
    if (state.currentBlogId === blogId) {
      renderOpenBlog();
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
  const nicknameInput = form?.elements.namedItem("nickname");
  const passwordInput = form?.elements.namedItem("commentPassword");
  if (!textarea) return;
  const message = textarea.value.trim();
  const nickname = String(nicknameInput?.value || "").trim();
  const password = String(passwordInput?.value || "").trim();
  if (!message) return;
  if (!state.bootstrap.viewer && !nickname) {
    window.alert("닉네임을 입력해주세요.");
    return;
  }

  try {
    await api("/api/comments", {
      method: "POST",
      body: {
        projectId: state.currentProjectId,
        message,
        nickname,
        password
      }
    });
    textarea.value = "";
    if (passwordInput) {
      passwordInput.value = "";
    }
    await loadComments(state.currentProjectId);
    await refreshCommentCounts();
  } catch (error) {
    window.alert(`댓글 등록 실패: ${error.message}`);
  }
}

async function submitBlogComment() {
  const form = elements.blogModalBody?.querySelector("#blog-comment-form");
  const textarea = form?.elements.namedItem("message");
  const nicknameInput = form?.elements.namedItem("nickname");
  const passwordInput = form?.elements.namedItem("commentPassword");
  if (!textarea || !state.currentBlogId) return;

  const message = textarea.value.trim();
  const nickname = String(nicknameInput?.value || "").trim();
  const password = String(passwordInput?.value || "").trim();
  if (!message) return;
  if (!state.bootstrap.viewer && !nickname) {
    window.alert("닉네임을 입력해주세요.");
    return;
  }

  try {
    await api("/api/blog-comments", {
      method: "POST",
      body: {
        blogId: state.currentBlogId,
        message,
        nickname,
        password
      }
    });
    textarea.value = "";
    if (nicknameInput) {
      nicknameInput.value = "";
    }
    if (passwordInput) {
      passwordInput.value = "";
    }
    await loadBlogComments(state.currentBlogId);
  } catch (error) {
    window.alert(`블로그 댓글 등록 실패: ${error.message}`);
  }
}

async function refreshCommentCounts() {
  const data = await api("/api/bootstrap");
  state.bootstrap.commentCounts = data.commentCounts;
  renderProjects();
}

async function saveProjectPatch(projectId, patch) {
  const project = findProject(projectId);
  if (!project) return;
  await api("/api/projects", {
    method: "POST",
    body: {
      project: {
        ...project,
        ...patch
      }
    }
  });
}

async function reorderProject(projectId, direction) {
  const ordered = getVisibleProjects();
  const currentIndex = ordered.findIndex((project) => project.id === projectId);
  const nextIndex = currentIndex + direction;
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= ordered.length) return;

  const normalized = ordered.map((project, index) => ({
    ...project,
    manualOrder: index
  }));
  const current = normalized[currentIndex];
  const target = normalized[nextIndex];
  const currentOrder = current.manualOrder;

  current.manualOrder = target.manualOrder;
  target.manualOrder = currentOrder;

  try {
    await saveProjectPatch(current.id, { manualOrder: current.manualOrder });
    await saveProjectPatch(target.id, { manualOrder: target.manualOrder });
    await refreshApp();
  } catch (error) {
    window.alert(`순서 변경 실패: ${error.message}`);
  }
}

async function toggleProjectPin(projectId) {
  const ordered = getOrderedProjects(state.bootstrap.projects);
  const target = ordered.find((project) => project.id === projectId);
  if (!target) return;

  const orders = ordered
    .map((project) => {
      if (project.manualOrder === null || project.manualOrder === undefined || project.manualOrder === "") {
        return null;
      }
      const value = Number(project.manualOrder);
      return Number.isFinite(value) ? value : null;
    })
    .filter((value) => value !== null);
  const minOrder = orders.length ? Math.min(...orders) : 0;
  const maxOrder = orders.length ? Math.max(...orders) : ordered.length;
  const nextPinned = !target.pinned;

  try {
    await saveProjectPatch(projectId, {
      pinned: nextPinned,
      manualOrder: nextPinned ? minOrder - 1 : maxOrder + 1
    });
    await refreshApp();
  } catch (error) {
    window.alert(`핀 변경 실패: ${error.message}`);
  }
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

function getProjectManualOrder(project) {
  if (project.manualOrder === null || project.manualOrder === undefined || project.manualOrder === "") {
    return Number.MAX_SAFE_INTEGER;
  }
  const order = Number(project.manualOrder);
  return Number.isFinite(order) ? order : Number.MAX_SAFE_INTEGER;
}

function getProjectDeduplicationKey(project) {
  const githubLink = getProjectExternalLinks(project).find((item) => String(item.label || "").toLowerCase() === "github");
  if (!githubLink?.url) return "";
  return `github:${String(githubLink.url).trim().replace(/\/+$/, "").toLowerCase()}`;
}

function getOrderedProjects(projects) {
  const ordered = [...projects].sort((left, right) => {
    const pinDiff = Number(Boolean(right.pinned)) - Number(Boolean(left.pinned));
    if (pinDiff) return pinDiff;

    const orderDiff = getProjectManualOrder(left) - getProjectManualOrder(right);
    if (orderDiff) return orderDiff;

    const recentDiff = getProjectRecentTimestamp(right) - getProjectRecentTimestamp(left);
    if (recentDiff) return recentDiff;

    return String(getProjectDisplayName(left)).localeCompare(String(getProjectDisplayName(right)), "ko");
  });

  const seen = new Set();
  return ordered.filter((project) => {
    const key = getProjectDeduplicationKey(project);
    if (!key) return true;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function getVisibleProjects() {
  return getOrderedProjects(state.bootstrap.projects)
    .filter((project) => {
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

function getProjectRecentTimestamp(project) {
  return (
    parseTimelineDate(project.timeline?.end || project.timeline?.start || project.createdAt)?.getTime() || 0
  );
}

function findProject(projectId) {
  return state.bootstrap.projects.find((project) => project.id === projectId);
}

function findBlogPost(blogId) {
  return arrayOrEmpty(state.bootstrap.blogPosts).find((post) => post.id === blogId);
}

function getSortedBlogPosts() {
  return [...arrayOrEmpty(state.bootstrap?.blogPosts)]
    .filter((post) => post.status === "published" || state.bootstrap.viewer?.role === "admin")
    .sort((left, right) => String(right.updatedAt || right.createdAt || "").localeCompare(String(left.updatedAt || left.createdAt || "")));
}

function getAdjacentBlogPosts(blogId) {
  const posts = getSortedBlogPosts();
  const index = posts.findIndex((post) => post.id === blogId);
  return {
    previous: index >= 0 ? posts[index - 1] || null : null,
    next: index >= 0 ? posts[index + 1] || null : null
  };
}

function getBlogEditorialMeta(post) {
  const override = BLOG_EDITORIAL_OVERRIDES[post.id];
  if (override) {
    return override;
  }
  return {
    noteLabel: arrayOrEmpty(post.tags)[0] || "Editorial Note",
    leadNote: extractLeadParagraph(post.markdown || "") || post.excerpt || "이 글의 핵심 포인트를 정리 중입니다."
  };
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

function formatRelativeTime(value) {
  const date = parseTimelineDate(value);
  if (!date) return String(value || "");
  const diffMs = date.getTime() - Date.now();
  const minutes = Math.round(diffMs / (1000 * 60));
  const hours = Math.round(diffMs / (1000 * 60 * 60));
  const days = Math.round(diffMs / (1000 * 60 * 60 * 24));
  const formatter = new Intl.RelativeTimeFormat("ko-KR", { numeric: "auto" });
  if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
  if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
  return formatter.format(days, "day");
}

function estimateBlogReadMinutes(value) {
  const plain = String(value || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#>*`\-\[\]\(\)]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const units = plain ? plain.split(" ").length : 0;
  return Math.max(1, Math.round(units / 220));
}

function extractLeadParagraph(value) {
  const lines = String(value || "")
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const line = lines.find((item) => !/^#{1,4}\s/.test(item) && !/^[-*]\s/.test(item) && !/^>\s/.test(item));
  return line ? line.replace(/[*`[\]()]/g, "").trim() : "";
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
