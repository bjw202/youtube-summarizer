# YouTube 영상 요약 하네스 구축 프롬프트

아래 "프롬프트 본문" 구획의 내용을 복사해서 `/harness` 스킬에 입력하세요.

---

## 프롬프트 본문

YouTube 공개 영상의 자막 기반 비주얼 요약을 수행하는 하네스를 구축해줘.

### 참고 구현

`<Codex 원본 저장소>/skills/youtube-visual-summary/` 경로에 Codex용으로 이미 구현된 동일 기능의 하네스가 있어. 이걸 Claude Code용으로 포팅하면서 아래 변경사항을 반영해:

1. **Codex 하네스의 핵심 스크립트 9개를 그대로 가져와서** `.claude/skills/youtube-visual-summary/scripts/` 에 번들링해:

   - `common.py` — 공통 유틸리티 (JSON 읽기/쓰기, 타임스탬프 포맷, 실행 파일 탐색, 슬러그화)
   - `setup_venv.py` — 프로젝트 루트 `.venv` 생성/업데이트 (uv 우선, pip 폴백)
   - `env_check.py` — 필수 도구(yt-dlp, ffmpeg, ffprobe) 및 Python 패키지 확인
   - `fetch_youtube.py` — yt-dlp로 메타데이터+자막 다운로드, run 디렉토리 생성
   - `build_transcript.py` — VTT 자막 파싱 → `transcript.json` 생성 (롤링 자막 병합 포함)
   - `fetch_frame_source.py` — 저해상도(720p 이하) 비디오 전용 스트림 다운로드
   - `extract_frames.py` — 챕터별 후보 프레임 추출 (기본 8프레임/챕터)
   - `make_contact_sheets.py` — Pillow로 프레임 그리드(contact sheet) 생성
   - `render_markdown.py` — 최종 `summary.md` + 이미지 복사

2. **참고 문서도 가져와서** `.claude/skills/youtube-visual-summary/references/` 에 배치해:

   - `workflow.md` — 전체 오케스트레이션 체크리스트
   - `summary-levels.md` — short/normal/detailed 요약 밀도 정의
   - `frame-selection-rubric.md` — 프레임 선택 기준
   - `troubleshooting.md` — 문제 해결 가이드

3. **마크다운 템플릿도** `.claude/skills/youtube-visual-summary/assets/markdown-template.md` 에 배치해

### 핵심 아키텍처 결정사항

**실행 모드: 서브 에이전트 (단일 에이전트)**

이 하네스는 순차적 파이프라인 워크플로우라 에이전트 팀이 불필요해. 오케스트레이터 스킬 하나가 전체 워크플로우를 직접 수행하면 돼:

- 스크립트 실행은 Bash 도구로
- 자막 분석/챕터 분할/요약/프레임 선택은 Claude가 직접 수행
- 중간 결과물은 파일 기반으로 전달

에이전트 정의 파일(`.claude/agents/youtube-summarizer.md`)은 만들되, 오케스트레이터 스킬이 이 에이전트를 서브 에이전트로 호출하는 대신 **직접 수행**하는 구조로 해. 즉 오케스트레이터 스킬 자체가 전체 파이프라인을 드라이브하고, 에이전트 정의는 역할/원칙 문서로만 사용해.

### 워크플로우

1. **입력 파싱**: YouTube URL + 요약 수준(short/normal/detailed, 기본값: normal) 추출
2. **환경 준비**: `setup_venv.py` → `env_check.py`
3. **데이터 수집**: `fetch_youtube.py` → `build_transcript.py`
4. **콘텐츠 분석 (Claude 직접 수행)**:
   - `transcript.json` 읽고 챕터 분할
   - `chapters.codex.json` 생성 (챕터별 제목, 시간, 요약 불릿, visual_query)
   - `references/summary-levels.md` 참고하여 요약 밀도 조절
5. **비주얼 처리** (텍스트 전용 요청이 아닌 경우):
   - `fetch_frame_source.py` → `extract_frames.py` → `make_contact_sheets.py`
6. **프레임 선택 (Claude 직접 수행)**:
   - contact sheet 이미지 검사
   - `references/frame-selection-rubric.md` 기준으로 프레임 선택
   - `selected-frames.json` 생성
