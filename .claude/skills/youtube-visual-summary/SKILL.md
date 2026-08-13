---
name: youtube-visual-summary
description: "YouTube/유튜브 영상의 자막 기반 비주얼 요약을 Markdown과 HTML로 생성. YouTube URL이 주어지면 반드시 이 스킬을 사용할 것. 영상 요약, 비디오 요약, 비디오 서머리, 자막 요약, 챕터 분할, 프레임 추출, visual summary, 마크다운 요약, HTML 요약, summary.md, summary.html 생성 시에도 이 스킬 사용. 후속 작업 — 다시 요약, 요약 수정, 요약 보완, 더 자세히, 간단히, 텍스트 전용 요약, 프레임만 재선택 — 요청 시에도 반드시 이 스킬을 사용."
---

# YouTube Visual Summary

YouTube 공개 영상의 자막 기반 비주얼 요약을 Markdown과 HTML 두 형식으로 생성하는 오케스트레이터 스킬.

## 실행 모드: 단일 오케스트레이터 (직접 수행)

순차 파이프라인이므로 에이전트 팀이나 서브 에이전트를 사용하지 않는다. 이 스킬이 직접 전체 워크플로우를 드라이브한다.

## 워크플로우

### Phase 0: 컨텍스트 확인

1. `runs/` 디렉토리에서 기존 산출물 확인
2. 실행 모드 결정:
   - 기존 run 없음 + 새 URL → **초기 실행** (Phase 1)
   - 기존 run 있음 + 수정 요청 → **부분 재실행** (해당 단계부터)
   - 기존 run 있음 + 새 URL → **새 실행**

### Phase 1: 입력 파싱

사용자 요청에서 다음을 추출한다:

- `url`: YouTube URL
- `summary_level`: `short`, `normal`, `detailed` (기본값: `normal`)
- `output_format`: `both`, `markdown`, `html` (기본값: `both`)
- `text_only`: `true`면 프레임 추출 생략 (기본값: `false`)

### Phase 2: 환경 준비

```bash
python3 .claude/skills/youtube-visual-summary/scripts/setup_venv.py
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/env_check.py --json
```

`setup_venv.py`는 uv로 **Python 3.12를 자동 확보**하고 `yt-dlp[default,curl-cffi]`를 설치한다. 두 extra가 YouTube 자막/메타데이터 fetch의 핵심 의존성을 채운다:
- `default` extra → `yt-dlp-ejs` (deno로 EJS 챌린지 해결) + brotli/requests 등 런타임 의존성
- `curl-cffi` extra (<0.16) → 브라우저 impersonation, YouTube 429 봇 탐지 우회

> **Python ≥3.10 강제.** yt-dlp(≥2026.x)는 Python 3.9를 거부한다. 시스템 `python3`이 3.9인 환경에서 기본 실행하면 구버전 yt-dlp가 깔려 EJS 챌린지가 "The page needs to be reloaded"로 전면 실패한다 — setup_venv.py의 기본값 `--python 3.12`(uv가 자동 확보)가 이를 방지한다.

필수 외부 도구: `yt-dlp`, `ffmpeg`, `ffprobe`. `env_check.py --json`의 `ok`가 `false`면 누락 도구를 안내 후 중단.

JS 런타임 (`deno` 권장, `node`도 가능): yt-dlp-ejs가 YouTube EJS 챌린지("The page needs to be reloaded")를 풀 때 deno로 JS를 실행하므로 필수다. `env_check.py --json`의 `has_js_runtime`으로 확인. 없으면 deno 설치:

```bash
curl -fsSL https://deno.land/install.sh | sh
```

### Phase 3: 데이터 수집

```bash
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/fetch_youtube.py "URL" --run-root runs
```

stdout에서 run 디렉토리 경로를 읽는다.

**자막 다운로드 동작:**
- 언어별 개별 다운로드: `ko` → `ko-orig` → `en` 순서로 시도
- 429 (Too Many Requests) 에러 시 지수 백오프로 최대 2회 재시도
- 부분 성공 허용: 하나의 언어라도 다운로드되면 워크플로우 계속 진행
- 멱등 재실행: 동일 URL의 기존 run이 있으면 메타데이터/자막을 스킵하고 누락분만 재시도
- JS 런타임 + curl_cffi가 감지되면 yt-dlp에 `--remote-components ejs:github`(EJS 챌린지 해결)와 `--impersonate chrome`(429 봇 탐지 우회)을 자동 추가

```bash
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/build_transcript.py RUN_DIR
```

실패(자막 없음) 시 텍스트 전용 모드로 전환하거나 선택적 STT를 제안한다. 기본적으로 STT는 MVP 범위 밖이다.

### Phase 4: 콘텐츠 분석 (Claude 직접 수행)

1. `RUN_DIR/_work/transcript.json` 읽기
2. `references/summary-levels.md` 읽어 요약 밀도 확인
3. 챕터 분할 및 `RUN_DIR/_work/chapters.codex.json` 생성:

