---
name: research-synthesis-report
description: "여러 소스(YouTube 영상 N개 + 공식 문서/홈페이지 사이트 M개)를 병렬 분석해 교차 검증된 단일 종합 리서치 리포트로 합성하는 오케스트레이터. 다음 요청 시 반드시 이 스킬을 사용할 것 — '여러 리뷰 영상 종합해줘', '영상이랑 공식 문서 합쳐서 정리', '종합 리포트', '리서치 리포트', '제품 리뷰 종합', '리뷰 영상들 비교 정리', '이 사이트 분석해서 영상이랑 비교', '도입 검토 자료 만들어줘'. 후속 작업 — 리포트 업데이트, 새 소스 추가, 특정 소스만 다시 분석, 보완, 더 자세히, 미해결 질문 추가 조사, 결과 개선 — 요청 시에도 반드시 이 스킬을 사용. 영상 1개만 요약하는 것은 youtube-visual-summary, 세미나 영상 1개를 슬라이드덱으로 재저작하는 것은 technical-seminar-deck을 사용한다."
---

# Research Synthesis Report — 멀티소스 종합 리서치 리포트

YouTube 영상 N개 + 공식 문서/홈페이지 사이트 M개를 병렬로 수집·분석하여, 사용자의 리서치 질문에 답하는 **단일 종합 리포트**(Markdown + HTML)로 합성하는 오케스트레이터.

**기존 스킬과의 차이:** `youtube-visual-summary`는 영상 1개를 요약한다. `technical-seminar-deck`는 세미나 영상 1개를 슬라이드덱으로 재저작한다. 이 스킬은 **여러 소스를 교차 검증하며 하나의 리서치 리포트**로 합친다 — 제품 리뷰 종합, 영상×공식문서 비교, 도입 검토 자료가 대표 사례.

## 실행 모드: 서브 에이전트

| Phase | 모드 | 이유 |
|-------|------|------|
| 2 (영상 데이터 수집) | 오케스트레이터 직접 | yt-dlp 스크립트 순차 실행 (동시 fetch는 429 위험) |
| 3 (소스별 분석) | 서브 에이전트 병렬 | 영상·사이트 분석이 서로 독립 — 파일 전달이면 충분 |
| 4 (합성) | 서브 에이전트 단일 | 단일 작가 원칙 — 여러 작가가 나눠 쓰면 목소리가 갈라진다 |
| 5 (QA) | 서브 에이전트 단일 | 검증자는 생산자와 분리 |

팀 모드를 쓰지 않는 이유: 모든 산출물이 파일로 전달되고 실시간 협상(스펙 조정 등)이 없어 팀 통신이 구조적으로 불필요하다. 대신 **동시 실행 에이전트를 3~5개로 제한**한다 — 이 세션의 모델 백엔드는 RPM 한도가 있어 과도한 병렬 호출이 429를 유발한다. 429 발생 시 1회 재시도, 지속되면 순차 전환.

## 에이전트 구성

| 에이전트 | 역할 | 참조 | 출력 |
|----------|------|------|------|
| video-analyst | 영상 1개 주장 추출 (N회 호출) | `references/source-schemas.md` | `_work/10_video_{id}.json` |
| docs-analyst | 사이트 1개 전체 순회 (M회 호출) | `docs-site-crawl` 스킬 + `references/source-schemas.md` | `_work/20_site_{id}.json` |
| visual-producer (공유) | 리포트용 영상 프레임 선정 | `youtube-visual-summary/references/frame-selection-rubric.md` | `images/`, `_work/30_visual_manifest.json` |
| report-synthesizer | 교차 검증·합성 | `references/report-writing-guide.md` | `report.md` |
| report-qa | 원본 대조 검증 | `references/qa-checklist.md` | `_work/40_qa.json` |

모든 Agent 호출에 `model: "opus"`와 `run_in_background: true`를 명시한다.

## Phase 0: 컨텍스트 확인