7. **출력 렌더링**:
   - `render_markdown.py` → `summary.md`
   - `render_html.py` **→** `summary.html` (아래 추가 기능 참조)

### ⭐ 추가 기능: HTML 출력

기존 codex 하네스는 Markdown만 출력하는데, **HTML 출력도 함께 생성**하도록 새 스크립트를 추가해.

#### 새 스크립트: `render_html.py`

`render_markdown.py`와 동일한 입력(`metadata.json`, `chapters.codex.json`, `selected-frames.json`)을 사용해서 `summary.html`을 생성해.

#### HTML 템플릿

Claude가 디자인을 고민하지 않고 바로 렌더링하도록, **아래 템플릿을** `assets/html-template.html`**에 그대로 저장**하고 `render_html.py`는 이 템플릿을 읽어서 변수 치환 방식으로 렌더링하도록 구현해.

템플릿 변수:

- `{{TITLE}}` — 비디오 제목
- `{{URL}}` — YouTube URL
- `{{CHANNEL}}` — 채널명
- `{{DURATION}}` — 영상 길이 (MM:SS)
- `{{SUMMARY_LEVEL}}` — 요약 수준
- `{{TAGS}}` — 챕터 제목을 태그로 변환한 HTML 문자열
- `{{TOC}}` — 목차 HTML 문자열
- `{{CHAPTERS}}` — 챕터 본문 HTML 문자열
- `{{TIMESTAMP}}` — 생성 일시

아래가 템플릿 전문이야. **그대로 파일로 저장**해:

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{TITLE}}</title>
<style>
/* ── Reset & Base ── */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
html { font-size: 16px; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
body {
  font-family: "Pretendard Variable", "Pretendard", -apple-system, BlinkMacSystemFont, system-ui, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans KR", "Malgun Gothic", sans-serif;
  color: #171B1F;
  background: #ffffff;
  line-height: 1.75;
}

/* ── Article Container ── */
.article-wrapper {
  max-width: 680px;
  margin: 0 auto;
  padding: 0 20px;
}

/* ── Category Badge ── */
.category-badge {
  display: inline-block;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #fc1c49;
  margin-bottom: 12px;
  letter-spacing: -0.01em;
}

/* ── Title Section ── */
.article-title {
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.4;
  color: #171B1F;
  letter-spacing: -0.02em;
  margin-bottom: 16px;
}
.article-title a {
  color: inherit;
  text-decoration: none;
}
.article-title a:hover {
  color: #0066FF;
}

/* ── Meta Info ── */
.meta-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  font-size: 0.8125rem;
  color: #747678;
  margin-bottom: 12px;
}
.meta-bar span { display: inline-flex; align-items: center; gap: 4px; }
.meta-bar .label { font-weight: 600; color: #4B4D4F; }

/* ── Tags ── */
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 28px;
}
.tag-list .tag {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 500;
  color: #747678;
  background: #F5F5F6;
  padding: 3px 10px;
  border-radius: 4px;
}

/* ── Divider ── */
.divider {
  border: none;
  border-top: 1px solid #E7E7E8;
  margin: 28px 0;
}

/* ── TOC (Table of Contents) ── */
.toc {
  background: #F5F5F6;
  border-radius: 8px;
  padding: 20px 24px;
  margin-bottom: 32px;
}
.toc-title {
  font-size: 0.875rem;
  font-weight: 700;
  color: #171B1F;
  margin-bottom: 12px;
}
.toc-list {
  list-style: none;
  counter-reset: toc-counter;
}
.toc-list li {
  counter-increment: toc-counter;
  font-size: 0.8125rem;
  line-height: 1.6;
  color: #4B4D4F;
  padding: 4px 0;
}
.toc-list li::before {
  content: counter(toc-counter) ". ";
  font-weight: 600;
  color: #171B1F;
}
.toc-list a {
  color: #4B4D4F;
  text-decoration: none;
}
.toc-list a:hover {
  color: #0066FF;
}

/* ── Chapter Section ── */
.chapter {
  margin-bottom: 40px;
}
.chapter:last-child {
  margin-bottom: 0;
}