```json
{
  "summary_level": "normal",
  "chapters": [
    {
      "id": "chapter-01",
      "title": "챕터 제목",
      "start": 12.0,
      "end": 145.5,
      "summary_bullets": ["..."],
      "visual_query": "찾아야 할 시각적 장면 설명"
    }
  ]
}
```

챕터 분할 원칙:
- 트랜스크립트 타임스탬프를 기준으로 의미 단위로 분할
- `detailed`는 하위 주제 전환 시 더 세밀하게 분할
- 각 챕터에 구체적인 `visual_query` 포함

### Phase 5: 비주얼 처리 (텍스트 전용이 아닌 경우)

```bash
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/extract_frames.py RUN_DIR
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/make_contact_sheets.py RUN_DIR
```

### Phase 6: 프레임 선택 (Claude 직접 수행)

1. `references/frame-selection-rubric.md` 읽기
2. contact sheet 이미지 검사
3. `RUN_DIR/_work/selected-frames.json` 생성:

```json
{
  "selections": [
    {
      "chapter_id": "chapter-01",
      "frame_id": "chapter-01-f003",
      "timestamp": 83.2,
      "image_path": "frames/chapter-01/chapter-01-f003.jpg",
      "reason": "요약에서 설명하는 차트가 보이고 읽기 가능함"
    }
  ]
}
```

프레임 선택 기준:
- 시맨틱 매치 → 정보 가치(차트>얼굴) → 가독성 → 선명도 → 특이성
- 후보가 모두 부족하면 `--max-frames-per-chapter 16`으로 재추출

### Phase 7: 출력 렌더링

```bash
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/render_markdown.py RUN_DIR
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/render_html.py RUN_DIR
```

`render_html.py`는 `assets/html-template.html`을 읽어 템플릿 변수를 치환한다.

최종 산출물:
- `RUN_DIR/summary.md`
- `RUN_DIR/summary.html`
- `RUN_DIR/images/` (선택된 프레임)

## Tab 추출 모드 워크플로우

Phase 1에서 `mode: tab`으로 결정된 경우 아래 워크플로우를 따른다. 요약 모드의 Phase 2-7은 건너뛴다.

### Tab Phase 2: 환경 준비

요약 모드와 동일. 누락된 도구가 있으면 설치 안내 후 중단.

### Tab Phase 3: 데이터 수집

요약 모드 Phase 3과 동일하게 메타데이터 + 비디오 파일을 다운로드한다.
자막은 tab 추출에 불필요하므로 건너뛴다.

```bash
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/fetch_youtube.py "URL" --run-root runs
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR
```

### Tab Phase 4: Tab 프레임 추출

밀집 프레임 추출 + 중복 제거 + 컨택트 시트 생성:

```bash
# 3fps로 프레임 추출 + 중복 제거
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/extract_tab_frames.py RUN_DIR

# 컨택트 시트 생성 (시각적 분석용)
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/make_tab_contact_sheet.py RUN_DIR
```

**매개변수 조정 가이드:**
- 프레임이 너무 적으면 (< 10개): `--fps 5`로 재추출
- 프레임이 너무 많으면 (> 300개): `--threshold 4`로 중복 제거 강화
- 영상 해상도가 낮으면: `--max-width 1920`로 고해상도 추출

출력:
- `RUN_DIR/_work/tab-frames/tab_XXXX.png` — 고유 프레임들
- `RUN_DIR/_work/tab-frames/tab_manifest.json` — 프레임 메타데이터
- `RUN_DIR/_work/tab-sheets/tab-sheet-NN.jpg` — 컨택트 시트

### Tab Phase 5: Tab 분석 (Claude 직접 수행)

이 단계는 Claude가 비전 능력으로 tab 악보를 시각적으로 분석하여 텍스트로 변환한다.

**사전 준비:** `references/tab-extraction-guide.md`를 읽어 tab 분석 방법론을 숙지한다.

**분석 절차:**

1. **컨택트 시트 검사** — `tab-sheets/`의 이미지를 읽어 tab 악보가 보이는지 확인
2. **개별 프레임 분석** — 필요하면 `tab-frames/tab_XXXX.png` 개별 파일도 읽어 상세 분석
3. **Tab 전사** — 각 프레임에서 tab notation을 읽어 텍스트로 변환
4. **중첩 제거** — 연속 프레임 간 겹치는 구간을 식별하고 새로운 내용만 남김
5. **섹션 분할** — 곡 구조(Intro, Verse, Chorus 등)에 따라 섹션 헤더 추가
6. **`RUN_DIR/_work/tab_analysis.json` 생성:**

```json
{
  "mode": "tab",
  "title": "곡 제목",
  "sections": [
    {
      "name": "Intro",
      "time_range": "0:00 - 0:15",
      "tab_text": "e|---0---1---3---5---|\nB|--1---1---0---0----|...",
      "repeat": 1,
      "confidence": "high"
    }
  ],
  "notes": "분석 중 발견한 특이사항",
  "uncertain_parts": ["불확실한 구간 설명"]
}
```

