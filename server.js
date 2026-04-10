const http = require("http");
const fs = require("fs");
const fsp = require("fs/promises");
const path = require("path");
const crypto = require("crypto");

const ROOT = __dirname;
const DATA_DIR = path.join(ROOT, "data");
const SEED_DATA_DIR = path.join(ROOT, "seed-data");
const SITE_CONTENT_PATH = path.join(DATA_DIR, "site-content.json");
const STATUS_OVERRIDES_PATH = path.join(DATA_DIR, "status_overrides.json");
const COMMENTS_PATH = path.join(DATA_DIR, "comments.json");
const BLOG_POSTS_PATH = path.join(DATA_DIR, "blog-posts.json");
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
const DEFAULT_PUBLIC_EMAIL = "dowonkim0612@naver.com";
const DEFAULT_PROFILE_GITHUB = "https://github.com/Dohwon";
const SITE_CONTENT_SEED_SYNC_VERSION = "2026-03-18-site-v1";
const BLOG_POSTS_SEED_SYNC_VERSION = "2026-03-18-blog-v1";
const DEFAULT_HIDDEN_PROJECT_IDS = new Set([
  "dowon-codex-manager-memory-work-summary-v4",
  "a2a-family-classifier-experts",
  "utterance-similarity-notebook"
]);

const SESSION_COOKIE = "portfolio_session";
const VISITOR_COOKIE = "portfolio_visitor";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;
const MAX_COMMENT_LENGTH = 1000;
const MAX_COMMENT_PASSWORD_LENGTH = 32;
const MAX_COMMENT_NICKNAME_LENGTH = 24;
const MAX_BLOG_MARKDOWN_LENGTH = 50000;

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

