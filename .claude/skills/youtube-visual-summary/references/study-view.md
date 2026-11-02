# 학습 보기 (study view)

요약 페이지(`summary.html`)는 영상을 **읽게** 만든다. 학습 보기(`study.html`)는 영상을 **섹션별로 다시 보며 공부하게** 만든다. 이미지 한 장으로는 부족한 부분을, 그 구간 영상과 설명을 나란히 놓고 보는 용도다.

- 왼쪽: 그 구간만 잘라 둔 **로컬 클립**을 재생하는 고정(sticky) 플레이어 + 재생에 맞춰 강조되는 자막
- 오른쪽: 정의 · 요점 · 함께 알아두기(하위 장면) · 영상 속 설명 자세히 · AI 요청 프롬프트 · 관련 항목
- 상단 토글로 "깊게 보기"(섹션별) ↔ "훑어보기"(카드 격자) 전환, 사이드바에 "공부함" 진행률

## 언제 쓰나

| 상황 | 방식 |
| --- | --- |
| 영상 1개를 챕터별로 공부 | `study.json` 없이 렌더 → 챕터 1개 = 항목 1개로 자동 구성 (아래 "자동 구성") |
| 용어·기능을 하나씩 소개하는 영상(용어집, 기능 투어) | `study.json`을 직접 써서 항목·그룹·하위 장면을 정의 |
| 영상 여러 개를 하나의 학습 노트로 통합 | 영상별 표준 run을 먼저 만들고, 새 run 디렉터리에 `study.json`만 두어 각 run을 `sources[].run`으로 참조 |

## 워크플로우

표준 요약 Phase 1~6을 그대로 거친 run(들)이 입력이다. 학습 보기를 만들 것을 처음부터 알면 Phase 5를 다음처럼 바꾼다.

```bash
S=.claude/skills/youtube-visual-summary/scripts
# Phase 5 대체: 소리 포함 1080p 한 파일 — 프레임 추출과 클립 절단에 같이 쓴다
uv run python $S/fetch_frame_source.py RUN_DIR --with-audio
# 챕터가 10~40초로 짧으면(항목 1개 = 챕터 1개) 고정 간격으로 조밀하게
uv run python $S/extract_frames.py RUN_DIR --interval 2.5
uv run python $S/make_contact_sheets.py RUN_DIR
```

이후:

```bash
# (선택) RUN_DIR/_work/study.json 작성 — 없으면 챕터에서 자동 구성
uv run python $S/cut_clips.py RUN_DIR       # clips/{항목}.mp4, 기존 클립은 재사용
uv run python $S/render_study.py RUN_DIR    # study.html + images/study/*.webp
uv run python $S/check_study.py RUN_DIR     # QA — FAIL이 하나라도 있으면 전달 금지
```

이미 무음 소스로 받은 run이면 `fetch_frame_source.py --with-audio`를 다시 돌린다(무음 파일을 지우고 새로 받는다). 프레임은 같은 영상이므로 다시 뽑지 않아도 된다.

### 영상 여러 개 통합

1. 영상마다 표준 run을 만든다(각자 fetch → 챕터 → `--with-audio` 소스 → 프레임 추출).
2. 통합 run 디렉터리 `runs/YYYY-MM-DD_HHMMSS_<slug>/_work/`를 만들고 `study.json`을 둔다. `sources[].run`은 **통합 run 기준 상대 경로**(`../<영상 run>`)다.
3. `cut_clips` → `render_study` → `check_study`를 통합 run에 대해 실행한다. 클립과 이미지는 통합 run에 모인다.

## 자동 구성 (`study.json` 없을 때)

`study_spec.py`가 챕터마다 항목 하나를 만든다.

| 항목 칸 | 가져오는 곳 (`chapters.codex.json` · `selected-frames.json`) |
| --- | --- |
| 이름 | 챕터 `title` |
| 리드 문장(정의) | 챕터 `key_point` — 없으면 칸이 생략된다. 그래서 Phase 6.5가 `key_point` 없는 챕터를 FAIL로 잡는다 |
| 요점 | 챕터 `summary_bullets` |
| 영상 속 설명 자세히 | 챕터 `summary_paragraphs` (없으면 생략) |
| AI에게 이렇게 요청 | 챕터 `prompt.text` (없으면 생략) |
| 장면(포스터·클립) | 그 챕터에서 고른 **첫** 장면, 클립은 챕터 전체. 고른 장면이 없으면 후보 가운데 가운데 것 |
| 함께 알아두기(`subs`) | 그 챕터에서 고른 **두 번째부터의** 장면 하나마다 하나. 이름은 장면의 `caption`(없으면 "장면 n (mm:ss)"), 설명은 요약에서 그 그림이 붙은 요점(`after_bullet`, 없으면 `reason`) |

