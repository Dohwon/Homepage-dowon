const http = require("http");
const fs = require("fs");
const fsp = require("fs/promises");
const path = require("path");
const crypto = require("crypto");

const ROOT = __dirname;
const DATA_DIR = path.join(ROOT, "data");
const SITE_CONTENT_PATH = path.join(DATA_DIR, "site-content.json");
const COMMENTS_PATH = path.join(DATA_DIR, "comments.json");
const ANALYTICS_PATH = path.join(DATA_DIR, "analytics.jsonl");
const ENV_PATH = path.join(ROOT, ".env");

loadEnv();

const PORT = Number(process.env.PORT || 4173);
const HOST = process.env.HOST || "0.0.0.0";
const SESSION_SECRET = process.env.SESSION_SECRET || crypto.randomBytes(32).toString("hex");
const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID || "";
const ADMIN_EMAILS = new Set(
  (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean)
);
const DEV_ALLOW_LOCAL_LOGIN = process.env.DEV_ALLOW_LOCAL_LOGIN === "true";
const DEV_ADMIN_EMAIL = (process.env.DEV_ADMIN_EMAIL || "").trim().toLowerCase();

const SESSION_COOKIE = "portfolio_session";
const VISITOR_COOKIE = "portfolio_visitor";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;
const MAX_COMMENT_LENGTH = 1000;

const MIME_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".json": "application/json; charset=utf-8",
  ".mp4": "video/mp4",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".webm": "video/webm"
};

async function ensureStorage() {
  await fsp.mkdir(DATA_DIR, { recursive: true });

  try {
    await fsp.access(SITE_CONTENT_PATH);
  } catch {
    const seeded = await buildSeedContent();
    await writeJsonAtomic(SITE_CONTENT_PATH, seeded);
  }

  try {
    await fsp.access(COMMENTS_PATH);
  } catch {
    await writeJsonAtomic(COMMENTS_PATH, { comments: [] });
  }

  try {
    await fsp.access(ANALYTICS_PATH);
  } catch {
    await fsp.writeFile(ANALYTICS_PATH, "", "utf8");
  }
}

async function buildSeedContent() {
  const generated = await readJson(path.join(DATA_DIR, "projects.generated.json"), null);
  const manual = await readJson(path.join(DATA_DIR, "projects.json"), null);
  const primary = generated || manual || {};
  const secondary = manual || {};

  const mergedProjects = mergeProjects(primary.projects || [], secondary.projects || []);
  const owner = secondary.owner || primary.owner || defaultOwner();
  const profile = secondary.profile || primary.profile || {};
  const links = { ...(primary.links || {}), ...(secondary.links || {}) };

  return {
    site: defaultSite(owner, links),
    owner,
    profile,
    links,
    projects: mergedProjects.map((project, index) => normalizeProject(project, index)),
    meta: {
      seededAt: new Date().toISOString(),
      source: generated ? "projects.generated.json" : "projects.json"
    }
  };
}

function mergeProjects(primaryProjects, secondaryProjects) {
  const secondaryMap = new Map(secondaryProjects.map((project) => [project.id || slugify(project.name || "project"), project]));
  const merged = primaryProjects.map((project) => {
    const id = project.id || slugify(project.name || "project");
    const secondary = secondaryMap.get(id) || {};
    secondaryMap.delete(id);
    return {
      ...project,
      ...secondary,
      detail: secondary.detail || project.detail,
      highlights: secondary.highlights || project.highlights,
      stack: secondary.stack || project.stack,
      tags: secondary.tags || project.tags
    };
  });

  for (const project of secondaryMap.values()) {
    merged.push(project);
  }
  return merged;
}

function mergeProjectsByStatus(existingProjects, generatedProjects) {
  const generatedMap = new Map(
    generatedProjects.map((project) => [project.id || slugify(project.name || "project"), project])
  );

  const merged = existingProjects.map((project) => {
    const id = project.id || slugify(project.name || "project");
    const generated = generatedMap.get(id);
    if (!generated) return project;
    generatedMap.delete(id);
    return {
      ...project,
      status: generated.status || project.status,
      path: project.path || generated.path || "",
      readme: project.readme || generated.readme || ""
    };
  });

  for (const generated of generatedMap.values()) {
    merged.push({
      id: generated.id,
      name: generated.name,
      status: generated.status,
      category: generated.category || "Imported Project",
      summary: "원본 프로젝트에서 상태만 복사한 항목입니다.",
      highlights: [`상태: ${generated.status === "in-progress" ? "진행중" : "완료/운영"}`],
      stack: [],
      tags: ["Imported", "Status Sync"],
      path: generated.path || "",
      readme: generated.readme || "",
      detail: {
        readmeSummary: ["원본 프로젝트 폴더는 수정하지 않고 상태만 동기화했습니다."],
        workflow: [],
        keyFiles: generated.path ? [generated.path] : [],
        diagramCaption: "원본 프로젝트 상태 동기화 카드"
      }
    });
  }

  return merged;
}

