---
name: technical-seminar-deck
description: "기술 세미나·논문 디펜스·학술 발표 영상을 비전공 엔지니어도 이해할 수 있는 상세 HTML 슬라이드덱 보고서로 재구성. 리서치 보강 + codex SVG 다이어그램 생성 + 영상 프레임 삽입을 포함한 종합 보고서를 만든다. 다음 요청 시 반드시 이 스킬을 사용할 것 — '이 영상 테크니컬하니까 제대로 정리해줘', '세미나/강연/디펜스/컨퍼런스 발표 정리', '슬라이드덱 보고서', '심층 보고서', '종합 보고서', 'HTML 발표자료로 만들어줘', '비전공자도 이해하게', '리서치로 보강해서 정리', 'codex로 이미지/다이어그램 만들어서 넣어줘'. 후속 작업 — 덱 다시 만들어줘, 슬라이드 추가/삭제/수정, 해설 더 자세히, 다이어그램 다시 그려줘, 리서치 보강, 특정 슬라이드만 재작업 — 요청 시에도 반드시 이 스킬을 사용. 단순 영상 요약(요약본 하나만 필요)은 youtube-visual-summary를 사용한다."
---

# Technical Seminar Deck — 기술 세미나 심층 보고서

기술 세미나 영상을 **슬라이드덱 + 슬라이드별 해설 노트** 형태의 자기 완결형 HTML 보고서로 재구성하는 오케스트레이터.

**youtube-visual-summary와의 차이:** 그 스킬은 영상을 *요약*한다. 이 스킬은 영상을 *교재로 재저작*한다 — 순서를 독자 이해 순으로 재배열하고, 외부 리서치로 빈틈을 메우고, 없는 그림은 새로 그린다.

## 실행 모드: 하이브리드

| Phase | 모드 | 이유 |
|-------|------|------|
| 1~2 (수집·분석) | 단일(오케스트레이터 직접) | 순차 파이프라인, 병렬 이득 없음 |
| 3 (분석 + 리서치) | 서브 에이전트 병렬 | 두 작업이 독립적, 결과만 회수하면 충분 |
| 4~6 (기획·비주얼·집필) | 에이전트 팀 | 스펙 실현 불가 항목 회신, 근거 부족 시 추가 조사 요청 등 실시간 상호 조율이 필요 |
| 7 (QA) | 서브 에이전트 | 독립적 검증이 목적. 팀 내부에 있으면 검증자가 생산자에게 동조된다 |

모든 Agent 호출에 `model: "opus"`를 명시한다.

## Phase 0: 컨텍스트 확인

1. `runs/` 에서 대상 URL의 기존 run 디렉토리를 찾는다
2. 실행 모드를 결정한다:

| 상태 | 모드 | 동작 |
|------|------|------|
| run 없음 | **초기 실행** | Phase 1부터 전체 |
| run 있음 + `_work/05_deck.json` 없음 | **이어하기** | 존재하는 최신 산출물 다음 Phase부터 |
| run 있음 + 부분 수정 요청 | **부분 재실행** | 해당 산출물 담당 에이전트만 재호출, 하위 산출물 재생성 |
| run 있음 + 다른 URL | **새 실행** | 새 run 디렉토리 |

**부분 재실행 의존 관계** — 상위가 바뀌면 하위를 다시 만든다:
`01_ledger` → `02_research` → `03_plan` → `04_visual` → `05_deck` → `deck.html`

## Phase 1: 입력 파싱

- `url` (필수)
- `audience`: 기본 `"관련 전공자가 아닌 엔지니어"`
- `depth`: `standard`(30~45장) | `deep`(45~60장). 기본 `standard`
- `visuals`: `both`(기본) | `frames_only` | `diagrams_only`
- `research`: `on`(기본) | `off`

## Phase 2: 데이터 수집

`youtube-visual-summary` 스킬의 스크립트를 그대로 재사용한다. 중복 구현하지 않는다.

```bash
python3 .claude/skills/youtube-visual-summary/scripts/setup_venv.py
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/env_check.py --json
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/fetch_youtube.py "URL" --run-root runs
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/build_transcript.py RUN_DIR
```

**자막 언어 정책이 요약 스킬과 다르다.** 기술 세미나는 자동 번역 자막이 고유명사를 파괴한다(`tactile`→"타칼", `Tac2Pose`→"TCTO 포스트"). 따라서 **원어 자막을 정본으로 삼는다.** `_work/captions/` 에 원어 파일이 있으면 그것을 seminar-analyst에게 넘기고, 번역 자막은 보조로만 전달한다.