1. `runs/`에서 리서치 run(`*_research-*`)을 찾아 대상 소스 URL과 비교한다
2. 실행 모드 결정:

| 상태 | 모드 | 동작 |
|------|------|------|
| run 없음 | **초기 실행** | Phase 1부터 |
| run 있음 + 부분 수정 요청 | **부분 재실행** | 해당 소스의 분석 에이전트만 재호출 → 합성 → QA |
| run 있음 + 새 소스 추가 | **확장 실행** | 신규 소스만 수집·분석(새 ID 부여) 후 기존 `_work/`와 병합해 재합성 |
| run 있음 + 전혀 다른 주제 | **새 실행** | 기존 run 보존, 새 run 디렉토리 |

**부분 재실행 의존 관계:** `10_video_*` / `20_site_*` → `report.md` → `40_qa.json`. 소스 분석이 바뀌면 합성·QA를 다시 돌린다.

## Phase 1: 입력 파싱 + 브리프

사용자 요청에서 추출:

- `video_urls[]`: YouTube URL 목록
- `site_urls[]`: 공식 문서/홈페이지 목록
- `research_questions[]`: 리서치 질문 — **리포트 목차를 결정하는 핵심 입력**
- `audience`: 기본 `"제품 도입을 검토하는 기술적인 일반 독자"`

**리서치 질문이 없으면**: 영상 제목·채널·사이트 주제만으로 기본 질문 세트를 초안 작성해 사용자에게 확인받는다. 예: "이 제품은 무엇이고 어떤 문제를 푸나" / "리뷰어들의 평가는 어디가 갈리고 어디가 일치하나" / "공식 문서가 보장하는 것과 리뷰의 주장이 일치하나" / "쓰기 시작하면 무엇을 조심해야 하나". **질문 확정 전 Phase 2 이후 진행 금지.**

그 다음:

1. run 디렉토리 생성: `runs/{YYYY-MM-DD_HHMMSS}_research-{topic-slug}/`
2. 브리프 작성: `_work/00_brief.md` — 리서치 질문, 소스 목록(URL+ID), audience, 사용자 특별 지시. 모든 에이전트가 이 파일을 먼저 읽는다
3. 소스 ID 부여: 영상 `v01, v02…`, 사이트 `s01…`

## Phase 2: 영상 데이터 수집 (오케스트레이터 직접)

`youtube-visual-summary` 스킬의 스크립트를 재사용한다 (중복 구현 금지):

```bash
python3 .claude/skills/youtube-visual-summary/scripts/setup_venv.py
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/env_check.py --json
# 영상별로 순차 실행 (동시 yt-dlp는 429 위험)
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/fetch_youtube.py "URL" --run-root RUN/_sources
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/build_transcript.py RUN/_sources/{video_run}
```

- 자막 정책: **원어 자막을 정본으로** 한다 (번역 자막은 고유명사를 훼손 — 세미나 하네스에서 확인된 정책)
- 자막 없음 → 기존 STT 폴백(`stt_transcribe.py`, mlx-whisper)을 사용자에게 제안하고 승인받아 적용
- 영상 1개 fetch 실패 → 1회 재시도 → 재실패 시 누락 목록에 기록하고 진행 (brief에 반영)

## Phase 3: 소스별 분석 (서브 에이전트 병렬)

단일 메시지에서 Agent 도구로 **최대 3~5개씩** 호출한다 (남은 소스는 앞 배치 완료 후):

| 에이전트 | 입력 | 출력 | model | run_in_background |
|----------|------|------|-------|-------------------|
| video-analyst × N | 영상 run 경로 + ID + brief 경로 | `_work/10_video_{id}.json` | opus | true |
| docs-analyst × M | 사이트 URL + ID + brief 경로 | `_work/20_site_{id}.json` | opus | true |

- 각 프롬프트에 에이전트 정의(`.claude/agents/{name}.md`)가 지시하는 입출력 경로를 구체적으로 전달
- 반환 메시지에서 실패·이슈 수집 → 누락 소스는 brief에 기록
- 과반(>50%) 실패 시 사용자에게 진행 여부 확인