function normalizeProject(project, index) {
  const id = project.id || slugify(project.name || `project-${index + 1}`);
  const previewAssets = inferPreviewAssets(id);
  const detail = normalizeDetail(project.detail, project);
  const preview = normalizePreview(project.preview, project, previewAssets);
  const story = normalizeStory(project.story, project);
  const timeline = normalizeTimeline(project.timeline, project);

  return {
    id,
    name: String(project.name || `Project ${index + 1}`),
    status: project.status === "in-progress" ? "in-progress" : "active",
    category: String(project.category || "General"),
    summary: String(project.summary || "요약 정보가 아직 없습니다."),
    highlights: arrayify(project.highlights),
    stack: arrayify(project.stack),
    tags: arrayify(project.tags),
    path: String(project.path || ""),
    readme: project.readme ? String(project.readme) : "",
    detail,
    preview,
    story,
    timeline,
    createdAt: project.createdAt || new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };
}

function normalizeDetail(detail, project) {
  const fallbackFlow = [
    { step: "문제 정의", desc: "핵심 과업과 제약 조건을 정리합니다." },
    { step: "설계/실험", desc: "가설을 세우고 작은 단위로 설계와 검증을 반복합니다." },
    { step: "구현/검증", desc: "결과물을 실행 가능한 형태로 만들고 지표로 확인합니다." }
  ];

  return {
    readmeSummary: arrayify(detail?.readmeSummary).length
      ? arrayify(detail.readmeSummary)
      : [project.summary || "요약 정보가 아직 없습니다."],
    workflow: Array.isArray(detail?.workflow) && detail.workflow.length
      ? detail.workflow
          .map((item) => ({
            step: String(item.step || "단계"),
            desc: String(item.desc || "")
          }))
          .filter((item) => item.step || item.desc)
      : fallbackFlow,
    keyFiles: arrayify(detail?.keyFiles || [project.path, project.readme]).filter(Boolean),
    diagramCaption: String(detail?.diagramCaption || "입력 -> 설계 -> 실행 -> 결과 흐름")
  };
}

function normalizePreview(preview, project, assets) {
  const stepsSource = arrayify(preview?.steps).length
    ? preview.steps
    : arrayify(project.highlights || project.tags).slice(0, 3).map((item, index) => ({
        label: index === 0 ? "Focus" : index === 1 ? "Flow" : "Impact",
        value: item
      }));

  const steps = stepsSource.map((step, index) => {
    if (typeof step === "string") {
      return {
        label: index === 0 ? "Focus" : index === 1 ? "Flow" : "Impact",
        value: step
      };
    }
    return {
      label: String(step.label || `Step ${index + 1}`),
      value: String(step.value || "")
    };
  });

  const useVideo = Boolean(preview?.video || assets.video);

  return {
    mode: useVideo ? "video" : "mock",
    poster: String(preview?.poster || assets.poster || ""),
    video: String(preview?.video || assets.video || ""),
    eyebrow: String(preview?.eyebrow || project.category || "Preview"),
    caption: String(preview?.caption || project.summary || ""),
    steps
  };
}

function normalizeStory(story, project) {
  return {
    narrative: String(story?.narrative || ""),
    challenge: String(story?.challenge || ""),
    attempts: arrayify(story?.attempts),
    resolution: String(story?.resolution || ""),
    impact: arrayify(story?.impact || project.highlights),
    caseIds: arrayify(story?.caseIds)
  };
}

function normalizeTimeline(timeline, project) {
  const inferred = inferProjectDateRange(project);
  const start = normalizeTimelineDate(timeline?.start || inferred.start || project.createdAt);
  const defaultEnd = project.status === "in-progress"
    ? normalizeTimelineDate(new Date())
    : normalizeTimelineDate(timeline?.end || inferred.end || start);
  const end = normalizeTimelineDate(timeline?.end || defaultEnd || start);

  return {
    start,
    end,
    label: String(timeline?.label || buildTimelineLabel(start, end, project.status)),
    difficultyWindows: Array.isArray(timeline?.difficultyWindows)
      ? timeline.difficultyWindows
          .map((item, index) => normalizeDifficultyWindow(item, start, end, index))
          .filter((item) => item.label)
      : [],
    milestones: Array.isArray(timeline?.milestones)
      ? timeline.milestones
          .map((item) => normalizeMilestone(item))
          .filter((item) => item.label || item.date)
      : []
  };
}