자막이 아예 없으면 `scripts/stt_transcribe.py`(mlx-whisper) 사용을 사용자에게 제안한다.

## Phase 3: 분석 + 리서치 (서브 에이전트 병렬)

**3-1.** `seminar-analyst`를 호출한다 → `_work/01_analyst_ledger.json`

**3-2.** ledger의 `open_questions` / `terms[needs_research]` / `visual_gaps`를 입력으로 `research-augmenter`를 호출한다 → `_work/02_research_pack.json`

두 호출은 순차 의존이지만, ledger 초안이 나온 뒤에는 리서치와 이후 프레임 소스 다운로드(`fetch_frame_source.py`)를 병렬로 돌린다.

```bash
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR
```

## Phase 4~6: 기획 · 비주얼 · 집필 (에이전트 팀)

`TeamCreate`로 팀을 구성한다: `deck-planner`, `visual-producer`, `deck-writer`. `TaskCreate`로 아래 작업을 의존 관계와 함께 등록하고, 팀원들은 `SendMessage`로 직접 조율한다.

### 4. deck-planner → `_work/03_deck_plan.json`

`references/deck-planning-guide.md`를 읽고 따른다. 슬라이드 유형·용어 예산·비주얼 배분 원칙이 거기 있다.

플랜 완성 후 오케스트레이터가 다이어그램 스펙만 뽑아 `_work/04_diagram_specs.json`으로 저장한다:

```json
{ "diagrams": [ { "slug": "", "kind": "", "intent": "", "elements": [], "labels_ko": [], "must_not": [], "context": "", "width": 1000, "height": 620 } ] }
```

### 5. visual-producer → `assets/`, `_work/04_visual_manifest.json`

**5-1. 영상 프레임 (라인 A)**

```bash
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/extract_frames.py RUN_DIR
.venv/bin/python .claude/skills/youtube-visual-summary/scripts/make_contact_sheets.py RUN_DIR
```

컨택트 시트를 눈으로 검사해 슬라이드별 최적 프레임을 고른 뒤 `assets/frames/{slide_id}.jpg`로 복사한다. 선택 기준은 `youtube-visual-summary/references/frame-selection-rubric.md`.

프레임 추출은 `chapters.codex.json`을 요구한다. deck plan의 슬라이드 중 `visual.type == "frame"`인 것들을 챕터로 변환해 먼저 써준다.

**5-2. codex SVG 다이어그램 (라인 B)**

```bash
.venv/bin/python .claude/skills/technical-seminar-deck/scripts/codex_svg.py RUN_DIR \
  --spec RUN_DIR/_work/04_diagram_specs.json
```

`references/codex-svg-guide.md`를 읽고 스펙을 작성한다. 스크립트가 검증·재시도를 처리하지만, **생성된 SVG를 반드시 눈으로 확인한다** — 자동 검증은 텍스트 겹침이나 논리적 오류를 잡지 못한다. 문제가 있으면 스펙에 `review_note`를 추가하고 `--only {slug} --force`로 재생성한다.

### 6. deck-writer → `_work/05_deck.json`

`references/explainer-writing-guide.md`(문체·눈높이)와 `references/deck-schema.md`(스키마)를 읽고 따른다.

## Phase 7: 렌더링 + QA

```bash
.venv/bin/python .claude/skills/technical-seminar-deck/scripts/render_deck.py RUN_DIR
.venv/bin/python .claude/skills/technical-seminar-deck/scripts/validate_deck.py RUN_DIR
```

`render_deck.py`는 SVG를 인라인하고 이미지를 base64로 임베드해 **HTML 한 파일**을 만든다. 용어집·참고문헌·누락 슬라이드는 자동으로 덱 끝에 붙는다.

`validate_deck.py` 종료 코드가 0이 아니면 그 결과를 들고 `deck-qa` 서브 에이전트를 호출한다. QA는 자동 검사가 못 잡는 사실 정합성·눈높이·렌더 결과를 검증하고 `_work/06_qa_report.json`을 낸다.

- `verdict: fail` → 담당 에이전트에게 수정 지시 후 Phase 7 재실행 (최대 2회)
- 2회 후에도 blocker가 남으면 산출은 하되 남은 문제를 사용자에게 명시 보고

## 최종 산출물

