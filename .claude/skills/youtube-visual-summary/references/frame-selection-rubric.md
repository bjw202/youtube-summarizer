# Frame Selection Rubric

Inspect the contact sheets (`RUN_DIR/_work/contact-sheets/<chapter_id>-sheet-01.jpg`)
and single candidates (`RUN_DIR/_work/frames/<chapter_id>/<frame_id>.jpg`) as needed.
Write only `frame_id`, `caption`, `reason` (and `after_bullet`) to
`RUN_DIR/_work/selected-frames.json`, then run `fill_selections.py RUN_DIR` — it fills
`chapter_id`, `timestamp` and `image_path` (relative to `RUN_DIR/_work/`) from
`_work/frames/manifest.json`.

## How many scenes per chapter

**One scene per chapter by default.** Pick the best one in the order below.

Add a **second (third …) scene** only when it shows information the first does not, and
the summary text refers to it:

- a **different slide, chart, table or diagram** — different content, not the same slide
  with a red circle or highlight added, not a zoomed copy
- the **before and after** of a demo (empty form → filled result, code → its output,
  setting off → on)
- a screen whose **exact text the bullets quote** (a prompt, a command, a menu path)
  that the first scene does not show

Never add one for: another camera angle or close-up of the speaker, the channel title
card, the same slide again, a transition frame.

Caps — pass the row's number to `fill_selections.py --max-per-chapter` (it fails above it; default 6):

| Video | Scenes per chapter |
| --- | --- |
| `short` summary (any video) | 1 |
| Lecture, talk, interview, news (`normal`, `detailed`) | up to 3 |
| Screen demo, tutorial, product tour (step-by-step screens) | up to 6 |

Each scene after the first gets `after_bullet` — the 0-based bullet it illustrates — so
it sits next to the text it supports. In the study view it becomes tab '장면 2', '장면 3'
of that chapter.

## `caption` — write it for every scene

`caption` is what readers see: the figure caption under the picture in summary.md /
summary.html, the image alt text, and the name of the '장면 n' sub-scene in the study
view. Without it, `reason` (an internal note such as "the only diagram among the
candidates") is printed under the picture instead.

- Say what is **on screen**, as a short noun phrase (about 40 characters): the slide or
  chart title and its key figure — "뇌졸중 아형 비율 원그래프: 출혈 26%, 허혈 71%".
- If the screen has no text worth naming (speaker only), quote the key sentence spoken
  at that moment: “119를 타고 여러분들이 가시게 되면”.
- Spell names as checked on screen; numbers in a caption follow the same rule as the
  summary (`verified_numbers` for numbers read off the screen).

`reason` stays required: why this frame beat the other candidates (and its limits, e.g.
"no slide in this chapter — speaker only").

## Topic bar on screen — check the chapter split points

While looking at the sheets, note where the on-screen topic bar (a lecture's corner title
such as "뇌출혈의 종류 2. 지주막하출혈") changes. A bar change is the manifest timestamp of
the first candidate whose bar shows the new text — a new slide under the old bar is not one.
If `_work/chapter-plan.json` has a boundary whose `start_rule` begins with `split:`, pass every
bar change inside that uploader chapter:
`plan_chapters.py RUN_DIR --level <level> --anchor T1 --anchor T2 …`. The script picks one per
split point (nearest the ideal point, inside the window, more than 20 s away) — do not pick
yourself (SKILL.md Phase 6, `summary-levels.md` "챕터 나누기 수치" 6).

## Scoring order

1. Semantic match: the frame shows what the chapter summary discusses.
2. Information value: charts, slides, product screens, demos, tables, documents, code, maps, or objects beat a generic face shot.
3. Readability: important text and numbers are visible enough to support the summary.
4. Clarity: avoid motion blur, black frames, transitions, overlays, and heavily cropped content.
5. Specificity: prefer a frame unique to this chapter over a frame that could fit any part of the video.

Use speaker-face frames only when:

- the chapter is about the speaker's identity, expression, interview, reaction, or personal story
- no relevant visual content appears after denser sampling

## When a slide you know about is missing

1. Look in `_work/frames/manifest.json` → `scene_detection.rejected` for scene changes near
   that time and why they were dropped (`same_picture`, `near_time_same_shot`,
   `chapter_edge`, `chapter_cap`, `outside_chapters`). A change up to 2 s before a chapter
   starts belongs to that chapter.
2. Find the second it is mentioned: `find_moment.py RUN_DIR "여기 보시면"`.
3. Add it: `extract_frames.py RUN_DIR --at <time> [--chapter <id>]`, then
   `make_contact_sheets.py RUN_DIR`.

If all candidates are bad:

1. Rerun `extract_frames.py RUN_DIR --max-frames-per-chapter 16`.
2. Rerun `make_contact_sheets.py RUN_DIR`.
3. Reinspect candidates.
4. If still weak, choose the least misleading frame and state the limitation in `reason`.

`selected-frames.json` must include `reason` because it proves the image was chosen by comparison rather than a midpoint capture.