const PROJECT_CONTENT_OVERRIDES = {
  "central-memory-prompt-kit": {
    summary: "에이전트 작업기억을 한 장으로 묶는 실험이자, 여러 AI 툴과 사람 협업자가 같은 운영 문서를 재사용할 수 있게 만드는 중앙 메모리 프롬프트 키트.",
    highlights: [
      "오너/스킬/회사 운영 모델을 한 세트로 묶은 프롬프트 상품화",
      "중앙 메모리 + 프로젝트 메모리 + worklog archive 구조 정리",
      "manager memory 요약 실험을 이 카드 안으로 통합"
    ],
    stack: ["Markdown", "Prompt Design", "Node.js", "JSON Schema"],
    tags: ["Central Memory", "Prompt Kit", "Worklog", "AgentOps"],
    detail: {
      readmeSummary: [
        "여러 AI 툴과 사람 협업자 사이에서 손실 없는 인수인계를 만들기 위한 중앙 메모리 프롬프트 키트다.",
        "owner profile, skill profile, company operating model, project rules, worklog archive를 한 세트의 상품처럼 다룬다.",
        "예전 `에이전트 작업기억을 한 장으로 묶는 실험` 카드 내용도 이 카드 안으로 합쳐, manager memory 압축 실험과 work summary 구조를 함께 설명한다."
      ],
      workflow: [
        {
          step: "프로필 구조화",
          desc: "오너 성향, 스킬 역할, 회사 운영 모델을 프롬프트 템플릿으로 정리한다."
        },
        {
          step: "메모리 계층 설계",
          desc: "central memory와 short/mid/long/log 작업기억 구조를 분리하고 연결한다."
        },
        {
          step: "프로젝트 어댑터 연결",
          desc: "프로젝트별 AGENTS 규칙과 memory link를 붙여 실제 협업 흐름으로 이어준다."
        },
        {
          step: "아카이브 상품화",
          desc: "work summary, prompt bundle, skill docs까지 묶어 재사용 가능한 패키지로 정리한다."
        }
      ],
      keyFiles: [
        "projects/260324_central_memory_prompt_kit/README.md",
        "projects/260324_central_memory_prompt_kit/prompts/01_owner_profile_prompt.md",
        "projects/260324_central_memory_prompt_kit/prompts/06_worklog_archive_prompt.md",
        "projects/260324_central_memory_prompt_kit/skill_docs/startup-business-strategist-ko.md",
        "manager_memory/source/work_summary_versions/dowon_codex_manager_memory_work_summary.v6.md"
      ],
      diagramCaption: "owner profile → skill profile → operating model → memory workspace → project rules → worklog archive"
    },
    story: {
      challenge: "툴마다 메모리가 갈라지고, 작업기억 요약 실험과 프롬프트 상품화 문서가 서로 다른 폴더에서 흩어지며 handoff 손실이 커졌다.",
      attempts: [
        "중앙 메모리와 프로젝트 메모리를 분리하되, prompt 세트와 어댑터 구조로 다시 연결했다.",
        "manager memory 요약 실험과 work summary 버전 축적 흐름을 한 카드 안에서 읽히도록 합쳤다.",
        "문서 템플릿을 단순 기록이 아니라 다른 팀도 가져갈 수 있는 prompt product 형태로 재구성했다."
      ],
      resolution: "중앙 메모리 인프라와 프롬프트 상품 레이어를 같은 프로젝트로 묶어, 에이전트 운영 문서를 복제 가능한 자산으로 바꿨다.",
      impact: [
        "툴 간 handoff 손실 감소",
        "작업기억과 worklog archive 구조 통합",
        "재사용 가능한 prompt kit 형태 확보"
      ]
    }
  },
  "calc-stt-cer-colab": {
    summary: "음성 인식 결과를 CER 기준으로 뜯어보며, 왜 성능이 흔들리는지를 숫자로 설명 가능하게 만든 진단 노트북.",
    highlights: [
      "CER 기준으로 인식 품질을 수치화",
      "환경 차이에 따른 성능 흔들림을 비교 가능하게 정리",
      "설명 가능한 품질 회고 자료로 전환"
    ],
    story: {
      challenge: "인식이 왜 떨어졌는지 감으로만 말하면 회의는 길어지고 개선 포인트는 흐려졌다.",
      attempts: [
        "CER 계산 기준을 정리하고 비교 가능한 입력 구조로 맞췄다.",
        "환경별 결과를 같은 기준으로 묶어 흔들리는 구간을 드러냈다.",
        "숫자와 사례를 같이 붙여 설명 자료로 바로 쓸 수 있게 만들었다."
      ],
      resolution: "결국 품질 이슈를 체감이 아니라 수치와 사례로 설명할 수 있게 바꿨다.",
      impact: [
        "품질 흔들림 설명 가능화",
        "환경별 비교 기준 확보",
        "후속 튜닝 우선순위 선명화"
      ]
    }
  },
  "morpheme-analysis-notebook": {
    summary: "학습데이터를 형태소 단위로 해부하고, 비슷한 발화의 경계까지 같이 비교해 표현 다양성과 라벨 흔들림이 어디서 생기는지 잡아내는 분석 노트북.",
    highlights: [
      "형태소 기준 데이터 품질 점검과 발화 유사도 분석을 한 카드로 통합",
      "표현 다양성과 분류 경계가 흔들리는 구간 탐색",
      "말버릇/유사 표현 기반 후속 NLU 개선 포인트 발굴"
    ],
    stack: ["Jupyter", "Python", "NLP", "Cosine Similarity"],
    tags: ["Morphology", "Similarity", "Notebook", "NLU"],
    detail: {
      readmeSummary: [
        "형태소 단위로 학습데이터를 분해해 품질을 점검하고, 동시에 비슷한 발화 쌍의 경계를 유사도 기준으로 읽어보는 분석 노트다.",
        "기존 `비슷한 발화의 차이를 잡아내는 분석 노트` 카드는 이 카드 안으로 합쳐, 형태소 분석과 발화 유사도 실험을 하나의 탐색 축으로 정리했다.",
        "핵심은 '말버릇이 왜 분류를 흔드는가'를 데이터 품질과 유사 표현 비교 두 방향에서 같이 보는 것이다."
      ],
      workflow: [
        {
          step: "형태소 분해",
          desc: "학습데이터를 형태소 단위로 쪼개 빈도와 조합 패턴을 관찰한다."
        },
        {
          step: "유사 발화 비교",
          desc: "비슷한 표현쌍의 거리와 경계를 비교해 라벨 흔들림 후보를 모은다."
        },
        {
          step: "노이즈 구간 추출",
          desc: "표현은 비슷한데 라벨이 갈라지는 지점을 따로 분리한다."
        },
        {
          step: "개선 포인트 정리",
          desc: "사전 보강, 라벨 재정비, NLU 보정 후보로 연결한다."
        }
      ],
      keyFiles: [
        "projects/250731_학습데이터_형태소분석기.ipynb",
        "projects/형태소분석기_기반_사용자_발화_유사도_분석(2).ipynb"
      ],
      diagramCaption: "형태소 분해 → 유사 발화 비교 → 노이즈 구간 추출 → 라벨/사전 개선"
    },
    story: {
      challenge: "데이터가 많아도 왜 분류가 흔들리는지는 토큰 레벨과 유사 발화 경계를 같이 보지 않으면 잘 드러나지 않았다.",
      attempts: [
        "형태소 단위로 자르고 빈도와 조합 패턴을 다시 봤다.",
        "비슷한 발화쌍을 묶어 어떤 표현이 경계를 흔드는지 같이 확인했다.",
        "표현이 비슷한데 라벨이 달라지는 구간을 따로 추렸다.",
        "분류 기준을 다시 세울 수 있게 분석 축을 정리했다."
      ],
      resolution: "표면적인 예시 나열이 아니라, 데이터 구조 자체를 손볼 근거를 만드는 방향으로 바꿨다.",
      impact: [
        "데이터 노이즈 구간 가시화",
        "라벨 재정비 후보 확보",
        "형태소 기반 개선 힌트 축적"
      ]
    }
  },
  "260218-ope-log-anlayze": {
    summary: "운영계 대화 로그를 읽고 끝내지 않고, 실제 기능 우선순위와 품질 개선 backlog로 바꿔내는 분석 프로젝트.",
    highlights: [
      "실패 응답을 제품 개선 과제로 번역",
      "클라우드 동의 퍼널과 미디어 수요를 분리 추출",
      "후속 라벨링과 실험 설계를 위한 failure 샘플 구조화"
    ],
    detail: {
      readmeSummary: [
        "원시 운영 로그를 단순 모니터링 자료가 아니라, 제품 의사결정용 인사이트로 바꾸는 흐름이 핵심인 프로젝트다.",
        "대화 실패를 단순 집계로 끝내지 않고 기능 수요, 전환 퍼널, 품질 이슈 backlog로 재구성했다.",
        "대표 산출물은 business insights 리포트, media feature demand 리포트, failure_by_category/request_failures 데이터셋이다."
      ]
    },
    story: {
      challenge: "운영 로그는 쌓이는데도 무엇을 먼저 고쳐야 하는지, 사용자 불만이 어디에 몰리는지가 한눈에 보이지 않았다.",
      attempts: [
        "CSV/XLSX 로그를 정제해 실패 응답과 요청 유형을 다시 묶었다.",
        "카테고리별 실패와 수요를 분리해 기능 우선순위로 연결했다.",
        "리포트를 바로 backlog와 실험 설계로 이어질 수 있는 형태로 정리했다."
      ],
      resolution: "원시 로그를 읽기 쉬운 보고서가 아니라, 실제 제품 우선순위와 개선 실험으로 연결되는 입력값으로 바꿨다.",
      impact: [
        "클라우드 동의 전환 개선 포인트 식별",
        "미디어 재생 unmet demand 가시화",
        "후속 수동 라벨링과 라우팅 개선 기준 확보"
      ]
    }
  },
  "260315-moe-prompt-routing": {
    summary: "질문 성격에 따라 다른 프롬프트와 실행 경로를 고르는 음성 라우팅 구조를 설계하고, 그 안의 1차 family classifier와 2차 expert 묶음까지 엑셀 기반 회귀 평가로 검증하는 프로젝트.",
    highlights: [
      "1차 family classifier와 2차 expert-system 분리를 한 카드로 통합",
      "632행 회귀 테스트와 judge 평가 체계",
      "latency와 유지보수 공수를 함께 줄이는 라우팅 구조"
    ],
    detail: {
      readmeSummary: [
        "이 프로젝트의 핵심은 음성 요청을 하나의 거대한 시스템 프롬프트로 처리하지 않고, family classifier와 expert prompt로 나눠 다루는 구조다.",
        "기존 `A2A Family Classifier Experts` 카드는 이 프로젝트의 일부 축이었기 때문에, 같은 레포를 가리키는 중복 카드 대신 여기서 함께 설명한다.",
        "라우팅 시트, route_only 모드, judge prompt 분리, retry/에러 격리까지 갖춰서 구조 변경 영향도 추적할 수 있게 만들었다.",
        "manager_memory 기준으로 가장 큰 초점은 schedule/search/default가 섞이며 커지던 복잡도와 latency를 줄이는 것이었다."
      ]
    },
    story: {
      challenge: "검색, 스케줄, 일반 대화가 한 덩어리 프롬프트에 섞일수록 수정할수록 느려지고, 회귀 포인트도 계속 늘어났다.",
      attempts: [
        "1차 family classifier와 2차 expert prompt를 분리해 책임을 쪼갰다.",
        "judge prompt와 routing 결과 시트를 분리해 변경 영향이 어디서 나는지 추적 가능하게 만들었다.",
        "retry, row 단위 에러 격리, route_only 모드까지 넣어 긴 실험도 중단 없이 돌릴 수 있게 했다."
      ],
      resolution: "최종적으로 full pipeline을 분리형 라우팅 구조로 옮겨, 어떤 질문이 왜 그 경로로 갔는지 엑셀과 로그에서 바로 읽히게 만들었다.",
      impact: [
        "신규 기능 추가 시 라우터 수정 최소화",
        "분류만 빠르게 확인하는 검증 루프 확보",
        "routing 결과를 행 단위로 추적하는 운영형 평가 구조 완성"
      ]
    }
  },
  "260317-desktop-scheduler": {
    summary: "Windows 바탕화면에서 바로 실행해 월간 흐름, 주간 카드, 체크리스트를 한 화면에서 관리하려는 데스크 스케줄러.",
    highlights: [
      "월간 달력과 주간 카드 흐름을 같이 보여주는 데스크톱 UI",
      "체크리스트 CRUD와 미루기/보류/언젠가 상태 관리",
      "SQLite 로컬 저장과 Windows 바로가기 실행 경로 정리"
    ],
    stack: ["Python", "Tkinter", "SQLite"],
    tags: ["Scheduler", "Desktop", "Calendar", "Checklist"],
    detail: {
      readmeSummary: [
        "이 프로젝트는 서버 없이 개인 일정과 체크리스트를 로컬에서 바로 관리하는 Windows 데스크톱 스케줄러다.",
        "월간 달력에서 전체 흐름을 보고, 선택 날짜 기준 주간 카드와 세부 목록을 바로 이어서 확인하게 만든 것이 핵심이다.",
        "실행 방식도 중요해서 `.pyw`, `.vbs`, 바탕화면 바로가기까지 묶어 실제 사용 흐름에 맞췄다."
      ]
    },
    story: {
      challenge: "웹 앱처럼 한 단계 더 들어가는 구조는 귀찮고, 데스크톱 앱은 바로 켜지는 대신 흐름과 세부 일정이 분리되기 쉬웠다.",
      attempts: [
        "월간 달력과 주간 카드, 체크리스트 패널을 한 화면에서 이어 보이게 설계했다.",
        "미루기/보류/언젠가 상태와 연기 기록을 넣어 실제 할 일 흐름에 맞췄다.",
        "Windows 바로가기와 무콘솔 실행 경로까지 정리해서 '실제로 쓰는 도구'처럼 마무리했다."
      ],
      resolution: "결국 일정을 저장하는 앱이 아니라, 바탕화면에서 바로 열어 오늘과 이번 주 흐름을 한눈에 보는 개인 운영 도구 쪽으로 방향을 잡았다.",
      impact: [
        "월간-주간-세부 할 일 흐름 통합",
        "로컬 단일 사용자용 빠른 실행 경험 확보",
        "MVP 상태지만 실제 사용 시나리오에 맞는 구조 완성"
      ]
    }
  },
  "a2a-family-classifier-experts": {
    summary: "거대한 시스템 프롬프트를 쪼개서, 1차 family classifier가 경로를 고르고 2차 expert/system이 실제 처리하는 A2A-ready 음성 라우팅 묶음.",
    highlights: [
      "1차 순수 분류기와 2차 순수 처리기의 책임 분리",
      "schedule / general / unsupported / on-device 계층 분리",
      "stage1-only와 judge까지 붙인 회귀 검증 흐름"
    ],
    stack: ["Python", "Prompt Routing", "XLSX Judge"],
    tags: ["A2A", "Classifier", "Experts", "Routing"],
    detail: {
      readmeSummary: [
        "이 카드는 MoE 폴더 전체 중에서도 특히 `1차 family classifier -> 2차 experts/systems`로 정리한 핵심 설계 축만 따로 떼어 본 프로젝트다.",
        "답을 한 번에 잘 만드는 프롬프트보다, 어떤 처리기로 보내야 하는지 먼저 고르는 구조를 분리한 것이 포인트다.",
        "route_only, stage1-only, classifier 시트까지 붙여서 1차 라우팅 품질만 빠르게 보는 루프도 같이 만들고 있다."
      ]
    },
    story: {
      challenge: "기존처럼 큰 시스템 프롬프트 하나에 기능을 계속 붙이면 latency도 늘고, 왜 그 답이 나왔는지 추적도 어려워졌다.",
      attempts: [
        "1차는 `family classifier`로 순수 분류만 하게 두고, 2차는 expert/system이 실제 처리하게 경계를 나눴다.",
        "low confidence일 때만 제한 병렬과 selector를 허용해 무조건 복잡해지지 않게 설계했다.",
        "stage1-only 실행과 classifier 시트로 1차 품질만 빠르게 확인하는 검증 루프를 추가했다."
      ],
      resolution: "결국 프롬프트를 잘 쓰는 문제가 아니라, 음성 요청을 어떤 처리 계층으로 보낼지 먼저 고르는 오케스트레이션 문제로 다시 정의했다.",
      impact: [
        "A2A-ready 구조 초안 고정",
        "1차 라우팅 품질만 보는 빠른 실험 루프 확보",
        "expert 추가 시 전체 프롬프트 재작성 부담 감소"
      ]
    },
    timeline: {
      start: "2026-03-16",
      end: "2026-03-18",
      label: "2026.03",
      difficultyWindows: [
        {
          label: "1차 분류 기준 재정의",
          start: "2026-03-16",
          end: "2026-03-17",
          severity: "high"
        }
      ],
      milestones: [
        {
          label: "stage1-only 실행 루프 추가",
          date: "2026-03-18",
          tone: "success"
        }
      ]
    }
  },
  "operation-log-analyzer": {
    summary: "운영 대화 로그를 정제하고 쪼개고 판정해서, 검색 가능한 형태와 요약 리포트로 다시 만드는 로그 분석 워크벤치.",
    highlights: [
      "운영 로그 전처리와 분할 자동화",
      "judge/search 보조 스크립트로 원인 후보 압축",
      "엑셀 기반 리포트와 분석 산출물 생성"
    ],
    detail: {
      readmeSummary: [
        "로그 전처리, 판정 보조, 요약 리포트 생성이 끊기지 않게 이어지는 분석 툴체인 성격이 강한 프로젝트다.",
        "한 번성 분석이 아니라 반복적으로 로그를 쌓아 비교하고 다시 해석할 수 있게 스크립트를 나눠둔 것이 특징이다."
      ]
    },
    story: {
      challenge: "운영 이슈를 매번 눈으로 찾다 보니 원인 논쟁은 길어지고, 같은 질문도 다시 처음부터 분석하게 됐다.",
      attempts: [
        "로그를 여러 단계로 분할하고 정규화하는 스크립트를 정리했다.",
        "검색/판정 보조 도구로 문제 후보를 빠르게 좁히게 만들었다.",
        "요약 산출물을 다시 사람 손으로 읽을 수 있는 리포트 형태로 묶었다."
      ],
      resolution: "로그를 raw data가 아니라 반복 가능한 분석 루틴으로 바꿔, 같은 문제를 더 빠르게 재현하고 설명할 수 있게 만들었다.",
      impact: [
        "운영 로그 분석 리드타임 단축",
        "반복 가능한 디버깅 입력 데이터 확보",
        "리포트 재사용성과 비교 가능성 향상"
      ]
    }
  },
  "semantic-verb-schema": {
    summary: "흔들리던 한국어 기능 발화를 동사와 엔티티 기준으로 다시 태깅해, 분류 기준 자체를 정비한 스키마 프로젝트.",
    highlights: [
      "entity/verb 자동 태깅과 정합성 보강",
      "non-19 fail 패턴 재판정과 룰 튜닝",
      "weak label 의심 샘플 분리로 검수 포인트 명확화"
    ],
    detail: {
      readmeSummary: [
        "학습데이터의 동사/엔티티 라벨이 흔들리던 문제를 정비하고, 분류 기준 자체를 다시 세우는 작업이 핵심이다.",
        "자동 태깅, strict rule 추가, 재판정 실험, weak label 분리까지 이어지며 데이터 품질을 점진적으로 끌어올렸다."
      ]
    },
    story: {
      challenge: "같은 의도라도 어미와 표현이 조금만 달라지면 기능 분류 기준이 흔들리고, 학습데이터 라벨도 일관되지 않았다.",
      attempts: [
        "핵심 entity와 동사를 자동 태깅해 반복 검수 비용을 줄였다.",
        "strict 룰과 매핑 규칙을 추가해 오매칭 패턴을 다시 잡았다.",
        "weak label 의심 샘플을 따로 분리해 사람이 봐야 할 지점을 줄였다."
      ],
      resolution: "스키마, 규칙, 검수 포인트를 한 번에 정리해서 데이터 정합성을 올리고 이후 튜닝 기준도 더 분명하게 만들었다.",
      impact: [
        "학습데이터 검수 효율 향상",
        "비-19 실패 패턴 재분류 기준 확보",
        "예외 사전 고도화의 기반 마련"
      ]
    }
  },
  "gemini-multiturn-tester-v3": {
    story: {
      challenge: "Postman 같은 단발 테스트만으로는 멀티턴 상태, 응답 스키마 문제, 배치 회귀를 제대로 재현하기 어려웠다.",
      attempts: [
        "대화 히스토리를 포함한 REPL/JSON/XLSX 실행 흐름을 하나로 묶었다.",
        "response schema 제약을 반영해 additionalProperties 문제를 제거했다.",
        "요청/응답 로그를 남겨 턴별 품질 흔들림을 다시 읽을 수 있게 했다."
      ],
      resolution: "단발 확인 도구가 아니라, 멀티턴 시나리오를 반복 검증할 수 있는 테스트 스캐폴드로 바꿨다.",
      impact: [
        "멀티턴 회귀 테스트 가능",
        "엑셀 배치 실행 지원",
        "로그 기반 원인 추적 용이"
      ]
    }
  },
  "todack": {
    summary: "웹, 데스크톱, 모바일이 같은 감정 데이터를 공유하면서도 가볍고 다정한 사용감을 유지하려는 회복 인터페이스 프로젝트.",
    highlights: [
      "여러 클라이언트가 같은 감정 데이터를 공유",
      "작은 입력으로도 계속 남길 수 있는 기록 경험",
      "브랜딩과 제품 경험을 함께 다듬는 진행형 서비스"
    ],
    story: {
      challenge: "감정 기록은 귀찮아지면 바로 끊기기 때문에, 기능을 늘리면서도 입력 부담은 가볍게 유지해야 했다.",
      attempts: [
        "웹/위젯/모바일이 같은 데이터를 보도록 구조를 단순화했다.",
        "브랜딩과 캐릭터 톤을 함께 실험해 기록 진입장벽을 낮췄다.",
        "기록, 요약, 알림 흐름이 끊기지 않게 화면 역할을 분리했다."
      ],
      resolution: "무거운 일기 앱이 아니라, 짧게 남겨도 계속 이어지는 감정 기록 인터페이스 방향을 잡았다.",
      impact: [
        "여러 접점에서 이어지는 감정 기록 경험",
        "브랜드 톤과 제품 기능의 결합",
        "진행중이지만 방향성이 명확한 회복 서비스"
      ]
    }
  },
  "utterance-similarity-notebook": {
    summary: "비슷해 보이는 사용자 발화를 수치로 비교해, 인텐트 경계와 오매칭 구간을 더 선명하게 보려던 유사도 분석 노트북.",
    highlights: [
      "발화 간 거리와 유사도를 수치로 비교",
      "헷갈리는 표현쌍을 분류 기준 관점에서 재해석",
      "인텐트 보조 지표 실험"
    ],
    story: {
      challenge: "사람 눈에는 비슷한데 모델은 다르게 보는 발화가 계속 쌓이면서 분류 기준을 설명하기 어려웠다.",
      attempts: [
        "형태소 기반 특징을 뽑아 발화 간 유사도를 비교했다.",
        "헷갈리는 표현쌍을 묶어 어떤 단어가 경계를 흔드는지 확인했다.",
        "유사도 결과를 분류 보정 힌트로 다시 연결했다."
      ],
      resolution: "단순 예시 비교를 넘어서, 발화 경계를 수치로 읽고 설명할 수 있는 분석 축을 만들었다.",
      impact: [
        "헷갈리는 발화쌍 정리",
        "분류 기준 설명력 향상",
        "후속 NLU 보정 근거 확보"
      ]
    }
  },
  "project-naming-rule": {
    summary: "프로젝트 이름이 첫인상을 망치지 않도록, 날짜·영문명·메모리 경로까지 같이 정리한 네이밍 규칙 문서.",
    highlights: [
      "yymmdd_english_project_name 형식 고정",
      "폴더명과 메모리 경로 규칙을 함께 정리",
      "스킬/프로젝트 운영에서 같은 네이밍 원칙 재사용"
    ],
    stack: ["Markdown", "Naming Rule", "Project Ops"],
    tags: ["Naming", "Rule", "Skill", "Documentation"],
    detail: {
      readmeSummary: [
        "이 카드는 코드 프로젝트라기보다, 프로젝트 이름이 첫인상과 검색성을 좌우한다는 전제에서 만든 네이밍 규칙 문서다.",
        "핵심은 날짜 기준 폴더명, 영문 소문자/숫자/언더스코어 제한, 그리고 project_memory 분리 규칙을 한 번에 고정하는 것이다.",
        "즉, 기능 구현보다 '이름을 어떻게 붙이면 이후 운영과 기억 관리가 덜 꼬이는가'를 다루는 운영 스킬 문서에 가깝다."
      ],
      workflow: [
        { "step": "형식 정의", "desc": "`yymmdd_english_project_name` 형식을 기본 규칙으로 고정한다." },
        { "step": "금지 조건 정리", "desc": "공백, 한글, 특수문자, 제멋대로인 날짜 표기를 막는다." },
        { "step": "메모리 규칙 연결", "desc": "프로젝트 폴더명과 project_memory 경로 규칙을 같이 묶는다." },
        { "step": "운영 재사용", "desc": "새 프로젝트 생성 스크립트와 스킬 문서에서 같은 규칙을 재사용한다." }
      ],
      keyFiles: ["projects/PROJECT_NAMING_RULE.md"],
      diagramCaption: "이름 규칙 정의 → 금지 조건 정리 → 메모리 경로 연결 → 운영 재사용"
    }
  },
  "scripts": {
    summary: "새 프로젝트 생성, 레포 생성·푸시, 자동 동기화, work summary 버전업까지 반복 작업을 덜어주는 자동화 툴박스.",
    highlights: [
      "프로젝트 초기 폴더/README/AGENTS 자동 생성",
      "선택 레포 생성·원격 연결·push 자동화",
      "cron 기반 autosync와 work summary 버전업 스크립트"
    ],
    stack: ["Bash", "Git", "Cron", "GitHub API"],
    tags: ["Automation", "Toolbox", "Scripts", "Ops"],
    detail: {
      readmeSummary: [
        "이 카드는 막연한 scripts 폴더가 아니라, 실제로 반복 작업을 덜기 위해 쓰는 운영 자동화 툴 묶음이다.",
        "`create_project.sh`는 새 프로젝트 기본 구조를 만들고, `create_and_push_selected_repos.sh`는 선택 프로젝트를 GitHub 레포와 연결해 push한다.",
        "`project_repo_autosync.sh`, `install_projects_autosync_cron.sh`, `version_work_summary.sh`는 프로젝트 저장소 동기화와 업무 기록 버전업을 자동화한다."
      ],
      workflow: [
        { "step": "프로젝트 생성", "desc": "README, AGENTS, project_memory까지 포함한 새 프로젝트 기본 구조를 만든다." },
        { "step": "레포 연결", "desc": "선택한 로컬 프로젝트를 GitHub 레포와 연결하고 원격 push를 수행한다." },
        { "step": "자동 동기화", "desc": "변경된 프로젝트를 스캔해 자동 커밋/동기화 흐름을 돌린다." },
        { "step": "기록 버전업", "desc": "work summary 문서를 다음 버전으로 복제해 업무 기록을 축적한다." }
      ],
      keyFiles: [
        "projects/scripts/create_project.sh",
        "projects/scripts/create_and_push_selected_repos.sh",
        "projects/scripts/project_repo_autosync.sh",
        "projects/scripts/install_projects_autosync_cron.sh",
        "projects/scripts/version_work_summary.sh"
      ],
      diagramCaption: "프로젝트 생성 → 레포 연결 → autosync → work summary 버전업"
    }
  },
  "work-summary-versions": {
    summary: "매 세션의 판단과 작업 흔적을 버전별 Markdown으로 축적해, 내 업무 맥락이 어떻게 변했는지 남기는 아카이브.",
    highlights: [
      "업무 기록을 vN 문서로 보존",
      "판단 근거와 진행 상황을 버전 단위로 축적",
      "산출물 중심 아카이브로 남기고 GitHub 링크는 제거"
    ],
    stack: ["Markdown", "Worklog", "Versioning"],
    tags: ["Archive", "Work Summary", "Markdown", "History"],
    detail: {
      readmeSummary: [
        "이 카드는 코드 프로젝트가 아니라, ChatGPT와 함께 남긴 업무 기록을 버전별 Markdown으로 축적한 아카이브다.",
        "핵심은 '이번 판단이 왜 나왔는가'를 v1, v2, ... 식으로 남겨 다음 작업 세션이 앞 문맥을 다시 읽을 수 있게 하는 것이다.",
        "즉 GitHub 코드보다 산출물 자체가 중요한 카드라서, 대표 파일만 남기고 링크는 비우는 방향이 맞다."
      ],
      workflow: [
        { "step": "세션 기록", "desc": "그날의 판단, 작업 범위, 막힌 점을 Markdown으로 정리한다." },
        { "step": "버전 복제", "desc": "기존 summary를 다음 버전으로 복제해 연속성을 유지한다." },
        { "step": "판단 축적", "desc": "변한 전략과 우선순위를 이전 버전과 비교 가능하게 남긴다." },
        { "step": "다음 세션 연결", "desc": "이전 기록을 바로 읽고 이어서 작업할 수 있게 아카이브로 보존한다." }
      ],
      keyFiles: [
        "manager_memory/source/work_summary_versions/dowon_codex_manager_memory_work_summary.v5.md",
        "manager_memory/source/work_summary_versions/dowon_codex_manager_memory_work_summary.v6.md"
      ],
      diagramCaption: "세션 기록 → 버전 복제 → 판단 축적 → 다음 세션 연결"
    }
  },
  "personal-essay-writer-ko": {
    summary: "사용자의 감정, 장면, 말투를 붙잡아 한국어 일기와 에세이를 대신 써주는 창작 스킬 문서.",
    highlights: [
      "일기형/에세이형 출력 모드 분리",
      "감정 온도와 문체 리듬을 먼저 맞추는 작성 규칙",
      "값싼 위로나 상담체를 피하는 문학적 리라이트 스킬"
    ],
    stack: ["Skill Design", "Markdown", "Creative Writing"],
    tags: ["Skill", "Essay", "Diary", "Voice Matching"],
    detail: {
      readmeSummary: [
        "이 카드는 별도 앱이 아니라 `personal-essay-writer-ko` 스킬 자체를 설명하는 문서형 카드다.",
        "핵심은 사용자의 감정, 장면, 말투를 먼저 붙잡고, 그다음 문체와 울림을 맞추는 워크플로우를 만드는 것이다.",
        "일기형과 에세이형 출력 모드를 분리하고, 과한 위로나 상담문체를 피하도록 경계 조건까지 설계했다."
      ],
      workflow: [
        { "step": "요청 분류", "desc": "일기형인지 에세이형인지 먼저 구분한다." },
        { "step": "장면 추출", "desc": "감정, 상황, 기억 장면, 핵심 문장을 뽑아낸다." },
        { "step": "문체 맞춤", "desc": "writing profile을 바탕으로 화자의 리듬과 톤을 반영한다." },
        { "step": "리라이트 점검", "desc": "과장, 싸구려 위로, 타인 목소리 같은 어색함을 걷어낸다." }
      ],
      keyFiles: [
        "skills/Creative Studio/personal-essay-writer-ko/SKILL.md",
        "skills/Creative Studio/personal-essay-writer-ko/references/writing-profile.md"
      ],
      diagramCaption: "요청 분류 → 장면 추출 → 문체 맞춤 → 리라이트 점검"
    }
  }
};