```
runs/{ts}_{slug}/
├── deck.html              ← 자기 완결형 슬라이드덱 보고서 (단일 파일)
├── deck.md                ← 동일 내용 Markdown
├── assets/
│   ├── frames/{slide_id}.jpg
│   └── svg/{slug}.svg
└── _work/                 ← 중간 산출물 (감사 추적용, 보존)
    ├── 01_analyst_ledger.json
    ├── 02_research_pack.json
    ├── 03_deck_plan.json
    ├── 04_diagram_specs.json
    ├── 04_visual_manifest.json
    ├── 05_deck.json
    └── 06_qa_report.json
```

## 데이터 전달 프로토콜

- **파일 기반**(주): `_work/` 하위 번호 접두 파일. 모든 에이전트가 읽고 쓴다
- **태스크 기반**: Phase 4~6 팀의 진행·의존 관계
- **메시지 기반**: 스펙 명확화, 추가 조사 요청, QA 수정 요구
- **반환값 기반**: Phase 3, 7의 서브 에이전트 결과

## 에러 핸들링

| 상황 | 대응 |
|------|------|
| 원어 자막 없음 | 번역 자막으로 진행 + 리서치로 고유명사 복원. 모든 기술 용어에 uncertain 표시 |
| 자막 전무 | `stt_transcribe.py` 제안. 거부 시 중단 |
| codex CLI 없음/미인증 | 전체 중단하지 않는다. diagram 슬라이드를 `visual.type: none`으로 폴백하고 보고서 `gaps`에 명시 |
| codex SVG 3라운드 실패 | 해당 다이어그램 포기, 해설 노트에 텍스트 설명으로 대체, `gaps`에 기록 |
| 영상 다운로드 실패 | 프레임 라인 중단, 전량 diagram으로 전환, 사용자에게 보고 |
| 리서치 결과 없음(`found:false`) | 해당 주장을 삭제하고 `gaps`에 기록. 추측으로 채우지 않는다 |
| 리서치와 발표가 상충 | 삭제하지 않고 노트에 양쪽 병기 + `caveat`에 시점 차이 설명 |
| validate_deck 종료 2 (blocker) | 산출 보류, 담당 에이전트 수정, 재검증 |
| deck.html 20MB 초과 | 프레임 JPEG 품질/폭을 낮춰 재추출 |

**공통 원칙:** 1회 재시도 후 재실패하면 그 결과 없이 진행하고, 보고서 `gaps`와 사용자 보고에 누락을 명시한다. 상충 데이터는 지우지 않고 출처를 병기한다.

## 테스트 시나리오

### 정상 흐름
1. 사용자: "이 논문 디펜스 영상 테크니컬하니까 슬라이드덱 보고서로 정리해줘 [URL]"
2. Phase 2에서 원어 자막 확보 → seminar-analyst가 ledger 생성
3. research-augmenter가 자막이 훼손한 시스템명을 원어로 복원
4. deck-planner가 38장 구성, 그중 14장에 diagram 스펙 부여
5. visual-producer가 프레임 24장 선정 + codex로 SVG 14개 생성(2개는 2라운드)
6. deck-writer가 deck.json 완성 → render_deck.py로 단일 HTML 산출
7. validate_deck 종료 0, deck-qa verdict `pass_with_fixes` → minor 3건 수정 후 완료

### 에러 흐름 (codex 미인증)
1. Phase 5-2에서 `codex_svg.py`가 exit 127 또는 전 다이어그램 실패
2. visual-producer가 오케스트레이터에 보고, diagram 슬라이드를 `visual.type: none`으로 폴백
3. deck-writer가 해당 슬라이드 노트에 텍스트 설명을 강화하고 `gaps`에 기록
4. 산출물은 정상 생성, 사용자 보고에 "다이어그램 14개 미생성 — codex 인증 필요" 명시

### 후속 흐름 (부분 재실행)
1. 사용자: "s12 다이어그램 라벨이 겹쳐. 다시 그려줘"
2. Phase 0에서 부분 재실행 판정 → `04_diagram_specs.json`의 해당 slug에 `review_note` 추가
3. `codex_svg.py --only {slug} --force` 실행 → visual-producer가 검수
4. `render_deck.py` 재실행. ledger/research/plan/deck.json은 건드리지 않는다

## 참고

- 스키마 표준: `references/deck-schema.md`
- 기획 가이드: `references/deck-planning-guide.md`
- 집필 가이드: `references/explainer-writing-guide.md`
- codex 위임 규격: `references/codex-svg-guide.md`
- 프레임 선택 기준: `../youtube-visual-summary/references/frame-selection-rubric.md`
- 수집 트러블슈팅: `../youtube-visual-summary/references/troubleshooting.md`
