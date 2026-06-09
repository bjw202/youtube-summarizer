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
  - 한국어: 짧게/간단히/핵심만 → short, 보통/일반/요약 → normal, 자세히/상세/깊게 → detailed
- `output_format`: `both`, `markdown`, `html` (기본값: `both`)
- `text_only`: `true`면 프레임 추출 생략 (기본값: `false`)

### Phase 2: 환경 준비

```bash
python3 .claude/skills/youtube-visual-summary/scripts/setup_venv.py
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/env_check.py --json
```

필수 외부 도구: `yt-dlp`, `ffmpeg`, `ffprobe`. 누락 시 설치 방법 안내 후 중단.

권장 JS 런타임: `deno` 또는 `node`. yt-dlp가 YouTube EJS 챌린지를 해결하는 데 필요하다. `env_check.py --json`의 `has_js_runtime`으로 확인 가능. 없으면 deno 설치 안내:

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
- JS 런타임이 감지되면 `--remote-components ejs:github` 플래그 자동 추가

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
