# Workflow

Use this checklist for each request.

 1. Normalize the user request.

    - Extract the YouTube URL.
    - Map Korean or English detail words to `short`, `normal`, or `detailed`.
    - Default to `normal` when unspecified.

 2. Prepare `.venv`.

    - Run `uv run python .claude/skills/youtube-visual-summary/scripts/doctor.py --json` from the project root.
    - If `.venv` is missing or `ok` is false, run `uv run .claude/skills/youtube-visual-summary/scripts/install.py` (safe to repeat, no admin rights), then run the `fix` of any check still `ok: false`.
    - Tell the user this keeps Python packages inside the project root.
    - Run every script with `uv run python .claude/skills/youtube-visual-summary/scripts/...` (works on macOS, Linux and Windows).

 3. Read `doctor.py --json`.

    - `features` says what can run: `summary`, `text_only`, `study_view`, `stt`.
    - Speech recognition (`optional.stt`) is installed only when captions are absent and the user accepts (`install.py --with-stt`, about 1.5 GB).

 4. Run `fetch_youtube.py`.

    - It creates a run directory with user-facing output slots at the root and internal files under `_work/`.
    - It writes `_work/metadata.json`, `_work/input.json`, and captions under `_work/captions/`.
    - It does not download video. This keeps the first summary pass fast.

 5. Run `build_transcript.py`.

    - It creates `_work/transcript.json` from VTT captions.
    - If captions are absent, stop the default flow and offer optional STT.

 6. Create `_work/chapters.codex.json`.

    - Use transcript timestamps.
    - Avoid tiny chapters unless the user requested detailed output and the topic actually changes.
    - For `detailed`, write chapter notes that feel like a detailed walkthrough, not a compact summary.
    - Add a concrete `visual_query` for each chapter.

 7. Run `fetch_frame_source.py` by default unless the user explicitly asked for text-only output.

    - Start it in the background right after the captions (SKILL.md Phase 3) and wait for it before Phase 5.
    - It downloads a 720p-or-lower video-only `_work/frame-source.*` file; `--with-audio` (study view) gets one 1080p file with sound.
    - If it fails: retry once, then run `install.py` (upgrades yt-dlp) and retry, then report the cause. Do not fall back to a text-only summary silently.

 8. Run `extract_frames.py` and `make_contact_sheets.py`.

    - Inspect contact sheets before choosing frames.
    - If no candidate matches the chapter, rerun extraction with a higher `--max-frames-per-chapter`.
    - Candidate frames and contact sheets are stored under `_work/frames/` and `_work/contact-sheets/`.

 9. Create `_work/selected-frames.json` with `frame_id`, `caption` and `reason` per scene, then run `fill_selections.py RUN_DIR`.

    - It fills `chapter_id`, `timestamp` and `image_path` (relative to `_work/`) from `_work/frames/manifest.json`.
    - Include a short reason for every selected frame; `caption` is what readers see under the picture (`references/frame-selection-rubric.md`).
    - Prefer visual evidence over speaker faces.

10. Run `render_markdown.py`.

- Return the root `summary.md` path.
- Final images are copied to the root `images/` directory.
- Mention if captions were auto-generated or if any chapter had weak visual evidence.