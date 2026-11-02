# Summary Levels

Map user wording to one of three levels.

| User wording | Level |
| --- | --- |
| 짧게, 간단히, 핵심만, brief, short, concise | `short` |
| 보통, 일반, 요약, summarize, normal | `normal` |
| 자세히, 상세하게, 깊게, detailed, in depth | `detailed` |

## `short`

- Use broad chapters.
- Preserve only the core claim, conclusion, and major transition.
- Use 1-2 bullets per chapter.
- Keep `visual_query` focused on the single strongest visual anchor.

## `normal`

- Use natural topic transitions.
- Include important arguments, examples, and outcomes.
- Use 2-4 bullets per chapter.
- Preserve named entities, important numbers, and decisions.

## `detailed`

- Split chapters by the numbers in "챕터 나누기 수치" below (uploader chapters over 6 min only); keep enough context that the reader can follow the full argument.
- Write the chapter like detailed notes, not a compressed recap.
- Include conditions, caveats, comparisons, numbers, steps, examples, and the reason each point matters.
- Use 6-10 bullets per chapter when the content supports it.
- Keep separate facts separate. Do not merge distinct claims into one bullet just to shorten the section.
- Avoid duplicating repeated transcript phrases, but preserve nuance, sequence, and intermediate reasoning.
- When the chapter contains an example or a process, spell it out instead of collapsing it into one line.

## 챕터 나누기 수치

목적: 같은 영상이면 누가 언제 돌려도 챕터 경계가 같게 나오게 한다. 판단이 갈리던 곳을 모두 결정 규칙으로 바꾸고, 그 규칙을 `scripts/plan_chapters.py`가 계산한다. **Phase 4에서는 이 도구를 돌려 나온 `_work/chapter-plan.json`의 `start`·`end`를 그대로 쓴다.**

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/plan_chapters.py RUN_DIR --level detailed
```

**1. 출발점.** 업로더 챕터(`_work/metadata.json`의 `chapters`) → 없으면 설명란의 타임스탬프 목록(`0:00`부터 시작하는 `m:ss 제목` 줄 2개 이상) → 둘 다 없으면 영상 전체 한 덩어리.

**2. 문장과 넘김 문장.** 문장 시작 = 앞 단어가 `.` `?` `!`로 끝난 다음 단어. 유튜브 자동 자막은 단어마다 시각이 있어 그 첫 단어 시각을 쓴다(`find_moment.py`와 같은 방법, 표에 `sentence times: word`). 단어 시각이 없는 자막은 `transcript.json` 세그먼트 안 글자 위치로 어림한다(`estimate`). **넘김 문장** = 이 말로 시작하는 문장: `자,` `그렇다면` `그다음` `다음으로` `다음은` `이번에는` `첫(두·세·네·다섯) 번째` `마지막으로` `또 한 가지` `또 하나` `한편` `정리하면` `결론적으로` / `so` `now` `next` `first` `second` `third` `finally` `let's` `okay` `all right` `moving on` `in summary`. ("그럼"·"그러면"은 강의에서 말 중간에 너무 흔해 넣지 않는다.)

**3. 합치고 나누기 (업로더 챕터·설명란 목록이 있을 때).**

| 수준 | 나누기 | 합치기 |
| --- | --- | --- |
| `short` | 하지 않음 | 앞에서부터 묶는다: 묶음이 5분 미만이거나, 다음 챕터를 더해도 15분 이하면 더한다 |
| `normal` | **10분 넘는** 챕터를 ⌈길이 ÷ 8분⌉ 조각으로 | 1분 미만이면서 제목이 인사·광고·예고·인트로·아웃트로(`plan_chapters.py`의 `GREETING`)인 챕터만 다음 챕터에 붙임 |
| `detailed` | **6분 넘는** 챕터를 ⌈길이 ÷ 5분⌉ 조각으로 | 위와 같음 — 이름 붙은 개념(예: "뇌졸중 확인 FAST" 46초)은 그대로 |

**4. 경계 맞추기 (업로더 경계 B마다).** B에서 ±15초 안에 넘김 문장이 있으면 **B에 가장 가까운 넘김 문장의 첫 단어 시각**(같으면 앞의 것)으로 옮긴다. 없으면 B 그대로. 넘김 문장이 아닌 문장 시작으로는 옮기지 않는다(14초짜리 자막 줄 시작은 대개 문장 중간이다).

