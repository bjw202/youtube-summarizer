# 소스 분석 스키마

video-analyst(`10_video_*.json`), docs-analyst(`20_site_*.json`), report-qa(`40_qa.json`)가 읽고 쓰는 표준 형식. 필드는 지시 사항이자 검증 기준이다 — report-qa가 이 스키마로 누락을 검사한다.

## 목차

1. [Video Analysis](#video-analysis-_work10_videoidjson)
2. [Site Analysis](#site-analysis-_work20_siteidjson)
3. [QA Report](#qa-report-_work40_qajson)

## Video Analysis (`_work/10_video_{id}.json`)

```json
{
  "id": "v01",
  "video": {
    "url": "", "title": "", "channel": "",
    "duration_sec": 0, "published_at": "",
    "caption_source": "manual | auto | stt"
  },
  "content_type": "review | tutorial | news | promo | other",
  "reviewer_stance": "긍정|중립|비판|혼합 — 한 문장 근거 포함",
  "structure": [
    { "time_range": [0, 95], "topic": "", "summary": "" }
  ],
  "claims": [
    {
      "id": "v01-c001",
      "type": "feature | performance | comparison | issue | pricing | roadmap | opinion",
      "claim": "문맥으로 정리한 주장 (고유명사는 복원 표기)",
      "verbatim": "자막 원문 발췌 (짧게)",
      "timestamp": 595,
      "sentiment": "positive | negative | neutral",
      "confidence": "high | medium | low"
    }
  ],
  "features_covered": [
    { "name": "UltraBrowse", "what_reviewer_said": "", "verdict": "칭찬|지적|중립|소개만" }
  ],
  "pros": ["구체적 근거 포함"],
  "cons": ["구체적 근거 포함"],
  "open_questions": [
    { "question": "리뷰가 답하지 못한 것", "docs_may_answer": true }
  ],
  "notable_quotes": [ { "text": "", "timestamp": 0 } ],
  "notes": "자막 훼손 등 분석 상 제약"
}
```

작성 규칙:

- claims 개수는 영상 길이와 밀도에 비례 — 10분 리뷰라면 최소 15개, 30분이면 최소 30개 수준. 단 억지로 채우지 않는다
- `timestamp`는 초 단위 숫자 (YouTube `&t=` 딥링크로 직결)
- id 체계: `{video_id}-c{3자리 연번}` (v01-c001 …)
- `sentiment`는 평가성 주장(opinion, performance, issue 등)에만 의미가 있다 — 소개형은 neutral

## Site Analysis (`_work/20_site_{id}.json`)

```json
{
  "id": "s01",
  "site": {
    "url": "",
    "framework": "mintlify | gitbook | docusaurus | unknown",
    "pages_crawled": 0,
    "pages_failed": [ { "url": "", "reason": "empty-render | fetch-error" } ]
  },
  "nav_map": [
    { "section": "Help", "pages": [ { "title": "Tasks", "url": "", "summary": "1~3문장" } ] }
  ],
  "facts": [
    {
      "id": "s01-f001",
      "topic": "tasks",
      "fact": "문서가 말하는 사실",
      "url": "", "section": "Help/Tasks",
      "confidence": "high | medium"
    }
  ],
  "features_documented": [ { "name": "", "description": "", "urls": [] } ],
  "answers_to_questions": [
    { "question": "brief의 리서치 질문 원문", "answer": "문서 기반 답변", "url": "", "found": true }
  ],
  "gaps": ["문서에 없어서 확인 불가였던 것"],
  "skipped_sections": ["페이지 과다로 생략한 섹션 — 있을 때만"]
}
```

작성 규칙:

- `topic`은 영상 분석의 `features_covered.name`과 대조 가능한 표기를 쓴다 (기능명은 문서 원어 그대로)
- 모든 fact는 URL 없이는 실리지 않는다
- brief에 리서치 질문이 있으면 `answers_to_questions`에 질문별 답을 채운다 (답 없으면 `found: false`)

## QA Report (`_work/40_qa.json`)

report-qa 에이전트 정의의 출력 형식을 따른다. verdict 기준:

- `fail`: 사실 오류, 출처 없는 주장, 타임스탬프 범위 위반, 리서치 질문 무답, 상충 은폐 중 하나라도 존재
- `pass_with_fixes`: minors(문체·구조 개선 사항)만 존재
- `pass`: 문제 없음 — `spot_checks`에 최소 5건의 대조 기록 포함