function normalizeDifficultyWindow(item, fallbackStart, fallbackEnd, index) {
  return {
    label: String(item?.label || item?.name || `난관 ${index + 1}`),
    start: normalizeTimelineDate(item?.start || fallbackStart),
    end: normalizeTimelineDate(item?.end || fallbackEnd || fallbackStart),
    severity: normalizeSeverity(item?.severity)
  };
}

function normalizeMilestone(item) {
  return {
    label: String(item?.label || item?.name || ""),
    date: normalizeTimelineDate(item?.date || item?.at || ""),
    tone: normalizeTone(item?.tone)
  };
}

function normalizeSeverity(value) {
  const severity = String(value || "").toLowerCase();
  if (severity === "high" || severity === "low") return severity;
  return "medium";
}

function normalizeTone(value) {
  const tone = String(value || "").toLowerCase();
  if (tone === "warning" || tone === "success" || tone === "neutral") return tone;
  return "neutral";
}

function normalizeTimelineDate(value) {
  if (!value) return "";
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.toISOString().slice(0, 10);
  }

  const raw = String(value).trim();
  if (!raw) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  if (/^\d{4}-\d{2}$/.test(raw)) return `${raw}-01`;
  if (/^\d{4}\.\d{2}\.\d{2}$/.test(raw)) return raw.replace(/\./g, "-");
  if (/^\d{4}\.\d{2}$/.test(raw)) return `${raw.replace(".", "-")}-01`;
  if (/^\d{8}$/.test(raw)) return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
  if (/^\d{6}$/.test(raw)) return `20${raw.slice(0, 2)}-${raw.slice(2, 4)}-${raw.slice(4, 6)}`;

  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toISOString().slice(0, 10);
  }
  return "";
}

function buildTimelineLabel(start, end, status) {
  const startLabel = formatTimelineMonth(start);
  const endLabel = formatTimelineMonth(end);
  if (!startLabel && !endLabel) {
    return status === "in-progress" ? "기간 입력 필요 · 진행중" : "기간 입력 필요";
  }
  if (startLabel && endLabel && startLabel !== endLabel) {
    return `${startLabel} - ${endLabel}`;
  }
  return startLabel || endLabel;
}

function formatTimelineMonth(dateText) {
  if (!dateText) return "";
  const normalized = normalizeTimelineDate(dateText);
  if (!normalized) return "";
  return normalized.slice(0, 7).replace("-", ".");
}

function inferProjectDateRange(project) {
  const explicitStart = normalizeTimelineDate(project.timeline?.start || "");
  const explicitEnd = normalizeTimelineDate(project.timeline?.end || "");
  if (explicitStart || explicitEnd) {
    return {
      start: explicitStart || explicitEnd,
      end: explicitEnd || explicitStart
    };
  }

  const fromText = extractDateCandidates([project.path, project.id, project.name]);
  const fromPathStats = inspectProjectPathRange(project.path);
  const fallbackStart = fromText[0] || fromPathStats.start || normalizeTimelineDate(project.createdAt);
  const fallbackEnd = project.status === "in-progress"
    ? normalizeTimelineDate(new Date())
    : fromPathStats.end || fromText[fromText.length - 1] || fallbackStart;

  return {
    start: fallbackStart,
    end: fallbackEnd
  };
}

function extractDateCandidates(values) {
  const hits = [];
  for (const value of values) {
    const text = String(value || "");
    const patterns = [
      /\b(20\d{2})[._-]?(\d{2})[._-]?(\d{2})\b/g,
      /\b(\d{2})(\d{2})(\d{2})\b/g
    ];
    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(text))) {
        if (match[1].length === 4) {
          hits.push(`${match[1]}-${match[2]}-${match[3]}`);
        } else {
          hits.push(`20${match[1]}-${match[2]}-${match[3]}`);
        }
      }
    }
  }
  return [...new Set(hits.map((item) => normalizeTimelineDate(item)).filter(Boolean))].sort();
}