## Phase 3.5: 비주얼 자산 — 프레임 추출·선정

리뷰 영상은 제품 UI 데모가 핵심 증거다 — 텍스트만으로는 전달되지 않는다. 프레임은 Phase 3의 분석이 끝난 뒤 합성 전에 준비한다.

**3-5-1. 프레임 후보 추출 (오케스트레이터 직접, 영상별 순차):**

1. video-analyst의 `structure`를 `chapters.codex.json`으로 변환해 `VIDEO_RUN/_work/`에 저장 (오케스트레이터가 직접 변환 — id/title/start/end/visual_query 매핑)
2. `youtube-visual-summary` 스킬의 스크립트를 재사용한다:

```bash
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py VIDEO_RUN
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/extract_frames.py VIDEO_RUN
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/make_contact_sheets.py VIDEO_RUN
```

- 1080p WebP(q88) 원본 해상도 유지 — 업스케일 금지 (기존 정책)
- 다운로드 실패 시 프레임 라인만 중단, 텍스트 리포트로 진행 (누락 명시)

**3-5-2. 프레임 선정 (visual-producer 서브 에이전트 1회, model: opus):**

- 컨택트 시트를 눈으로 검사해 리포트 섹션(기능 가이드·검증 표 등)에 어울리는 프레임을 선정한다
- 선정 기준: `youtube-visual-summary/references/frame-selection-rubric.md` (시맨틱 매치 > 정보 가치 > 가독성 > 선명도)
- 출력: `RUN/images/`로 복사 + `_work/30_visual_manifest.json`

```json
{ "assets": [
    { "section": "4.1 Tasks", "video_id": "v01", "path": "images/v01-tasks-95.webp",
      "t": 95.2, "alt": "Tasks 실행 화면", "caption": "개발동생 리뷰 — Tasks 실행 화면 (1:35)", "reason": "선정 근거" }
], "failed": [ { "section": "", "reason": "" } ] }
```

- **캡션에 출처(채널명 + 타임스탬프) 필수** — 프레임은 원저작물 인용이다. 캡션은 독자가 읽는 문구다: 내부 ID(V1)가 아니라 채널명 등 독자가 아는 이름으로 쓴다
- 한 섹션에 1~2장이 원칙 (리포트가 스크린샷 집합으로 변질되지 않도록)

**3-5-3. 합성 연계:** Phase 4에서 synthesizer가 manifest를 추가 입력으로 받아 해당 섹션 위치에 `![alt](path)` + `*caption*` 을 삽입한다.

## Phase 4: 합성 (서브 에이전트 단일)

`report-synthesizer` 1회 호출 → `RUN/report.md`.

프롬프트에: brief 경로, `_work/` 내 모든 분석 JSON 경로, 누락 소스 목록, `_work/30_visual_manifest.json` (프레임 준비된 경우 — 해당 섹션에 이미지 삽입).

## Phase 5: QA + 수정 루프 (서브 에이전트 단일)

`report-qa` 1회 호출 → `_work/40_qa.json`.

- `verdict: fail` → blockers를 들고 report-synthesizer 재호출 → QA 재실행 (최대 2회 루프)
- 2회 후에도 blocker가 남으면 산출은 하되 사용자에게 명시 보고

## Phase 6: 렌더링 + 최종 보고

```bash
.venv/bin/python .claude/skills/research-synthesis-report/scripts/render_report_html.py RUN_DIR
```

- `report.md`에서 h1(제목)·h2/h3(목차·섹션 번호)·표·인용구(⚠️ 시작 시 경고 스타일)를 파싱해 학습사이트 레이아웃(사이드바 목차 + 스크롤 스파이 + 진행률 바 + 다크모드)의 `report.html`을 만든다
- 의존: `markdown` 패키지. 없으면 `uv pip install --python .venv/bin/python markdown`