- 하위 장면의 클립은 그 장면이 화면에 나온 때의 자막 줄 시작부터 챕터 끝까지다(최소 8초). 장면이 둘 이상이면 플레이어 위에 '장면 1·장면 2…' 탭이 생긴다.
- 고른 장면은 하나도 빠지지 않는다. `check_study.py`가 `selected-frames.json`과 대조해 빠진 장면을 FAIL로 잡는다.

## `study.json` 스키마

```jsonc
{
  "title": "바이브코더 필수 용어집",
  "subtitle": "한 줄 소개",
  "sources": [
    { "key": "1", "label": "1탄", "run": "../2026-10-29_195901_...", "title": "영상 제목",
      "channel": "채널", "duration": "11:50" }            // url 생략 시 그 run의 input.json
  ],
  "formulas": [ { "label": "1탄 요청 공식", "text": "UI 용어 + 원하는 동작 + 적용 조건", "example": "\"...\"" } ],  // 선택
  "groups": [ { "id": "layout", "name": "레이아웃", "en": "Layout", "note": "...7개", "source": "1" } ],          // 선택
  "items": [{
    "id": "hero-section",                  // 앵커·클립·이미지 파일명
    "group": "layout",
    "name": "히어로 섹션", "en": "Hero Section",                       // en 선택
    "scene": { "source": "1", "frame_id": "chapter-01-f004" },        // 포스터 프레임; 클립 구간 = 그 프레임의 챕터
    "label": "장면 1",                     // 선택 — 하위 장면이 있을 때 플레이어 탭 글자(없으면 name)
    "definition": "한두 문장 정의 (크게 표시)",
    "points": ["요점 bullet", "**굵게** 허용"],
    "prompt": "영상에 나온 AI 요청 예시 (복사 카드)",                   // 선택
    "subs": [{ "id": "cta", "name": "CTA 버튼", "en": "Call To Action", "label": "CTA",   // label 선택 — 탭 글자
               "scene": { "source": "1", "frame_id": "chapter-01-f007" },
               "definition": "...", "points": ["..."] }],             // 선택 — 같은 플레이어에서 전환
    "related": ["sticky-header"]                                      // 선택 — 다른 항목 id
  }],
  "cheatsheets": [ { "source": "1", "frame_id": "chapter-27-f010", "caption": "..." } ],  // 선택
  "own_scenes": true   // 선택 — 요약용으로 고른 장면 대신 자기 장면(용어 타이틀 카드 등)을 쓰는 명세. 고른 장면 대조를 하지 않는다
}
```

- **고른 장면 대조**: `check_study.py`는 학습 보기가 다루는 챕터에서 Phase 6에 고른 장면(`selected-frames.json`)이 항목이나 하위 장면으로 모두 들어갔는지 본다. 빠지면 FAIL이다. 챕터를 통째로 뺀 것은 괜찮다. 용어집처럼 장면을 처음부터 따로 고르는 명세는 `"own_scenes": true`로 대조를 끈다.
- **간접 참조**: `scene`은 `frame_id`만 담고, 렌더러가 소스 run의 `_work/frames/manifest.json`에서 이미지 경로(`RUN_DIR/_work/` 기준)·챕터를 찾는다. 프레임 경로나 타임스탬프를 손으로 옮겨 적지 않는다.
- **클립 구간**: 기본은 그 프레임이 속한 챕터 전체(앞 0.2초, 뒤 0.4초 여유). 한 챕터 안의 일부만 원하면 `scene`에 `"start"`, `"end"`(초)를 넣는다.
- `source`는 소스가 하나면 생략 가능. `groups`가 없거나 그룹에 `name`이 없으면 그룹 머리 없이 목록만 나온다.
- "영상 속 설명 자세히"는 그 챕터의 `summary_paragraphs`, 자막은 소스 run의 `transcript.json`에서 자동으로 채운다.

## 항목·장면 고르기