function inspectProjectPathRange(projectPath) {
  if (!projectPath) return { start: "", end: "" };
  const absolutePath = path.join(ROOT, projectPath);
  try {
    const stat = fs.statSync(absolutePath);
    if (stat.isFile()) {
      const baseDate = normalizeTimelineDate(stat.mtime);
      return { start: baseDate, end: baseDate };
    }

    const ignoredNames = new Set([".git", "node_modules", "__pycache__", "dist", "build", ".venv"]);
    const stack = [absolutePath];
    const timestamps = [];
    let scanned = 0;
    while (stack.length && scanned < 400) {
      const current = stack.pop();
      const entries = fs.readdirSync(current, { withFileTypes: true });
      for (const entry of entries) {
        if (ignoredNames.has(entry.name)) continue;
        const fullPath = path.join(current, entry.name);
        if (entry.isDirectory()) {
          stack.push(fullPath);
          continue;
        }
        if (!entry.isFile()) continue;
        const entryStat = fs.statSync(fullPath);
        timestamps.push(entryStat.mtime);
        scanned += 1;
        if (scanned >= 400) break;
      }
    }

    if (!timestamps.length) {
      const folderDate = normalizeTimelineDate(stat.mtime);
      return { start: folderDate, end: folderDate };
    }

    timestamps.sort((left, right) => left.getTime() - right.getTime());
    return {
      start: normalizeTimelineDate(timestamps[0]),
      end: normalizeTimelineDate(timestamps[timestamps.length - 1])
    };
  } catch {
    return { start: "", end: "" };
  }
}

function inferPreviewAssets(projectId) {
  const posterExts = [".jpg", ".jpeg", ".png", ".webp"];
  const videoExts = [".mp4", ".webm"];
  const poster = findAssetPath(path.join(DATA_DIR, "posters"), projectId, posterExts);
  const video = findAssetPath(path.join(DATA_DIR, "previews"), projectId, videoExts);
  return { poster, video };
}

function findAssetPath(folder, fileBase, exts) {
  try {
    const files = fs.readdirSync(folder);
    const match = files.find((file) => {
      const parsed = path.parse(file);
      return parsed.name === fileBase && exts.includes(parsed.ext.toLowerCase());
    });
    if (!match) return "";
    return `/${path.relative(ROOT, path.join(folder, match)).split(path.sep).join("/")}`;
  } catch {
    return "";
  }
}

function defaultSite(owner, links) {
  return {
    brandLabel: "Portfolio Intelligence Atelier",
    heroBadge: "Kakao-style Reference Applied",
    heroTitle: "실무형 AI 프로젝트를 카드 라이브러리처럼 탐색하는 개인 홈페이지",
    heroDescription:
      "넓은 캔버스, 둥근 검색 바, 떠 있는 카드, 블러 모달을 중심으로 구성된 포트폴리오 허브입니다. 비로그인 방문자는 읽기, 로그인 사용자는 댓글, 관리자만 카드 관리 권한을 가집니다.",
    heroNote:
      "관리자 전용 기능: 카드 생성/수정/삭제, 방문자 집계, 댓글 운영, 실제 영상 또는 모션 목업 프리뷰 연결",
    ownerPrimary: owner?.name || "Dowon",
    externalLink: links?.notion || "",
    searchPlaceholder: "프로젝트, 태그, 문제 해결 키워드를 검색하세요",
    footerNote: "실제 영상은 data/previews/{project-id}.mp4 또는 .webm 파일을 두면 자동 연결됩니다."
  };
}

function defaultOwner() {
  return {
    name: "Dowon",
    headline: "AI Product / LLM Portfolio",
    careerSummary: "프로젝트 요약 데이터가 아직 없습니다.",
    focusAreas: []
  };
}

function arrayify(value) {
  return Array.isArray(value)
    ? value.map((item) => String(item)).filter(Boolean)
    : [];
}