사용자에게 보고: 리포트 경로(md+html), 리서치 질문별 핵심 답변 요약, 소스별 상태(성공/누락), 상충·미해결 목록. `_work/`, `_sources/`는 보존한다 (감사 추적).

## 최종 산출물

```
runs/{ts}_research-{slug}/
├── report.md              ← 최종 종합 리포트 (Markdown)
├── report.html            ← 동일 내용 (학습사이트 레이아웃, Phase 6 렌더)
├── images/                ← 선정된 영상 프레임 (Phase 3.5, HTML이 상대참조)
├── _work/                 ← 분석 산출물 (감사 추적용 보존)
│   ├── 00_brief.md
│   ├── 10_video_v01.json …
│   ├── 20_site_s01.json …
│   └── 40_qa.json
└── _sources/              ← 영상별 원본 수집 (fetch_youtube.py 출력)
```

## 데이터 전달 프로토콜

- **파일 기반(주)**: `_work/` 번호 접두 파일 — 모든 에이전트가 여기로 주고받는다
- **반환값 기반(보조)**: 각 서브 에이전트의 완료 메시지(성공/실패 요약)를 오케스트레이터가 수집
- 에이전트 간 직접 통신은 유도하지 않는다 — 독립성이 품질 보장 장치다 (특히 synthesizer↔qa 분리)

## 에러 핸들링

| 상황 | 대응 |
|------|------|
| 자막 없는 영상 | STT 폴백 제안 → 거부 시 메타데이터만으로 분석하거나 누락 처리 |
| 사이트 전체 접근 불가 | 1회 재시도 → 재실패 시 누락 명시 (영상만으로 합성) |
| 소스 과반 실패 | 사용자에게 진행 여부 확인 |
| 에이전트 429/중단 | 1회 재시도 → 순차 실행 전환 |
| QA 2회 루프 후 blocker 잔존 | 산출 + 문제 명시 보고 |
| 소스 간 상충 | 삭제 금지, 병기 (모든 에이전트 공통 원칙) |

**공통 원칙:** 1회 재시도 후 재실패하면 그 결과 없이 진행하고, brief와 최종 보고에 누락을 명시한다. 침묵하는 누락 금지.

## 테스트 시나리오

### 정상 흐름
1. 사용자: "이 리뷰 3개랑 공식 문서 합쳐서 종합 리포트 만들어줘 [URL×3] [docs URL]"
2. Phase 1: 리서치 질문 확정(사용자 확인) → brief 작성, run 생성
3. Phase 2: 영상 3개 자막 순차 수집 (`RUN/_sources/`)
4. Phase 3: video-analyst 3 + docs-analyst 1 (배치 실행) → 분석 JSON 4개
5. Phase 4: synthesizer가 교차 검증·합성 → `report.md`
6. Phase 5: QA verdict `pass_with_fixes` → minor 수정 1회 → 완료
7. 결과: `runs/{ts}_research-{slug}/report.md`

### 에러 흐름 (자막 없음 + 사이트 일부 실패)
1. 영상 2번 자막 없음 → STT 폴백 제안, 사용자 승인 → 전사 후 분석 (caption_source: stt)
2. 사이트 일부 페이지 empty-render → pages_failed 기록, 나머지로 분석
3. synthesizer가 누락을 리포트 '소스 및 누락'에 명시 → QA가 누락 명시 여부 검증

### 후속 흐름 (확장 실행)
1. 사용자: "새 리뷰 영상 하나 추가했어, 리포트 업데이트해줘"
2. Phase 0: 확장 실행 판정 → 기존 run에 새 영상만 fetch·분석 (ID v04)
3. 기존 v01~v03, s01 분석은 재사용 → synthesizer·QA만 재실행

## 참고

- 소스 스키마: `references/source-schemas.md`
- 리포트 구조·문체: `references/report-writing-guide.md`
- QA 체크리스트: `references/qa-checklist.md`
- 문서 사이트 순회: `../docs-site-crawl/SKILL.md`
- 수집 트러블슈팅: `../youtube-visual-summary/references/troubleshooting.md`