async function ensureStorage() {
  await fsp.mkdir(DATA_DIR, { recursive: true });
  await syncSeedFile("projects.generated.json");

  const existingContent = await readJson(SITE_CONTENT_PATH, null);
  if (!existingContent || isPlaceholderContent(existingContent)) {
    const seeded = await buildSeedContent();
    await writeJsonAtomic(SITE_CONTENT_PATH, seeded);
  }

  try {
    await fsp.access(COMMENTS_PATH);
  } catch {
    await writeJsonAtomic(COMMENTS_PATH, { comments: [] });
  }

  try {
    await fsp.access(BLOG_POSTS_PATH);
  } catch {
    const seededPosts = await readJsonWithFallback("blog-posts.json", { posts: [] });
    await writeJsonAtomic(BLOG_POSTS_PATH, seededPosts || { posts: [] });
  }

  try {
    await fsp.access(STATUS_OVERRIDES_PATH);
  } catch {
    const overrides = await readJsonWithFallback("status_overrides.json", {});
    await writeJsonAtomic(STATUS_OVERRIDES_PATH, overrides || {});
  }

  try {
    await fsp.access(ANALYTICS_PATH);
  } catch {
    await fsp.writeFile(ANALYTICS_PATH, "", "utf8");
  }

  await syncStoredSeedContent();
  await syncStoredSeedBlogPosts();
}