**5. 나누는 지점 (길이 L 챕터를 n조각으로).** 이상 지점 = 시작 + k·L/n. 허용 창 = 이상 지점 ± 0.3·L/n(2조각이면 각 조각이 L의 35~65%), 그리고 모든 조각은 2분 이상. 창 안에서 ① 이상 지점에 가장 가까운 **넘김 문장**의 첫 단어 → ② 없으면 가장 가까운 **문장 시작** → ③ 그것도 없으면 이상 지점 그대로. 화면 제목은 Phase 4에서는 볼 수 없으므로 여기서 쓰지 않는다.

**6. Phase 6 검증 (화면 주제 자막 바).** 컨택트 시트에서 화면 구석 주제 자막 바가 바뀌는 장면을 본다. 바 변경 시각 = **새 바 글자가 처음 보이는 후보의 manifest `timestamp`**(새 슬라이드가 떠도 바가 이전 글자면 아직 변경이 아니다). `split:`으로 시작하는 경계(5에서 정한 지점)가 든 업로더 챕터의 바 변경을 **모두** `plan_chapters.py RUN_DIR --level … --anchor T1 --anchor T2 …`로 넘긴다. 스크립트가 나누는 지점마다 ① 창 안의 바 변경 중 이상 지점에 가장 가까운 하나(같으면 앞의 것)를 고르고 ② 그것이 지금 지점과 **20초 넘게** 다르면 그 근처의 가장 가까운 문장 시작으로 옮긴다. 창 밖 변경은 무시하고, 업로더 경계(4)는 옮기지 않는다. anchor는 `chapter-plan.json`에 남아 다시 돌려도 같다. 왜 스크립트가 고르나: 한 업로더 챕터 안에서 바가 여러 번 바뀌면 사람이 고를 때마다 경계가 달라진다.

**7. 업로더 챕터도 설명란 목록도 없을 때.** 영상 전체를 ⌈길이 ÷ 목표⌉ 조각으로 5와 같은 규칙으로 나눈다.

| 수준 | 목표 | 63분 영상 |
| --- | --- | --- |
| `short` | 10분 | 7 |
| `normal` | 5.5분 | 12 |
| `detailed` | 3.5분 | 19 |

- 예: 63분 강의(업로더 챕터 16개, 46초~8분 26초). `detailed` → 6분 넘는 2개(7분 8초, 8분 26초)를 2조각씩 → **18개**. 나누는 지점은 4장 16:48("박지성 선수가…", 문장 시작 — Phase 6에서 바 변경 14:41·16:12를 넘기면 창(15:42~17:50) 안의 16:12 '뇌출혈의 종류 1. 뇌실질출혈'이 골라져 16:14로 옮겨진다. 17:28은 지주막하출혈 슬라이드가 떴지만 바가 아직 '1. 뇌실질출혈'이라 바 변경이 아니다)과 14장 50:37("자, 동맥류 같은 경우는", 넘김 문장). `normal` → 16개, `short` → 5개.

**8. 학습 보기(`study_view`)를 만들 때의 "짧은 단위"** — 챕터 = 학습 항목이다.
- 강의·발표·인터뷰: 위 규칙으로 나온 챕터를 그대로 쓴다(개념 하나 = 항목 하나, 보통 1~5분). 학습 보기 때문에 더 쪼개지 않는다. 한 챕터 안의 다른 슬라이드·도표는 장면 2·3(하위 장면)으로 들어간다.
- 용어집·기능 소개·단계별 튜토리얼처럼 영상 자체가 용어·단계 하나씩 다루면: 용어·단계 하나 = 챕터 하나(보통 10~40초). 영상 끝의 정리 화면이 공식 목록·개수를 정한다(`study-view.md`).

## Chapter Rules

- Every chapter needs a one-sentence `key_point` at every level (`check_summary.py` fails without it). The full field list — required/optional, where each field appears, per-level use — is the `chapters.codex.json` 필드 table in SKILL.md Phase 4.

- Use transcript timestamps as the source of truth.
- Chapter boundaries should follow meaning, not equal time slices.
- Each chapter must have an image-searchable `visual_query`.
- When the video is mostly talking head, write a visual query for the most relevant on-screen state, not a generic "speaker talking" frame.
