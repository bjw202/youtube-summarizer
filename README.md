# YouTube Summarizer

> Claude Code 기반 YouTube 영상 자막 요약기. 영상 하나로 Markdown + HTML 비주얼 요약을 자동 생성합니다.

## 설치

Claude Code를 열고 이 문장을 붙여 넣으세요: `https://github.com/bjw202/youtube-summarizer 를 설치해줘. README의 AI 설치 안내대로`

## AI 설치 안내 (For AI agents)

Follow these steps in order. Works on macOS, Linux and Windows (PowerShell or Git Bash) — the commands are the same on every OS unless a step says otherwise.

Rules:
- **Never use administrator rights**: no `sudo`, no "Run as administrator", no system package managers (`brew`, `apt`, `winget`, `choco`) and no `pip install` outside the project. Everything installs into the project folder (`.venv`) and the user's own folders.
- **Ask the user exactly one question** — step 5 (speech recognition). Do not ask anything else.
- **If a step fails, do not improvise another way.** Retry only where a step says so, then stop and report the step, the command, and its full output to the user.

### 1. Clone

```bash
git clone https://github.com/bjw202/youtube-summarizer.git
cd youtube-summarizer
```

If a `youtube-summarizer` folder already exists and is a clone of this repository, use it as is (do not delete it). Run every later command **from this folder**.

- Check: the file `.claude/skills/youtube-visual-summary/SKILL.md` exists.
- Success: you are inside the cloned folder.

### 2. uv

Check whether uv is installed:

```bash
uv --version
```

If that fails, install uv for the user (no admin rights needed):

- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Then open a new shell and run `uv --version` again. If the new shell still cannot find `uv`, call the same binary by its install path for the rest of this guide: `~/.local/bin/uv` (macOS/Linux) or `$env:USERPROFILE\.local\bin\uv.exe` (Windows PowerShell).

- Check: `uv --version`
- Success: it prints a version such as `uv 0.x.y`.

### 3. Install

```bash
uv run .claude/skills/youtube-visual-summary/scripts/install.py
```

Creates `.venv` with Python 3.12 (uv downloads it if needed) and installs yt-dlp, Pillow, ffmpeg (a static build, only when the system has none) and deno (JS runtime) into it. Safe to run more than once.

- Check: the last lines start with `OK — <os>` and the command exits with code 0.
- Success: `OK`. If it prints `NOT READY`, continue with step 4 — it tells you what to fix.

### 4. Check and fix

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/doctor.py --json
```

For every entry under `"checks"` whose `"ok"` is `false`, run its `"fix"` command from the project folder, then run `doctor.py --json` again. Repeat at most **2 times**. If an entry has `"fix": null`, show its `"hint"` to the user. Ignore `"optional"` here (that is step 5).

If any check is still `false` after 2 retries, stop and report those entries (`missing`, `fix`, `hint`) to the user exactly as printed.

- Check: the top-level `"ok"` in the JSON.
- Success: `"ok": true` (and `"features"` → `"summary"` → `"ok": true`).

### 5. Speech recognition (ask the user)

Ask the user this one question: *"Install local speech recognition for videos that have no captions? It downloads about 1.5 GB."*

If yes:

```bash
uv run .claude/skills/youtube-visual-summary/scripts/install.py --with-stt
```

(Apple Silicon Macs get mlx-whisper; other computers get faster-whisper. The model is downloaded once.)

- Check: `doctor.py --json` → `"optional"` → `"stt"` → `"ok"`.
- Success: `true`. If no, skip this step — it can be added later with the same command.

### 6. Tell the user how to start

Tell the user, in their language:

> Open a terminal and run `cd <full path of the youtube-summarizer folder> && claude`, then paste a YouTube link (for example: `이 영상 요약해줘: https://www.youtube.com/watch?v=...`).

(On Windows PowerShell 5, which has no `&&`, give the two commands on separate lines: `cd <folder>` then `claude`.)

Success: the user has the folder path and the command.


## 원리

### 파이프라인 전체 흐름