async function readJson(filePath, fallback) {
  try {
    const text = await fsp.readFile(filePath, "utf8");
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

async function writeJsonAtomic(filePath, data) {
  const tempPath = `${filePath}.${process.pid}.tmp`;
  await fsp.writeFile(tempPath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  await fsp.rename(tempPath, filePath);
}

async function appendJsonl(filePath, item) {
  await fsp.appendFile(filePath, `${JSON.stringify(item)}\n`, "utf8");
}

function loadEnv() {
  try {
    const raw = fs.readFileSync(ENV_PATH, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const separatorIndex = trimmed.indexOf("=");
      if (separatorIndex === -1) continue;
      const key = trimmed.slice(0, separatorIndex).trim();
      const value = trimmed.slice(separatorIndex + 1).trim();
      if (!(key in process.env)) {
        process.env[key] = value;
      }
    }
  } catch {
    // .env is optional.
  }
}

function parseCookies(header = "") {
  const result = {};
  for (const cookie of header.split(";")) {
    const [name, ...rest] = cookie.trim().split("=");
    if (!name) continue;
    result[name] = decodeURIComponent(rest.join("=") || "");
  }
  return result;
}

function createCookie(name, value, options = {}) {
  const parts = [`${name}=${encodeURIComponent(value)}`];
  if (options.maxAge !== undefined) parts.push(`Max-Age=${options.maxAge}`);
  if (options.httpOnly) parts.push("HttpOnly");
  if (options.sameSite) parts.push(`SameSite=${options.sameSite}`);
  if (options.path) parts.push(`Path=${options.path}`);
  if (options.secure) parts.push("Secure");
  return parts.join("; ");
}

function signPayload(payload) {
  return crypto.createHmac("sha256", SESSION_SECRET).update(payload).digest("base64url");
}

function encodeSession(viewer) {
  const payload = Buffer.from(JSON.stringify(viewer)).toString("base64url");
  return `${payload}.${signPayload(payload)}`;
}

function decodeSession(token) {
  if (!token || !token.includes(".")) return null;
  const [payload, signature] = token.split(".");
  const expected = signPayload(payload);
  if (!signature || signature.length !== expected.length) return null;
  const matches = crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
  if (!matches) return null;
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (!data.exp || Date.now() > data.exp) return null;
    return data;
  } catch {
    return null;
  }
}

function getViewer(req) {
  const cookies = parseCookies(req.headers.cookie || "");
  return decodeSession(cookies[SESSION_COOKIE]);
}

function ensureVisitorCookie(req, res) {
  const cookies = parseCookies(req.headers.cookie || "");
  if (cookies[VISITOR_COOKIE]) return cookies[VISITOR_COOKIE];
  const visitorId = crypto.randomUUID();
  setCookie(res, VISITOR_COOKIE, visitorId, {
    maxAge: 60 * 60 * 24 * 365,
    httpOnly: true,
    sameSite: "Lax",
    path: "/"
  });
  return visitorId;
}

function setCookie(res, name, value, options) {
  const headerValue = createCookie(name, value, options);
  const existing = res.getHeader("Set-Cookie");
  if (!existing) {
    res.setHeader("Set-Cookie", [headerValue]);
    return;
  }
  const cookies = Array.isArray(existing) ? existing : [existing];
  cookies.push(headerValue);
  res.setHeader("Set-Cookie", cookies);
}

function clearCookie(res, name) {
  setCookie(res, name, "", {
    maxAge: 0,
    httpOnly: true,
    sameSite: "Lax",
    path: "/"
  });
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error("JSON body parse failed");
  }
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(payload));
}

function sendText(res, statusCode, message) {
  res.writeHead(statusCode, {
    "Content-Type": "text/plain; charset=utf-8"
  });
  res.end(message);
}

function notFound(res) {
  sendJson(res, 404, { error: "not_found" });
}

function requireAdmin(viewer, res) {
  if (!viewer || viewer.role !== "admin") {
    sendJson(res, 403, { error: "admin_required" });
    return false;
  }
  return true;
}

function requireMember(viewer, res) {
  if (!viewer) {
    sendJson(res, 401, { error: "login_required" });
    return false;
  }
  return true;
}

function sanitizeProjectInput(input, existingProject) {
  const base = normalizeProject(
    {
      ...existingProject,
      ...input,
      tags: typeof input.tags === "string" ? splitByComma(input.tags) : input.tags,
      stack: typeof input.stack === "string" ? splitByComma(input.stack) : input.stack,
      highlights:
        typeof input.highlights === "string"
          ? splitByLine(input.highlights)
          : input.highlights,
      detail: {
        ...(existingProject?.detail || {}),
        ...(input.detail || {})
      },
      preview: {
        ...(existingProject?.preview || {}),
        ...(input.preview || {})
      },
      story: {
        ...(existingProject?.story || {}),
        ...(input.story || {})
      },
      timeline: {
        ...(existingProject?.timeline || {}),
        ...(input.timeline || {})
      }
    },
    0
  );

  const explicitId = String(input.id || existingProject?.id || "").trim();
  if (explicitId) {
    base.id = slugify(explicitId);
  }
  base.updatedAt = new Date().toISOString();
  if (!existingProject?.createdAt) {
    base.createdAt = new Date().toISOString();
  }
  return base;
}