async function syncSeedFile(fileName) {
  const seedPath = path.join(SEED_DATA_DIR, fileName);
  const seedData = await readJson(seedPath, null);
  if (!seedData) return;
  await writeJsonAtomic(path.join(DATA_DIR, fileName), seedData);
}

async function syncStoredSeedContent() {
  const current = await readJson(SITE_CONTENT_PATH, null);
  if (!current || isPlaceholderContent(current)) return;
  if (current.meta?.seedSyncVersion === SITE_CONTENT_SEED_SYNC_VERSION) return;

  const seeded = await readJson(path.join(SEED_DATA_DIR, "site-content.json"), null);
  if (!seeded || !Array.isArray(seeded.projects)) return;

  const hiddenProjectIds = mergeHiddenProjectIds(current.meta?.hiddenProjectIds);
  const projects = appendMissingItemsById(current.projects || [], seeded.projects || [], hiddenProjectIds);

  await writeJsonAtomic(SITE_CONTENT_PATH, {
    ...current,
    projects,
    meta: {
      ...(current.meta || {}),
      hiddenProjectIds: [...hiddenProjectIds],
      seedSyncVersion: SITE_CONTENT_SEED_SYNC_VERSION
    }
  });
}

async function syncStoredSeedBlogPosts() {
  const current = await readJson(BLOG_POSTS_PATH, { posts: [] });
  if (current.meta?.seedSyncVersion === BLOG_POSTS_SEED_SYNC_VERSION) return;

  const seeded = await readJson(path.join(SEED_DATA_DIR, "blog-posts.json"), { posts: [] });
  const posts = appendMissingItemsById(current.posts || [], seeded.posts || []);

  await writeJsonAtomic(BLOG_POSTS_PATH, {
    ...current,
    posts,
    meta: {
      ...(current.meta || {}),
      seedSyncVersion: BLOG_POSTS_SEED_SYNC_VERSION
    }
  });
}