**품질 기준:**
- 6개 현(E, A, D, G, B, e) 모두 누락 없이 표시
- 프렛 숫자 정확도 교차 검증
- 마디 구분자(`|`) 일관성 유지
- 읽기 어려운 부분은 `?` 또는 `(~N)` 표기

### Tab Phase 6: Tab 출력 렌더링

분석 결과를 사용자 친화적인 형식으로 출력한다.

**Markdown 출력** (`RUN_DIR/tab.md`):
```markdown
# 🎸 Tab: {곡 제목}

**원본 영상:** {YouTube URL}
**채널:** {채널명}
**추출 날짜:** {날짜}
**프레임 수:** {고유 프레임 수}개 @ {fps}fps

---

## Intro (0:00 - 0:15)

\```
e|---0---1---3---5---|
B|--1---1---0---0----|
G|-2---2---0---0-----|
D|-------------------|
A|-------------------|
E|-------------------|
\```

## Verse (0:16 - 0:45) (x2)

\```
e|-------0-----------|
B|-----1---1---------|
G|---2-------2-------|
D|-------------------|
A|-0-----------------|
E|-------------------|
\```

---

> ⚠️ 이 tab은 영상의 시각적 tab 악보에서 자동 추출한 것입니다.
> 정확도 확인을 위해 원본 영상과 대조하세요.
> `?` 또는 `(~N)` 표시는 불확실한 부분입니다.
```

**HTML 출력** (`RUN_DIR/tab.html`) — HTML 템플릿을 사용해 반응형 웹페이지로 렌더링. tab 코드는 `<pre>` 블록으로 표시.

최종 산출물:
- `RUN_DIR/tab.md` — Markdown tab 악보
- `RUN_DIR/tab.html` — HTML tab 악보
- `RUN_DIR/images/` — 컨택트 시트 이미지 (참조용)

## 캡션 정책

우선순위: 수동 한국어 > 수동 영어 > 자동 생성 > 다른 언어. 자막이 없으면 기본 실패 + 선택적 STT 제안.

## 환경 정책

프로젝트 루트 `.venv` 사용. 시스템 Python 오염 방지. `setup_venv.py`가 `uv` 우선, `pip` 폴백으로 관리한다.

## 에러 핸들링

| 상황 | 대응 |
|------|------|
| 자막 없음 | 텍스트 전용으로 전환, STT 제안 |
| 자막 일부 실패 (429) | 성공한 언어로 계속 진행, 실패 언어는 경고만 |
| 프레임 추출 실패 | 텍스트 전용으로 진행 |
| yt-dlp 실패 | 네트워크/권한 안내 |
| JS 런타임 없음 | deno/node 설치 안내, `--remote-components` 없이 재시도 |
| 스크립트 실행 에러 | `references/troubleshooting.md` 참조 |
| Tab 프레임 너무 적음 | `--fps 5`로 재추출 권장 |
| Tab 프레임 너무 많음 | `--threshold 4`로 재추출 권장 |
| Tab 영상이 아니었음 | 사용자에게 요약 모드 전환 제안 |
| Tab 읽기 불가능 (해상도/화질) | `--max-width 1920`로 재추출 후 재시도 |

## 테스트 시나리오

### 정상 흐름

1. 사용자가 YouTube URL 제공
2. Phase 1-3: 환경 준비 → 메타데이터+자막 수집
3. Phase 4: Claude가 트랜스크립트 분석 → chapters.codex.json 생성
4. Phase 5: 프레임 소스 다운로드 → 후보 프레임 추출 → contact sheet 생성
5. Phase 6: Claude가 contact sheet 검사 → selected-frames.json 생성
6. Phase 7: summary.md + summary.html 렌더링
7. 결과: `runs/YYYY-MM-DD_HHMMSS_slug/` 에 전체 산출물 생성

### 에러 흐름 (자막 없음)

1. Phase 3에서 `build_transcript.py` 실패
2. 사용자에게 텍스트 전용 모드 전환 또는 STT 제안
3. 텍스트 전용 선택 시 Phase 5-6 건너뛰고 Phase 7 진행
4. 결과: 프레임 이미지 없는 summary.md + summary.html 생성

### Tab 추출 흐름

1. 사용자가 "이 기타 영상 tab 악보 추출해줘: [URL]" 입력
2. Phase 1: `mode: tab` 감지
3. Tab Phase 2-3: 환경 준비 → 비디오 다운로드
4. Tab Phase 4: `extract_tab_frames.py`로 밀집 프레임 추출 + 중복 제거 → `make_tab_contact_sheet.py`로 컨택트 시트 생성
5. Tab Phase 5: Claude가 컨택트 시트/프레임을 비전으로 분석 → `tab_analysis.json` 생성
6. Tab Phase 6: `tab.md` + `tab.html` 렌더링
7. 결과: `runs/YYYY-MM-DD_HHMMSS_slug/tab.md` 에 완전한 tab 악보 생성

### Tab 에러 흐름 (Tab 영상이 아닌 경우)

1. Tab Phase 5에서 프레임에 tab notation이 보이지 않음
2. 사용자에게 요약 모드 전환 제안
3. 요약 모드로 전환하여 기존 워크플로우 실행