```
YouTube URL
   │
   ▼
┌─────────────────────────────┐
│  Phase 1  입력 파싱          │  URL → 요약 수준(short/normal/detailed) + 출력 형식
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Phase 2  환경 준비          │  .venv 생성, yt-dlp · ffmpeg 확인
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Phase 3  데이터 수집        │  yt-dlp로 메타데이터 + 자막(ko→en 순) 다운로드
│                              │  → 트랜스크립트 JSON 빌드
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Phase 4  콘텐츠 분석        │  Claude가 트랜스크립트 분석 → 챕터 분할
│          (Claude 직접 수행)   │  chapters.codex.json 생성
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Phase 5  비주얼 처리        │  영상 다운로드 → 프레임 추출 → Contact Sheet 생성
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Phase 6  프레임 선택        │  Claude가 Contact Sheet 분석 → 대표 프레임 선정
│          (Claude 직접 수행)   │  selected-frames.json 생성
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Phase 7  출력 렌더링        │  summary.md + summary.html + images/ 생성
└─────────────────────────────┘
```

### 핵심 개념

| 개념 | 설명 |
|------|------|
| **Gaussian Splat** | 단일 이미지나 비디오에서 생성하는 3D 포인트 클라우드 기반 표현 방식 |
| **자막 우선순위** | 수동 한국어 > 수동 영어 > 자동 생성 > 다른 언어 |
| **챕터 분할** | 트랜스크립트 타임스탬프를 기준으로 의미 단위로 분할 |
| **요약 수준** | `short`(1-2 bullets), `normal`(2-4), `detailed`(6-10, 상세 노트) |
| **프레임 선택** | 시맨틱 매치 → 정보 가치 → 가독성 → 선명도 → 특이성 순 평가 |

## 프로젝트 구조

```
youtube-summarizer/
├── .claude/
│   ├── agents/
│   │   └── youtube-summarizer.md     # 에이전트 정의
│   ├── skills/
│   │   └── youtube-visual-summary/
│   │       ├── SKILL.md               # 스킬 정의 (워크플로우 전체 기술)
│   │       ├── scripts/               # Python 스크립트 모음
│   │       │   ├── setup_venv.py      # 가상환경 생성 (uv 우선, pip 폴백)
│   │       │   ├── env_check.py       # 필수 도구(yt-dlp, ffmpeg) 확인
│   │       │   ├── fetch_youtube.py   # 메타데이터 + 자막 다운로드
│   │       │   ├── build_transcript.py# 자막 → 트랜스크립트 JSON 변환
│   │       │   ├── fetch_frame_source.py  # 영상 파일 다운로드
│   │       │   ├── extract_frames.py  # ffmpeg로 프레임 추출
│   │       │   ├── make_contact_sheets.py # 프레임 → Contact Sheet 이미지
│   │       │   ├── render_markdown.py # chapters.codex.json → summary.md
│   │       │   └── render_html.py     # HTML 템플릿 기반 렌더링
│   │       ├── assets/
│   │       │   ├── html-template.html # HTML 출력 템플릿
│   │       │   └── markdown-template.md
│   │       └── references/
│   │           ├── summary-levels.md  # 요약 수준 가이드
│   │           ├── frame-selection-rubric.md  # 프레임 선택 기준
│   │           ├── troubleshooting.md # 에러 해결 가이드
│   │           └── workflow.md
│   └── settings.json
├── runs/                              # ← 요약 결과물 (영상별 디렉토리)
│   └── YYYY-MM-DD_HHMMSS_영상슬러그/
│       ├── summary.md                 # Markdown 요약
│       ├── summary.html               # HTML 요약
│       ├── images/                    # 챕터별 대표 프레임
│       │   ├── chapter-01.jpg
│       │   ├── chapter-02.jpg
│       │   └── ...
│       └── _work/                     # 중간 작업 파일 (gitignore)
│           ├── metadata.json          # 영상 메타데이터
│           ├── transcript.json        # 타임스탬프+텍스트 세그먼트
│           ├── chapters.codex.json    # 챕터 분할 결과
│           ├── selected-frames.json   # 프레임 선택 결과
│           ├── captions/              # 원본 자막 파일 (.vtt)
│           ├── frames/                # 추출된 후보 프레임 + manifest.json(후보 목록·버린 전환)
│           ├── contact-sheets/        # Contact Sheet 이미지
│           ├── timing.log             # 단계별 시작·끝 시각 (timing.py)
│           ├── clean_run.log          # 원본 영상 정리 기록 (clean_run.py)
│           └── frame-source.mp4       # 다운로드한 원본 영상 (Phase 9에서 지움)
├── tests/                             # 자동 시험 (가짜 run으로 설치·그리기 확인)
├── .github/workflows/                 # 맥·윈도우·리눅스 자동 시험
├── CLAUDE.md                          # Claude Code 프로젝트 지침
├── CHANGELOG.md                       # 변경 이력
├── LICENSE                            # MIT
└── README.md                          # ← 이 파일
```

