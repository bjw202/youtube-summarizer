# Frame Selection Rubric

Select one frame per chapter after inspecting contact sheets and individual candidates as needed.

Score candidates mentally in this order:

1. Semantic match: the frame shows what the chapter summary discusses.
2. Information value: charts, slides, product screens, demos, tables, documents, code, maps, or objects beat a generic face shot.
3. Readability: important text and numbers are visible enough to support the summary.
4. Clarity: avoid motion blur, black frames, transitions, overlays, and heavily cropped content.
5. Specificity: prefer a frame unique to this chapter over a frame that could fit any part of the video.

Use speaker-face frames only when:

- the chapter is about the speaker's identity, expression, interview, reaction, or personal story
- no relevant visual content appears after denser sampling

If all candidates are bad:

1. Rerun `extract_frames.py RUN_DIR --max-frames-per-chapter 16`.
2. Rerun `make_contact_sheets.py RUN_DIR`.
3. Reinspect candidates.
4. If still weak, choose the least misleading frame and state the limitation in `reason`.

`selected-frames.json` must include `reason` because it proves the image was chosen by comparison rather than a midpoint capture.