/* ── Chapter Heading ── */
.chapter-heading {
  font-size: 1.25rem;
  font-weight: 700;
  color: #171B1F;
  line-height: 1.45;
  letter-spacing: -0.015em;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #E7E7E8;
}
.chapter-time {
  font-size: 0.8125rem;
  font-weight: 500;
  color: #747678;
  margin-left: 8px;
}

/* ── Chapter Image ── */
.chapter-image {
  margin: 20px 0;
  border-radius: 8px;
  overflow: hidden;
}
.chapter-image img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 8px;
}
.chapter-image-caption {
  font-size: 0.75rem;
  color: #747678;
  margin-top: 8px;
  font-style: italic;
}

/* ── Summary Bullets ── */
.summary-list {
  list-style: none;
  padding: 0;
}
.summary-list li {
  position: relative;
  font-size: 0.9375rem;
  color: #4B4D4F;
  line-height: 1.75;
  padding-left: 16px;
  margin-bottom: 8px;
}
.summary-list li::before {
  content: "•";
  position: absolute;
  left: 0;
  color: #fc1c49;
  font-weight: 700;
}

/* ── Footer ── */
.article-footer {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid #E7E7E8;
  font-size: 0.75rem;
  color: #747678;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.youtube-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #0066FF;
  text-decoration: none;
}
.youtube-link:hover { text-decoration: underline; }
.youtube-link svg { width: 18px; height: 18px; }

/* ── Responsive ── */
@media (max-width: 720px) {
  .article-wrapper { padding: 0 16px; }
  .article-title { font-size: 1.375rem; }
  .chapter-heading { font-size: 1.125rem; }
}