## 사용법

### 사전 요구사항

- **Claude Code** (CLI 또는 데스크톱 앱)
- **Python 3.11+**
- **ffmpeg / ffprobe** (Homebrew 등으로 설치)
- **인터넷 연결** (YouTube 자막·영상 다운로드용)

### 실행

Claude Code 프롬프트에 YouTube URL과 함께 요약을 요청합니다:

```
이 영상 상세 요약해줘: https://youtu.be/dlbU7kZmlwY
```

또는 스킬을 직접 호출:

```
/youtube-visual-summary https://youtu.be/dlbU7kZmlwY
```

### 요약 수준 지정

| 입력 예시 | 수준 | 설명 |
|-----------|------|------|
| "핵심만", "짧게" | `short` | 챕터당 1-2 불릿 |
| "요약해줘" (기본) | `normal` | 챕터당 2-4 불릿 |
| "상세히", "자세히" | `detailed` | 챕터당 6-10 불릿, 상세 노트 |

### 출력 예시

`runs/` 디렉토리에 타임스탬프 기반 폴더가 생성됩니다:

```
runs/2026-06-09_134540_how-to-create-an-interactive-3d-gaussian-splat-from-1-image-2026/
├── summary.md          ← Markdown 요약 (챕터별 제목, 불릿, 프레임 이미지 포함)
├── summary.html        ← HTML 요약 (인터랙티브 웹 페이지)
└── images/             ← 챕터별 대표 프레임
    ├── chapter-01.jpg
    └── ...
```

## 스크립트 개별 사용

Python 스크립트를 직접 실행할 수도 있습니다:

```bash
# 1. 설치 (위 "설치" 절과 같음)
uv run .claude/skills/youtube-visual-summary/scripts/install.py

# 2. 환경 확인
uv run python .claude/skills/youtube-visual-summary/scripts/env_check.py --json

# 3. 메타데이터 + 자막 다운로드
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_youtube.py "URL" --run-root runs

# 4. 트랜스크립트 빌드
uv run python .claude/skills/youtube-visual-summary/scripts/build_transcript.py runs/RUN_DIR

# 5. 프레임 추출 (비주얼 요약용)
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py runs/RUN_DIR
uv run python .claude/skills/youtube-visual-summary/scripts/extract_frames.py runs/RUN_DIR
uv run python .claude/skills/youtube-visual-summary/scripts/make_contact_sheets.py runs/RUN_DIR

# 6. 출력 렌더링
uv run python .claude/skills/youtube-visual-summary/scripts/render_markdown.py runs/RUN_DIR
uv run python .claude/skills/youtube-visual-summary/scripts/render_html.py runs/RUN_DIR
```

## 자막 정책

- **우선순위**: 수동 한국어 > 수동 영어 > 자동 생성 > 다른 언어
- **429 에러**: HTTP 429 (Too Many Requests) 발생 시 지수 백오프로 최대 2회 재시도
- **부분 성공 허용**: 하나의 언어라도 다운로드되면 워크플로우 계속 진행
- **멱등 재실행**: 동일 URL 기존 run이 있으면 누락분만 재시도

## 에러 처리

| 상황 | 대응 |
|------|------|
| 자막 없음 | 텍스트 전용 모드 전환, STT 제안 |
| 429 Rate Limit | 지수 백오프 재시도 후 성공한 언어로 계속 |
| 프레임 추출 실패 | 텍스트 전용으로 진행 |
| yt-dlp 실패 | 네트워크/권한 안내 |
| JS 런타임 없음 | deno/node 설치 안내 |

## 기술 스택

- **런타임**: Python 3.11+ (`.venv` 격리)
- **패키지 관리**: uv 우선, pip 폴백
- **영상 처리**: yt-dlp (자막·영상 다운로드), ffmpeg (프레임 추출)
- **AI 분석**: Claude (챕터 분할, 프레임 선택)
- **출력**: Jinja2 기반 Markdown/HTML 템플릿

## 라이선스

MIT