function splitByComma(value) {
  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitByLine(value) {
  return String(value)
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function slugify(value) {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "project";
}

async function loadContent() {
  const content = await readJson(SITE_CONTENT_PATH, null);
  const generated = await readJson(path.join(DATA_DIR, "projects.generated.json"), { projects: [] });

  if (!content) {
    return buildSeedContent();
  }

  const hiddenProjectIds = new Set(arrayify(content.meta?.hiddenProjectIds));
  const visibleGenerated = (generated.projects || []).filter((project) => !hiddenProjectIds.has(project.id));

  return {
    ...content,
    projects: mergeProjectsByStatus(content.projects || [], visibleGenerated).map((project, index) =>
      normalizeProject(project, index)
    ),
    meta: {
      ...(content.meta || {}),
      hiddenProjectIds: [...hiddenProjectIds]
    }
  };
}

async function saveContent(content) {
  await writeJsonAtomic(SITE_CONTENT_PATH, content);
}

async function loadComments() {
  const data = await readJson(COMMENTS_PATH, { comments: [] });
  return Array.isArray(data.comments) ? data.comments : [];
}

async function saveComments(comments) {
  await writeJsonAtomic(COMMENTS_PATH, { comments });
}

async function loadCases() {
  const data = await readJson(path.join(DATA_DIR, "work_cases.json"), { cases: [] });
  return Array.isArray(data.cases) ? data : { cases: [] };
}

async function loadAnalyticsEvents() {
  try {
    const raw = await fsp.readFile(ANALYTICS_PATH, "utf8");
    return raw
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}

function commentCounts(comments) {
  const counts = {};
  for (const comment of comments) {
    counts[comment.projectId] = (counts[comment.projectId] || 0) + 1;
  }
  return counts;
}

function summarizeAnalytics(events, content) {
  const uniqueVisitors = new Set();
  const uniqueLoggedIn = new Set();
  const projectCounts = new Map();
  const surfaceCounts = new Map();
  let authenticatedVisits = 0;
  let anonymousVisits = 0;

  for (const event of events) {
    uniqueVisitors.add(event.visitorId);
    if (event.loggedIn) {
      authenticatedVisits += 1;
      uniqueLoggedIn.add(event.visitorId);
    } else {
      anonymousVisits += 1;
    }
    if (event.projectId) {
      projectCounts.set(event.projectId, (projectCounts.get(event.projectId) || 0) + 1);
    }
    surfaceCounts.set(event.surface || "home", (surfaceCounts.get(event.surface || "home") || 0) + 1);
  }

  const byDay = new Map();
  for (let offset = 6; offset >= 0; offset -= 1) {
    const date = new Date();
    date.setDate(date.getDate() - offset);
    const key = date.toISOString().slice(0, 10);
    byDay.set(key, 0);
  }
  for (const event of events) {
    const key = String(event.timestamp || "").slice(0, 10);
    if (byDay.has(key)) {
      byDay.set(key, (byDay.get(key) || 0) + 1);
    }
  }

  const projectLookup = new Map((content.projects || []).map((project) => [project.id, project]));
  const topProjects = [...projectCounts.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 5)
    .map(([projectId, visits]) => ({
      projectId,
      name: projectLookup.get(projectId)?.name || projectId,
      visits
    }));

  return {
    totalVisits: events.length,
    uniqueVisitors: uniqueVisitors.size,
    uniqueLoggedInVisitors: uniqueLoggedIn.size,
    authenticatedVisits,
    anonymousVisits,
    last7Days: [...byDay.entries()].map(([date, visits]) => ({
      date,
      label: date.slice(5),
      visits
    })),
    surfaces: [...surfaceCounts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5)
      .map(([surface, visits]) => ({ surface, visits })),
    topProjects
  };
}

async function verifyGoogleCredential(credential) {
  if (!GOOGLE_CLIENT_ID) {
    throw new Error("GOOGLE_CLIENT_ID is not configured");
  }
  const endpoint = `https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(credential)}`;
  const response = await fetch(endpoint);
  if (!response.ok) {
    throw new Error("Google credential verification failed");
  }
  const data = await response.json();
  if (data.aud !== GOOGLE_CLIENT_ID) {
    throw new Error("Google client mismatch");
  }
  if (data.email_verified !== "true") {
    throw new Error("Google email is not verified");
  }
  const email = String(data.email || "").toLowerCase();
  if (!email) {
    throw new Error("Email is missing from Google token");
  }
  return {
    email,
    name: data.name || data.given_name || email.split("@")[0],
    picture: data.picture || "",
    role: ADMIN_EMAILS.has(email) ? "admin" : "member"
  };
}

function createViewerSession(profile) {
  const now = Date.now();
  return {
    email: profile.email,
    name: profile.name,
    picture: profile.picture,
    role: profile.role,
    iat: now,
    exp: now + SESSION_TTL_SECONDS * 1000
  };
}

async function handleApi(req, res, url) {
  const viewer = getViewer(req);

  if (req.method === "GET" && url.pathname === "/api/bootstrap") {
    const [content, comments, cases] = await Promise.all([loadContent(), loadComments(), loadCases()]);
    const response = {
      site: content.site,
      owner: content.owner,
      profile: content.profile,
      links: content.links,
      projects: content.projects,
      cases: cases.cases || [],
      commentCounts: commentCounts(comments),
      viewer: viewer
        ? {
            email: viewer.email,
            name: viewer.name,
            picture: viewer.picture,
            role: viewer.role
          }
        : null,
      config: {
        googleClientId: GOOGLE_CLIENT_ID,
        devLoginEnabled: DEV_ALLOW_LOCAL_LOGIN
      }
    };
    sendJson(res, 200, response);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/health") {
    sendJson(res, 200, {
      ok: true,
      service: "portfolio-homepage",
      timestamp: new Date().toISOString()
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/auth/google") {
    try {
      const body = await readBody(req);
      const profile = await verifyGoogleCredential(body.credential || "");
      const session = createViewerSession(profile);
      setCookie(res, SESSION_COOKIE, encodeSession(session), {
        maxAge: SESSION_TTL_SECONDS,
        httpOnly: true,
        sameSite: "Lax",
        path: "/"
      });
      sendJson(res, 200, {
        viewer: {
          email: session.email,
          name: session.name,
          picture: session.picture,
          role: session.role
        }
      });
    } catch (error) {
      sendJson(res, 400, { error: error.message });
    }
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/auth/dev") {
    if (!DEV_ALLOW_LOCAL_LOGIN) {
      sendJson(res, 403, { error: "dev_login_disabled" });
      return;
    }
    const body = await readBody(req);
    const email = String(body.email || DEV_ADMIN_EMAIL || [...ADMIN_EMAILS][0] || "dev@example.com").toLowerCase();
    const session = createViewerSession({
      email,
      name: body.name || "Local Admin",
      picture: "",
      role: ADMIN_EMAILS.has(email) || email === DEV_ADMIN_EMAIL ? "admin" : "member"
    });
    setCookie(res, SESSION_COOKIE, encodeSession(session), {
      maxAge: SESSION_TTL_SECONDS,
      httpOnly: true,
      sameSite: "Lax",
      path: "/"
    });
    sendJson(res, 200, {
      viewer: {
        email: session.email,
        name: session.name,
        picture: session.picture,
        role: session.role
      }
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/logout") {
    clearCookie(res, SESSION_COOKIE);
    sendJson(res, 200, { ok: true });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/comments") {
    const projectId = url.searchParams.get("projectId");
    if (!projectId) {
      sendJson(res, 400, { error: "projectId_required" });
      return;
    }
    const comments = await loadComments();
    const items = comments
      .filter((comment) => comment.projectId === projectId)
      .sort((left, right) => (left.createdAt < right.createdAt ? 1 : -1));
    sendJson(res, 200, { comments: items });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/comments") {
    if (!requireMember(viewer, res)) return;
    const body = await readBody(req);
    const projectId = String(body.projectId || "");
    const message = String(body.message || "").trim();
    if (!projectId) {
      sendJson(res, 400, { error: "projectId_required" });
      return;
    }
    if (!message) {
      sendJson(res, 400, { error: "message_required" });
      return;
    }
    if (message.length > MAX_COMMENT_LENGTH) {
      sendJson(res, 400, { error: "message_too_long" });
      return;
    }
    const content = await loadContent();
    if (!content.projects.some((project) => project.id === projectId)) {
      sendJson(res, 404, { error: "project_not_found" });
      return;
    }
    const comments = await loadComments();
    const comment = {
      id: crypto.randomUUID(),
      projectId,
      message,
      authorName: viewer.name,
      authorEmail: viewer.email,
      authorImage: viewer.picture || "",
      authorRole: viewer.role,
      createdAt: new Date().toISOString()
    };
    comments.push(comment);
    await saveComments(comments);
    sendJson(res, 201, { comment });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/analytics/visit") {
    const visitorId = ensureVisitorCookie(req, res);
    const body = await readBody(req).catch(() => ({}));
    const event = {
      id: crypto.randomUUID(),
      visitorId,
      loggedIn: Boolean(viewer),
      role: viewer?.role || "guest",
      email: viewer?.email || "",
      surface: String(body.surface || "home"),
      projectId: body.projectId ? String(body.projectId) : "",
      referrer: req.headers.referer || "",
      userAgent: req.headers["user-agent"] || "",
      timestamp: new Date().toISOString()
    };
    await appendJsonl(ANALYTICS_PATH, event);
    sendJson(res, 201, { ok: true });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/analytics/summary") {
    if (!requireAdmin(viewer, res)) return;
    const [content, events] = await Promise.all([loadContent(), loadAnalyticsEvents()]);
    sendJson(res, 200, summarizeAnalytics(events, content));
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/projects") {
    if (!requireAdmin(viewer, res)) return;
    const body = await readBody(req);
    const input = body.project || {};
    const content = await loadContent();
    content.meta = content.meta || {};
    content.meta.hiddenProjectIds = arrayify(content.meta.hiddenProjectIds).filter((id) => id !== slugify(input.id || ""));
    const existingIndex = content.projects.findIndex((project) => project.id === slugify(input.id || ""));
    const existingProject = existingIndex >= 0 ? content.projects[existingIndex] : null;
    const project = sanitizeProjectInput(input, existingProject);

    const duplicate = content.projects.find(
      (item) => item.id === project.id && (!existingProject || item.id !== existingProject.id)
    );
    if (duplicate) {
      sendJson(res, 400, { error: "duplicate_project_id" });
      return;
    }

    if (existingIndex >= 0) {
      content.projects[existingIndex] = project;
    } else {
      content.projects.unshift(project);
    }
    await saveContent(content);
    sendJson(res, 200, { project });
    return;
  }

  if (req.method === "DELETE" && url.pathname.startsWith("/api/projects/")) {
    if (!requireAdmin(viewer, res)) return;
    const projectId = decodeURIComponent(url.pathname.replace("/api/projects/", ""));
    const content = await loadContent();
    const nextProjects = content.projects.filter((project) => project.id !== projectId);
    const hiddenIds = new Set(arrayify(content.meta?.hiddenProjectIds));
    const existedInGenerated = await readJson(path.join(DATA_DIR, "projects.generated.json"), { projects: [] });
    const inGenerated = (existedInGenerated.projects || []).some((project) => project.id === projectId);
    if (nextProjects.length === content.projects.length && !inGenerated) {
      sendJson(res, 404, { error: "project_not_found" });
      return;
    }
    content.projects = nextProjects;
    content.meta = content.meta || {};
    if (inGenerated) {
      hiddenIds.add(projectId);
    }
    content.meta.hiddenProjectIds = [...hiddenIds];
    await saveContent(content);
    const comments = await loadComments();
    await saveComments(comments.filter((comment) => comment.projectId !== projectId));
    sendJson(res, 200, { ok: true });
    return;
  }

  notFound(res);
}

async function serveStatic(req, res, url) {
  const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
  const resolvedPath = path.normalize(path.join(ROOT, pathname));
  if (!resolvedPath.startsWith(ROOT)) {
    sendText(res, 403, "forbidden");
    return;
  }

  const ext = path.extname(resolvedPath).toLowerCase();
  const allowedExts = new Set([".html", ".css", ".js", ".jpg", ".jpeg", ".png", ".svg", ".webp", ".mp4", ".webm"]);
  if (!allowedExts.has(ext)) {
    sendText(res, 404, "not found");
    return;
  }

  try {
    const stat = await fsp.stat(resolvedPath);
    if (!stat.isFile()) {
      sendText(res, 404, "not found");
      return;
    }
    const contentType = MIME_TYPES[ext] || "application/octet-stream";
    res.writeHead(200, {
      "Content-Type": contentType,
      "Cache-Control": ext === ".html" ? "no-store" : "public, max-age=300"
    });
    fs.createReadStream(resolvedPath).pipe(res);
  } catch {
    sendText(res, 404, "not found");
  }
}

async function handleRequest(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);

  if (url.pathname.startsWith("/api/")) {
    try {
      await handleApi(req, res, url);
    } catch (error) {
      sendJson(res, 500, {
        error: "internal_server_error",
        detail: error.message
      });
    }
    return;
  }

  await serveStatic(req, res, url);
}

async function main() {
  await ensureStorage();

  if (!process.env.SESSION_SECRET) {
    console.warn("[portfolio-homepage] SESSION_SECRET is not set. Sessions will reset when the server restarts.");
  }
  if (!GOOGLE_CLIENT_ID) {
    console.warn("[portfolio-homepage] GOOGLE_CLIENT_ID is not configured. Google login button will be disabled.");
  }

  const server = http.createServer(handleRequest);
  server.listen(PORT, HOST, () => {
    console.log(`Portfolio homepage running at http://${HOST}:${PORT}`);
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