/* ── Dark Mode ── */
@media (prefers-color-scheme: dark) {
  body { background: #1a1a1a; color: #e0e0e0; }
  .category-badge { color: #ff5a7a; }
  .article-title { color: #f0f0f0; }
  .article-title a:hover { color: #5c9aff; }
  .meta-bar { color: #999; }
  .meta-bar .label { color: #bbb; }
  .tag-list .tag { background: #2a2a2a; color: #999; }
  .divider { border-top-color: #333; }
  .toc { background: #222; }
  .toc-title { color: #f0f0f0; }
  .toc-list li { color: #aaa; }
  .toc-list li::before { color: #f0f0f0; }
  .toc-list a { color: #aaa; }
  .toc-list a:hover { color: #5c9aff; }
  .chapter-heading { color: #f0f0f0; border-bottom-color: #333; }
  .chapter-time { color: #888; }
  .chapter-image-caption { color: #888; }
  .summary-list li { color: #c0c0c0; }
  .summary-list li::before { color: #ff5a7a; }
  .article-footer { border-top-color: #333; color: #888; }
  .youtube-link { color: #5c9aff; }
}
</style>
</head>
<body>

<div class="article-wrapper">

  <!-- Category Badge -->
  <span class="category-badge">YouTube 요약</span>

  <!-- Title (links to original YouTube video) -->
  <h1 class="article-title">
    <a href="{{URL}}" target="_blank" rel="noopener">{{TITLE}}</a>
  </h1>

  <!-- Meta Info -->
  <div class="meta-bar">
    <span><span class="label">채널</span> {{CHANNEL}}</span>
    <span><span class="label">길이</span> {{DURATION}}</span>
    <span><span class="label">요약 수준</span> {{SUMMARY_LEVEL}}</span>
  </div>

  <!-- Tags (chapter titles) -->
  <div class="tag-list">
    {{TAGS}}
  </div>

  <hr class="divider">

  <!-- Table of Contents -->
  <nav class="toc">
    <div class="toc-title">목차</div>
    <ol class="toc-list">
      {{TOC}}
    </ol>
  </nav>

  <!-- Chapter Content -->
  {{CHAPTERS}}

  <!-- Footer -->
  <div class="article-footer">
    <span>생성일: {{TIMESTAMP}}</span>
    <a class="youtube-link" href="{{URL}}" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
      원본 영상 보기
    </a>
  </div>

</div>

</body>
</html>
```

#### render_html.py 구현 지침

`render_html.py`는 다음과 같이 동작해:

1. `assets/html-template.html`을 읽음
2. `metadata.json`에서 TITLE, URL, CHANNEL, DURATION 획득
3. `chapters.codex.json`에서 SUMMARY_LEVEL, 챕터 데이터 획득
4. `selected-frames.json`에서 프레임 선택 데이터 획득
5. 템플릿 변수 치환:
   - `{{TAGS}}` → 각 챕터 제목을 `<span class="tag">#챕터제목</span>` 으로 변환
   - `{{TOC}}` → `<li><a href="#chapter-N">챕터제목 <span class="chapter-time">시간범위</span></a></li>` 목차 생성
   - `{{CHAPTERS}}` → 각 챕터를 아래 구조로 반복 생성:

```html
<section class="chapter" id="chapter-01">
  <h2 class="chapter-heading">챕터 제목 <span class="chapter-time">00:00 ~ 04:00</span></h2>

  <div class="chapter-image">
    <img src="images/chapter-01.jpg" alt="visual_query 텍스트" loading="lazy">
    <div class="chapter-image-caption">Frame: 03:58. 프레임 선택 사유 텍스트</div>
  </div>

  <ul class="summary-list">
    <li>요약 불릿 1</li>
    <li>요약 불릿 2</li>
    <li>요약 불릿 3</li>
  </ul>
</section>
```

6. 프레임이 없는 챕터는 `chapter-image` 블록 생략
7. 이미지는 `render_markdown.py`와 동일하게 `run_dir/images/` 에 이미 복사된 파일 사용
8. `{{TIMESTAMP}}` → 현재 KST 기준 `YYYY-MM-DD HH:MM`
9. 최종 `summary.html`을 `run_dir/summary.html` 에 저장

### 출력 디렉토리 구조

```
runs/YYYY-MM-DD_HHMMSS_slug/
├── summary.md          # Markdown 요약 (기존)
├── summary.html        # HTML 요약 (신규)
├── images/             # 선택된 프레임 이미지
└── _work/              # 내부 작업 파일
    ├── metadata.json
    ├── transcript.json
    ├── chapters.codex.json
    ├── selected-frames.json
    ├── frame-source.*
    ├── frames/
    └── contact-sheets/
```

### 스킬 description (적극적 트리거)

스킬 description은 다음 키워드를 모두 포함하도록 작성해:

- "YouTube", "유튜브", "영상 요약", "비디오 요약", "비디오 서머리"
- "자막", "요약", "챕터", "프레임", "visual summary"
- "마크다운 요약", "HTML 요약", "summary.md", "summary.html"
- 후속 작업: "다시 요약", "요약 수정", "요약 보완", "더 자세히", "간단히"

### 환경 정책

- 프로젝트 루트 `.venv` 사용 (시스템 Python 오염 방지)
- 필수 외부 도구: `yt-dlp`, `ffmpeg`, `ffprobe` (OS 패키지 매니저로 설치)
- Python 패키지: `yt-dlp`, `Pillow`, `pydantic`, `rich`, `PyYAML` (.venv 내부)
- Claude 자체가 LLM 역할을 하므로 외부 LLM API 호출 금지

### 캡션 정책

우선순위: 수동 한국어 자막 &gt; 수동 영어 자막 &gt; 자동 생성 자막 &gt; 다른 언어 자막 자막이 없으면 기본 실패 처리 + 선택적 STT 제안 (MVP 범위 밖)

### 프레임 정책

- 챕터 중간 지점 단일 캡처 금지, 반드시 여러 후보 프레임 비교
- 슬라이드/차트/코드/데모 화면 &gt; 화자 얼굴 (얼굴은 화자 관련 챕터에서만)
- 후보가 모두 약하면 `--max-frames-per-chapter` 증가 후 재추출

### 참고: Codex 원본 파일 경로

스크립트와 참고 문서는 이 경로에서 직접 읽어서 포팅해:

- 스크립트: `<Codex 원본 저장소>/skills/youtube-visual-summary/scripts/`
- 참고문서: `<Codex 원본 저장소>/skills/youtube-visual-summary/references/`
- 템플릿: `<Codex 원본 저장소>/skills/youtube-visual-summary/assets/`
- SKILL.md: `<Codex 원본 저장소>/skills/youtube-visual-summary/SKILL.md`

### CLAUDE.md 포인터

완료 후 `CLAUDE.md`에 하네스 포인터 등록:

- 트리거: YouTube/유튜브 영상 요약 요청 시 `youtube-visual-summary` 스킬 사용
- 변경 이력: 초기 구성 기록