# deck.json 스키마 표준

모든 에이전트가 공유하는 데이터 계약. 필드명을 임의로 바꾸면 `render_deck.py`와 `validate_deck.py`가 깨진다.

## 최상위

```json
{
  "meta": {},
  "sections": [],
  "slides": [],
  "glossary": [],
  "references": [],
  "gaps": []
}
```

## meta

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `title` | string | ✓ | 보고서 제목 (원 발표 제목을 그대로 쓰지 말고 독자가 이해할 제목으로) |
| `subtitle` | string | | 한 줄 부제 |
| `speaker` | string | | 발표자 |
| `venue` | string | | 소속·행사 |
| `date` | string | | 발표일 `YYYY-MM-DD` |
| `source_url` | string | ✓ | 원본 YouTube URL. 타임스탬프 딥링크 생성에 쓰인다 |
| `video_id` | string | | |
| `duration_sec` | number | ✓ | 타임스탬프 범위 검증에 쓰인다 |
| `audience` | string | ✓ | 예: `"관련 전공자가 아닌 엔지니어"` |

## sections

```json
{ "id": "sec1", "title": "촉각 센싱은 왜 어려운가", "goal": "이 섹션을 읽고 나면 알게 되는 것" }
```

`id`는 `slides[].section_id`가 참조한다. 유효하지 않으면 validate가 major로 잡는다.

## slides

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `id` | string | ✓ | `s01` 형식. **한 번 정하면 바꾸지 않는다** — 자산 경로와 링크가 이 ID에 묶인다 |
| `section_id` | string | ✓ | |
| `kind` | enum | ✓ | 아래 표 참조 |
| `title` | string | ✓ | 슬라이드 제목 |
| `lead` | string | | 한 줄 핵심 메시지. 두 문장이 되면 슬라이드를 쪼갠다 |
| `bullets` | string[] | | 4개 이하, 한 줄 90자 이하 |
| `html_body` | string | | 표 등 사전 렌더된 HTML 조각. **신뢰된 입력으로만 사용**(이스케이프 안 됨) |
| `visual` | object | | 아래 참조 |
| `notes` | object | | 아래 참조 |

**kind 열거값:** `cover` `agenda` `section` `problem` `prereq` `concept` `architecture` `math` `demo` `result` `limitation` `qa` `takeaway` `refs` `glossary`

### slides[].visual

```json
{ "type": "svg|frame|none", "src": "assets/svg/pipeline.svg",
  "alt": "스크린리더용 설명", "caption": "그림 캡션" }
```

- `src`는 **run 디렉토리 기준 상대 경로**
- `type: "frame"`이면 캡션에 출처 타임스탬프(`0:00` 형식)를 포함한다 — 인용 표기 의무
- 자산이 없으면 `type: "none"`으로 두고 `src`를 비운다. 존재하지 않는 경로를 남기면 blocker

### slides[].notes

```json
{
  "why": "이 슬라이드가 왜 중요한가 (1~2문장)",
  "explain": ["해설 문단", "해설 문단"],
  "analogy": "일상 비유",
  "terms": ["extrinsic contact"],
  "source": { "t": 812, "quote": "원문 발췌" },
  "research": [{ "claim": "", "title": "", "url": "" }],
  "caveat": "불확실하거나 발표에서 언급되지 않은 사항"
}
```

- `terms`에 넣은 용어는 **반드시 `glossary`에도 있어야 한다** (없으면 major)
- `source.t`는 초 단위 숫자. `duration_sec` 범위를 넘으면 major
- `research[].url`이 없으면 major
- `kind`가 `result`/`math`인데 `source.t`도 `research`도 없으면 major
- `kind: "math"`인데 `explain`이 비면 major — 수식은 반드시 문장으로 번역한다

## glossary

```json
{ "term": "extrinsic contact", "ko": "외재적 접촉",
  "def": "한두 문장 정의", "first_slide": "s07" }
```

`term`은 원어를 정본으로 쓴다. 독자가 검색할 수 있어야 한다.

## references

```json
{ "title": "논문/문서 제목", "url": "https://…", "note": "왜 읽을 가치가 있는지" }
```

## gaps

문자열 배열. **보고서가 다루지 못한 것과 그 이유**를 적는다. 비워두지 않는다 — 완벽한 보고서는 없고, 무엇을 안 다뤘는지 밝히는 것이 신뢰의 근거다.

```json
["Q&A 후반 15분의 위원회 심화 질문은 자막 품질 문제로 요약만 수록",
 "s21 다이어그램은 codex 3라운드 실패로 텍스트 설명으로 대체"]
```

## 자동 추가되는 슬라이드

`render_deck.py`가 덱 끝에 자동으로 붙인다. **deck.json에 직접 쓰지 않는다.**

| 슬라이드 ID | 조건 |
|------------|------|
| `apx-glossary` | `glossary`가 비어있지 않음 |
| `apx-refs` | `references`가 비어있지 않음 |
| `apx-gaps` | `gaps`가 비어있지 않음 |