async function buildSeedContent() {
  const generated = await readJsonWithFallback("projects.generated.json", null);
  const manual = await readJsonWithFallback("projects.json", null);
  const primary = generated || manual || {};
  const secondary = manual || {};

  const mergedProjects = mergeProjects(primary.projects || [], secondary.projects || []);
  const owner = {
    ...defaultOwner(),
    ...(primary.owner || {}),
    ...(secondary.owner || {})
  };
  const profile = secondary.profile || primary.profile || {};
  const links = {
    github: DEFAULT_PROFILE_GITHUB,
    ...(primary.links || {}),
    ...(secondary.links || {})
  };

  const hiddenProjectIds = mergeHiddenProjectIds([]);
  return {
    site: defaultSite(owner, links),
    owner,
    profile,
    links,
    projects: mergedProjects
      .filter((project) => !hiddenProjectIds.has(project.id))
      .map((project, index) => normalizeProject(project, index)),
    meta: {
      seededAt: new Date().toISOString(),
      source: generated ? "projects.generated.json" : "projects.json",
      hiddenProjectIds: [...hiddenProjectIds]
    }
  };
}

function isPlaceholderContent(content) {
  if (!content) return true;
  const ownerName = String(content.owner?.name || "");
  const projects = Array.isArray(content.projects) ? content.projects : [];
  const hasProfile = Boolean(content.profile && Object.keys(content.profile).length);
  return ownerName === "Dowon" && projects.length === 0 && !hasProfile;
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

function appendMissingItemsById(existingItems, seedItems, blockedIds = new Set()) {
  const existingList = Array.isArray(existingItems) ? existingItems : [];
  const seedList = Array.isArray(seedItems) ? seedItems : [];
  const existingIds = new Set(
    existingList.map((item) => String(item?.id || slugify(item?.name || item?.title || "item")))
  );
  const nextItems = [...existingList];

  for (const item of seedList) {
    const id = String(item?.id || slugify(item?.name || item?.title || "item"));
    if (!id || existingIds.has(id) || blockedIds.has(id)) continue;
    existingIds.add(id);
    nextItems.push(item);
  }

  return nextItems;
}

function mergeProjectsByStatus(existingProjects, generatedProjects, statusOverrides = {}) {
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
      status: resolveProjectStatus(id, generated.status, project.status, statusOverrides),
      path: project.path || generated.path || "",
      readme: project.readme || generated.readme || "",
      timeline: mergeProjectTimeline(project.timeline, generated.timeline)
    };
  });

  for (const generated of generatedMap.values()) {
    merged.push({
      id: generated.id,
      name: generated.name,
      status: resolveProjectStatus(generated.id, generated.status, generated.status, statusOverrides),
      category: generated.category || "Imported Project",
      summary: "원본 프로젝트에서 상태만 복사한 항목입니다.",
      highlights: [
        `상태: ${resolveProjectStatus(generated.id, generated.status, generated.status, statusOverrides) === "in-progress" ? "진행중" : "완료/운영"}`
      ],
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

function resolveProjectStatus(projectId, generatedStatus, fallbackStatus, statusOverrides) {
  const override = String(statusOverrides?.[projectId] || "").trim();
  if (override === "in-progress" || override === "active") {
    return override;
  }
  return generatedStatus || fallbackStatus || "active";
}

function mergeProjectTimeline(existingTimeline, generatedTimeline) {
  if (!generatedTimeline) return existingTimeline;
  if (!existingTimeline) return generatedTimeline;

  const start = preferEarlierDate(existingTimeline.start, generatedTimeline.start) || existingTimeline.start || generatedTimeline.start || "";
  const end = preferLaterDate(existingTimeline.end, generatedTimeline.end) || generatedTimeline.end || existingTimeline.end || start || "";
  const hasUsableLabel = String(existingTimeline.label || "").trim() && !String(existingTimeline.label || "").includes("기간 입력 필요");
  return {
    ...generatedTimeline,
    ...existingTimeline,
    start,
    end,
    label: buildTimelineLabel(start, end, hasUsableLabel ? existingTimeline.label : (generatedTimeline.label || existingTimeline.label || "")),
    difficultyWindows: Array.isArray(existingTimeline.difficultyWindows) && existingTimeline.difficultyWindows.length
      ? existingTimeline.difficultyWindows
      : (generatedTimeline.difficultyWindows || []),
    milestones: Array.isArray(existingTimeline.milestones) && existingTimeline.milestones.length
      ? existingTimeline.milestones
      : (generatedTimeline.milestones || [])
  };
}

function preferEarlierDate(left, right) {
  const leftDate = toTimelineDate(left);
  const rightDate = toTimelineDate(right);
  if (leftDate && rightDate) {
    return leftDate <= rightDate ? formatDateOnly(leftDate) : formatDateOnly(rightDate);
  }
  return left || right || "";
}

function preferLaterDate(left, right) {
  const leftDate = toTimelineDate(left);
  const rightDate = toTimelineDate(right);
  if (leftDate && rightDate) {
    return leftDate >= rightDate ? formatDateOnly(leftDate) : formatDateOnly(rightDate);
  }
  return right || left || "";
}

function toTimelineDate(value) {
  if (!value) return null;
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDateOnly(value) {
  return value.toISOString().slice(0, 10);
}

function buildTimelineLabel(start, end, fallback = "") {
  const startDate = toTimelineDate(start);
  const endDate = toTimelineDate(end);
  if (!startDate || !endDate) return fallback;
  const left = `${startDate.getUTCFullYear()}.${String(startDate.getUTCMonth() + 1).padStart(2, "0")}`;
  const right = `${endDate.getUTCFullYear()}.${String(endDate.getUTCMonth() + 1).padStart(2, "0")}`;
  return left === right ? left : `${left} - ${right}`;
}

function applyProjectOverride(projectId, project) {
  const override = PROJECT_CONTENT_OVERRIDES[projectId];
  if (!override) return project;

  return {
    ...project,
    ...override,
    detail: {
      ...(project.detail || {}),
      ...(override.detail || {})
    },
    preview: {
      ...(project.preview || {}),
      ...(override.preview || {})
    },
    story: {
      ...(project.story || {}),
      ...(override.story || {})
    },
    timeline: {
      ...(project.timeline || {}),
      ...(override.timeline || {})
    }
  };
}

function mergeHiddenProjectIds(ids) {
  return new Set([...DEFAULT_HIDDEN_PROJECT_IDS, ...arrayify(ids)]);
}

function isGenericSummary(summary) {
  const text = String(summary || "");
  return text.includes("프로젝트 자산") || text.includes("단일 파일 실험/분석 자산");
}

function hasWeakHighlights(highlights) {
  const items = arrayify(highlights);
  return !items.length || (items.length === 1 && items[0].includes("기본 요약")) || (items.length === 1 && items[0].includes("파일 기반 실험"));
}

function buildHumanSummary(project) {
  const category = String(project.category || "");
  const pathText = `${project.path || ""} ${project.name || ""}`.toLowerCase();

  if (category === "Speech Quality Metrics") {
    return "음성 인식 결과를 오류율 기준으로 다시 읽어보며 품질 흔들림을 수치로 확인하는 실험 노트.";
  }
  if (category === "NLU Data Analysis") {
    return "학습데이터를 형태소 단위로 분해해 품질과 패턴을 점검하는 분석 노트.";
  }
  if (category === "NLU Similarity Analysis") {
    return "비슷해 보이는 사용자 발화의 차이를 형태소와 유사도로 비교하는 실험 노트.";
  }
  if (category === "General" && pathText.includes("scripts")) {
    return "반복 작업을 줄이기 위해 자주 쓰는 생성/정리 스크립트를 모아둔 자동화 도구 모음.";
  }
  if (category === "General" && pathText.includes("naming")) {
    return "프로젝트 이름이 첫인상을 망치지 않도록 규칙을 정리한 네이밍 실험 문서.";
  }
  if (category === "General" && pathText.includes("work_summary")) {
    return "작업 기록과 판단 근거를 버전별로 남기며 개선 흐름을 축적한 아카이브.";
  }
  if (category === "General" && pathText.includes("manager_memory")) {
    return "에이전트 작업 메모리를 한 장의 요약 구조로 압축해보는 실험 문서.";
  }
  return "파일과 산출물을 바탕으로 실제 작업 흐름을 다시 읽을 수 있게 정리한 프로젝트 자산.";
}

function buildHumanHighlights(project) {
  const category = String(project.category || "");

  if (category === "Speech Quality Metrics") {
    return ["CER 기준 품질 점검", "음성 인식 오류 패턴 확인", "실험 결과 수치화"];
  }
  if (category === "NLU Data Analysis") {
    return ["형태소 단위 데이터 관찰", "학습데이터 품질 점검", "분석 노트 기반 실험"];
  }
  if (category === "NLU Similarity Analysis") {
    return ["발화 간 유사도 비교", "형태소 특징 실험", "분류 보조 지표 탐색"];
  }
  if (category === "General") {
    return ["핵심 파일과 산출물 정리", "작업 흐름 복기", "다음 개선 포인트 추적"];
  }
  return arrayify(project.tags).slice(0, 3);
}

function normalizeProject(project, index) {
  const id = project.id || slugify(project.name || `project-${index + 1}`);
  const enriched = applyProjectOverride(id, project);
  const summary = isGenericSummary(enriched.summary) ? buildHumanSummary(enriched) : enriched.summary;
  const highlights = hasWeakHighlights(enriched.highlights) ? buildHumanHighlights(enriched) : enriched.highlights;
  const previewAssets = inferPreviewAssets(id);
  const normalizedSource = {
    ...enriched,
    summary,
    highlights
  };
  const detail = normalizeDetail(normalizedSource.detail, normalizedSource);
  const preview = normalizePreview(normalizedSource.preview, normalizedSource, previewAssets);
  const story = normalizeStory(normalizedSource.story, normalizedSource);
  const timeline = normalizeTimeline(normalizedSource.timeline, normalizedSource);

  return {
    id,
    name: String(normalizedSource.name || `Project ${index + 1}`),
    status: normalizedSource.status === "in-progress" ? "in-progress" : "active",
    category: String(normalizedSource.category || "General"),
    summary: String(normalizedSource.summary || "요약 정보가 아직 없습니다."),
    highlights: arrayify(normalizedSource.highlights),
    stack: arrayify(normalizedSource.stack),
    tags: arrayify(normalizedSource.tags),
    links:
      normalizedSource.links && typeof normalizedSource.links === "object"
        ? normalizedSource.links
        : {},
    pinned: Boolean(normalizedSource.pinned),
    manualOrder:
      normalizedSource.manualOrder !== null &&
      normalizedSource.manualOrder !== undefined &&
      normalizedSource.manualOrder !== "" &&
      Number.isFinite(Number(normalizedSource.manualOrder))
      ? Number(normalizedSource.manualOrder)
      : null,
    path: String(normalizedSource.path || ""),
    readme: normalizedSource.readme ? String(normalizedSource.readme) : "",
    detail,
    preview,
    story,
    timeline,
    createdAt: normalizedSource.createdAt || new Date().toISOString(),
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
    heroBadge: "",
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
    publicEmail: DEFAULT_PUBLIC_EMAIL,
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

async function readJsonWithFallback(fileName, fallback) {
  const primaryPath = path.join(DATA_DIR, fileName);
  const fallbackPath = path.join(SEED_DATA_DIR, fileName);
  const primary = await readJson(primaryPath, null);
  if (primary) return primary;
  return readJson(fallbackPath, fallback);
}

async function writeJsonAtomic(filePath, data) {
  const tempPath = `${filePath}.${process.pid}.${Date.now()}.${Math.random().toString(36).slice(2, 8)}.tmp`;
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

function isLoopbackAddress(value = "") {
  const normalized = String(value || "").replace(/^::ffff:/, "");
  return normalized === "127.0.0.1" || normalized === "::1" || normalized === "localhost";
}

function isLocalRequest(req) {
  const hostHeader = String(req.headers.host || "").split(":")[0].toLowerCase();
  return isLoopbackAddress(hostHeader) || isLoopbackAddress(req.socket?.remoteAddress || "");
}

function isDevLoginAllowed(req) {
  return DEV_ALLOW_LOCAL_LOGIN && isLocalRequest(req) && Boolean(DEV_ADMIN_EMAIL || ADMIN_EMAILS.size);
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

function normalizeDisplayPayload(value) {
  if (typeof value === "string") {
    return value.replace(/ -> /g, " → ");
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeDisplayPayload(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, normalizeDisplayPayload(item)])
    );
  }
  return value;
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

function sanitizeBlogPostInput(input, existingPost, refreshUpdatedAt = true) {
  const explicitId = String(input.id || existingPost?.id || "").trim();
  const createdAt = existingPost?.createdAt || input.createdAt || new Date().toISOString();
  const updatedAt = refreshUpdatedAt
    ? new Date().toISOString()
    : input.updatedAt || existingPost?.updatedAt || createdAt;
  return {
    id: slugify(explicitId || input.title || "blog-post"),
    title: String(input.title || existingPost?.title || "").trim() || "제목 없는 글",
    excerpt: String(input.excerpt || existingPost?.excerpt || "").trim(),
    markdown: String(input.markdown || existingPost?.markdown || ""),
    status: String(input.status || existingPost?.status || "published") === "draft" ? "draft" : "published",
    tags: Array.isArray(input.tags)
      ? arrayify(input.tags)
      : typeof input.tags === "string"
        ? splitByComma(input.tags)
        : arrayify(existingPost?.tags),
    createdAt,
    updatedAt
  };
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
  const generated = await readJsonWithFallback("projects.generated.json", { projects: [] });
  const statusOverrides = await readJsonWithFallback("status_overrides.json", {});

  if (!content || isPlaceholderContent(content)) {
    return buildSeedContent();
  }

  const hiddenProjectIds = mergeHiddenProjectIds(content.meta?.hiddenProjectIds);
  const visibleGenerated = (generated.projects || []).filter((project) => !hiddenProjectIds.has(project.id));
  const owner = {
    ...defaultOwner(),
    ...(content.owner || {})
  };
  const links = {
    github: DEFAULT_PROFILE_GITHUB,
    ...(content.links || {})
  };

  return {
    ...content,
    site: {
      ...defaultSite(owner, links),
      ...(content.site || {}),
      heroBadge: ""
    },
    owner,
    links,
    projects: mergeProjectsByStatus(content.projects || [], visibleGenerated, statusOverrides)
      .filter((project) => !hiddenProjectIds.has(project.id))
      .map((project, index) => normalizeProject(project, index)),
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

async function loadBlogPosts() {
  const data = await readJson(BLOG_POSTS_PATH, { posts: [] });
  const posts = Array.isArray(data.posts) ? data.posts : [];
  return posts
    .map((post) => sanitizeBlogPostInput(post, post, false))
    .sort((left, right) => String(right.updatedAt || "").localeCompare(String(left.updatedAt || "")));
}

async function saveBlogPosts(posts) {
  const current = await readJson(BLOG_POSTS_PATH, {});
  await writeJsonAtomic(BLOG_POSTS_PATH, {
    ...current,
    posts
  });
}

async function loadCases() {
  const data = await readJsonWithFallback("work_cases.json", { cases: [] });
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
    if (!comment.projectId) continue;
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
    const [content, comments, cases, blogPosts] = await Promise.all([
      loadContent(),
      loadComments(),
      loadCases(),
      loadBlogPosts()
    ]);
    const response = {
      site: content.site,
      owner: content.owner,
      profile: content.profile,
      links: content.links,
      projects: content.projects,
      cases: cases.cases || [],
      blogPosts,
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
        devLoginEnabled: isDevLoginAllowed(req)
      }
    };
    sendJson(res, 200, normalizeDisplayPayload(response));
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
    if (!isDevLoginAllowed(req)) {
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
      .sort((left, right) => (left.createdAt < right.createdAt ? 1 : -1))
      .map((comment) => ({
        ...comment,
        password: viewer?.role === "admin" ? String(comment.password || "") : ""
      }));
    sendJson(res, 200, { comments: items });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/blog-comments") {
    const blogId = url.searchParams.get("blogId");
    if (!blogId) {
      sendJson(res, 400, { error: "blogId_required" });
      return;
    }
    const posts = await loadBlogPosts();
    if (!posts.some((post) => post.id === blogId)) {
      sendJson(res, 404, { error: "blog_not_found" });
      return;
    }
    const comments = await loadComments();
    const items = comments
      .filter((comment) => comment.blogId === blogId)
      .sort((left, right) => (left.createdAt < right.createdAt ? 1 : -1))
      .map((comment) => ({
        ...comment,
        password: viewer?.role === "admin" ? String(comment.password || "") : ""
      }));
    sendJson(res, 200, { comments: items });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/comments") {
    const body = await readBody(req);
    const projectId = String(body.projectId || "");
    const message = String(body.message || "").trim();
    const password = String(body.password || "").trim();
    const nickname = String(body.nickname || "").trim();
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
    if (password.length > MAX_COMMENT_PASSWORD_LENGTH) {
      sendJson(res, 400, { error: "password_too_long" });
      return;
    }
    if (!viewer && !nickname) {
      sendJson(res, 400, { error: "nickname_required" });
      return;
    }
    if (nickname.length > MAX_COMMENT_NICKNAME_LENGTH) {
      sendJson(res, 400, { error: "nickname_too_long" });
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
      authorName: viewer?.name || nickname,
      authorEmail: viewer?.email || "",
      authorImage: viewer?.picture || "",
      authorRole: viewer?.role || "guest",
      password,
      createdAt: new Date().toISOString()
    };
    comments.push(comment);
    await saveComments(comments);
    sendJson(res, 201, { comment });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/blog-comments") {
    const body = await readBody(req);
    const blogId = String(body.blogId || "");
    const message = String(body.message || "").trim();
    const password = String(body.password || "").trim();
    const nickname = String(body.nickname || "").trim();
    if (!blogId) {
      sendJson(res, 400, { error: "blogId_required" });
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
    if (password.length > MAX_COMMENT_PASSWORD_LENGTH) {
      sendJson(res, 400, { error: "password_too_long" });
      return;
    }
    if (!viewer && !nickname) {
      sendJson(res, 400, { error: "nickname_required" });
      return;
    }
    if (nickname.length > MAX_COMMENT_NICKNAME_LENGTH) {
      sendJson(res, 400, { error: "nickname_too_long" });
      return;
    }
    const posts = await loadBlogPosts();
    if (!posts.some((post) => post.id === blogId)) {
      sendJson(res, 404, { error: "blog_not_found" });
      return;
    }
    const comments = await loadComments();
    const comment = {
      id: crypto.randomUUID(),
      projectId: "",
      blogId,
      message,
      authorName: viewer?.name || nickname,
      authorEmail: viewer?.email || "",
      authorImage: viewer?.picture || "",
      authorRole: viewer?.role || "guest",
      password,
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
    const existedInGenerated = await readJsonWithFallback("projects.generated.json", { projects: [] });
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

  if (req.method === "POST" && url.pathname === "/api/blog") {
    if (!requireAdmin(viewer, res)) return;
    const body = await readBody(req);
    const input = body.blogPost || {};
    const posts = await loadBlogPosts();
    const targetId = slugify(input.id || input.title || "");
    const existingIndex = posts.findIndex((post) => post.id === targetId);
    const existingPost = existingIndex >= 0 ? posts[existingIndex] : null;
    const blogPost = sanitizeBlogPostInput(input, existingPost, true);

    if (!blogPost.title.trim()) {
      sendJson(res, 400, { error: "title_required" });
      return;
    }
    if (!blogPost.excerpt.trim()) {
      sendJson(res, 400, { error: "excerpt_required" });
      return;
    }
    if (blogPost.markdown.length > MAX_BLOG_MARKDOWN_LENGTH) {
      sendJson(res, 400, { error: "markdown_too_long" });
      return;
    }

    const duplicate = posts.find((post) => post.id === blogPost.id && (!existingPost || post.id !== existingPost.id));
    if (duplicate) {
      sendJson(res, 400, { error: "duplicate_blog_id" });
      return;
    }

    if (existingIndex >= 0) {
      posts[existingIndex] = blogPost;
    } else {
      posts.unshift(blogPost);
    }
    await saveBlogPosts(posts);
    sendJson(res, 200, { blogPost });
    return;
  }

  if (req.method === "DELETE" && url.pathname.startsWith("/api/blog/")) {
    if (!requireAdmin(viewer, res)) return;
    const blogId = decodeURIComponent(url.pathname.replace("/api/blog/", ""));
    const posts = await loadBlogPosts();
    const nextPosts = posts.filter((post) => post.id !== blogId);
    if (nextPosts.length === posts.length) {
      sendJson(res, 404, { error: "blog_not_found" });
      return;
    }
    await saveBlogPosts(nextPosts);
    const comments = await loadComments();
    await saveComments(comments.filter((comment) => comment.blogId !== blogId));
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
    const noStoreStatic = new Set([".html", ".css", ".js"]);
    res.writeHead(200, {
      "Content-Type": contentType,
      "Cache-Control": noStoreStatic.has(ext) ? "no-store" : "public, max-age=300"
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
