# Workflow

Use this checklist for each request.

1. Normalize the user request.
   - Extract the YouTube URL.
   - Map Korean or English detail words to `short`, `normal`, or `detailed`.
   - Default to `normal` when unspecified.

2. Prepare `.venv`.
   - Run `python3 skills/youtube-visual-summary/scripts/setup_venv.py` from the project root.
   - Tell the user this keeps Python packages inside the project root.
   - After this step, run Python scripts with `.venv/bin/python skills/youtube-visual-summary/scripts/...`.

3. Run `env_check.py`.
   - Required: `yt-dlp`, `ffmpeg`, `ffprobe`, Python 3.
   - Recommended: `Pillow` for contact sheets.
   - Do not check or install STT packages unless captions are absent and the user accepts STT.

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
   - It downloads a balanced 720p-or-lower video-only `_work/frame-source.*` file.
   - It intentionally avoids audio and stream merging.
   - If this fails, the text summary can still be produced from captions.

8. Run `extract_frames.py` and `make_contact_sheets.py`.
   - Inspect contact sheets before choosing frames.
   - If no candidate matches the chapter, rerun extraction with a higher `--max-frames-per-chapter`.
   - Candidate frames and contact sheets are stored under `_work/frames/` and `_work/contact-sheets/`.

9. Create `_work/selected-frames.json`.
   - Include a short reason for every selected frame.
   - Prefer visual evidence over speaker faces.

10. Run `render_markdown.py`.
   - Return the root `summary.md` path.
   - Final images are copied to the root `images/` directory.
   - Mention if captions were auto-generated or if any chapter had weak visual evidence.
