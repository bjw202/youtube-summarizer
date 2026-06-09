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

- Use finer chapters when the speaker changes subtopics, but keep enough context that the reader can follow the full argument.
- Write the chapter like detailed notes, not a compressed recap.
- Include conditions, caveats, comparisons, numbers, steps, examples, and the reason each point matters.
- Use 6-10 bullets per chapter when the content supports it.
- Keep separate facts separate. Do not merge distinct claims into one bullet just to shorten the section.
- Avoid duplicating repeated transcript phrases, but preserve nuance, sequence, and intermediate reasoning.
- When the chapter contains an example or a process, spell it out instead of collapsing it into one line.

## Chapter Rules

- Use transcript timestamps as the source of truth.
- Chapter boundaries should follow meaning, not equal time slices.
- Each chapter must have an image-searchable `visual_query`.
- When the video is mostly talking head, write a visual query for the most relevant on-screen state, not a generic "speaker talking" frame.