- **항목 단위 = 사람이 따로 복습하고 싶은 단위.** 용어 강의는 용어 1개, 튜토리얼은 단계 1개, 강의는 개념 1개. 강의·발표는 Phase 4의 챕터(`summary-levels.md` "챕터 나누기 수치" — 보통 1~5분)를 그대로 항목으로 쓰고 학습 보기 때문에 더 쪼개지 않는다. 한 챕터 안의 다른 슬라이드·도표는 장면 2·3으로 들어간다. 10~40초 단위는 영상 자체가 용어·단계 하나씩 다룰 때만이다.
- **포스터 프레임**: 이름과 한 줄 정의가 화면에 같이 잡힌 장면(타이틀 카드)을 우선한다. 글자가 다 드러난 뒤 시점을 고른다. 없으면 `frame-selection-rubric.md` 기준.
- **영상이 말하는 분류를 따른다.** 영상 말미의 치트시트·정리 화면이 공식 분류와 개수를 확정한다(첫 용어집에서 트랜스크립트로 센 26개와 영상 공칭 24개가 달랐고, 치트시트 프레임으로 맞췄다). 공칭 목록 밖의 부분 개념은 별도 항목 대신 `subs`로 흡수한다. 정리 화면은 `cheatsheets`에 넣는다.
- 영상에 나온 AI 요청 문장은 빠짐없이 모아 `prompt`로 만든다 — 실전에서 가장 많이 복사되는 부분이다.

## 반드시 지킬 것

1. **로컬 HTML에 유튜브 iframe을 넣지 않는다 (오류 153).** 2025-11부터 유튜브가 임베드 요청의 referrer를 검사해, `file://` 페이지의 iframe은 `youtube.com`·`youtube-nocookie.com` 모두 "동영상 플레이어 구성 오류(153)"로 실패한다. `<meta name="referrer">`로도 안 된다(보낼 출처 자체가 없음). 그래서 구간 재생은 **로컬 클립 + `<video>`**만 쓴다. 원본 이동 경로는 각 장면의 `t=` 딥링크로 남긴다.
2. **클립에는 소리가 있어야 한다.** 기본 프레임 소스는 영상 스트림만 받는다. 학습 보기용 run은 `--with-audio`로 받고, `cut_clips.py`는 소스에 오디오가 없으면 멈춘다. `check_study.py`가 모든 클립의 오디오 스트림을 ffprobe로 다시 확인한다.
3. **한 번에 하나만 재생한다.** 다른 섹션을 재생하거나 하위 장면으로 바꾸면 이전 클립은 멈추고 포스터로 돌아간다. 템플릿에 구현돼 있으니 바꿀 때 유지한다.
4. **레이아웃 비율**: 영상 쪽이 더 넓다(`1.28fr : 1fr`, 약 56:44). 첫 용어집의 44:56은 "동영상이 너무 작다"는 피드백으로 뒤집었다. 900px 이하에서는 세로로 쌓고 고정을 푼다.

## 산출물과 용량

- `study.html`, `images/study/*.webp`(1280px, q85), `clips/*.mp4`(720p H.264 + AAC 128k, faststart)
- 클립은 항목 48개 기준 약 100MB다. 페이지는 폴더째 옮겨야 재생된다. 가볍게 공유해야 하면 `cut_clips.py`를 건너뛰고 렌더한다 — 재생 버튼이 유튜브 딥링크를 연다(`check_study.py --allow-missing-clips`).
- 진행률·보기 방식은 브라우저 `localStorage`에 페이지 경로별로 저장된다(파일을 옮기면 초기화).
- 긴 강의는 클립이 영상 전체를 다시 담는다: 63분 강의 21개 항목이 약 290MB였다. 원본 영상(1080p 약 1.3GB)은 Phase 9의 `clean_run.py`가 지운다 — 클립을 다시 자르려면 `fetch_frame_source.py RUN_DIR --with-audio`로 다시 받는다.
- 정본 자막이 자동 생성 자막이나 음성 인식 결과면(`transcript.json`의 `caption_kind`가 `auto`·`stt`), '자막 따라 읽기' 머리에 "자동 생성 자막 — 받아쓰기 오류가 있을 수 있음"이 붙는다. `caption_kind`는 `build_transcript.py`가 `metadata.json`의 `subtitles`(업로더)·`automatic_captions`(자동)로 판단해 적는다. 이 값이 없는 예전 run은 표시하지 않는다.
