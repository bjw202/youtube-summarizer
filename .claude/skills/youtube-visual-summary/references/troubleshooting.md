# Troubleshooting

## Missing `yt-dlp`

First run:

```bash
python3 skills/youtube-visual-summary/scripts/setup_venv.py
```

Then rerun:

```bash
.venv/bin/python skills/youtube-visual-summary/scripts/env_check.py --json
```

Explain that `yt-dlp` is required to read metadata and captions from YouTube and should live inside the project-root `.venv`, not the user's system Python.

## Missing `ffmpeg`

Explain that `ffmpeg` is required to extract candidate frames from the downloaded frame-source video.

## Missing JS Runtime (deno or node)

yt-dlp requires a JavaScript runtime to solve YouTube's EJS challenges. Without it, some formats may be missing and caption downloads may fail with cryptic errors.

**Check:**

```bash
.venv/bin/python skills/youtube-visual-summary/scripts/env_check.py --json
```

If `has_js_runtime` is `false`, install deno (recommended):

```bash
curl -fsSL https://deno.land/install.sh | sh
```

Then add `$HOME/.deno/bin` to your PATH. Alternatively, install Node.js which also works.

The `fetch_youtube.py` script automatically adds `--remote-components ejs:github` when a JS runtime is detected, so no manual action is needed beyond installing the runtime.

## No Captions

Default behavior:

- Stop the workflow.
- Tell the user no manual or auto captions were available.
- Offer optional local STT only if they accept audio extraction, model download, and longer runtime.

Do not silently fall back to STT.

## Caption Download 429 (Too Many Requests)

YouTube rate-limits subtitle downloads. The script now handles this by:

1. Downloading each language individually (ko first, then en)
2. Retrying up to 2 times with exponential backoff (3s, 6s)
3. Continuing with partial results — if at least one language succeeds, the workflow proceeds

If all languages fail with 429, wait a few minutes and retry:

```bash
.venv/bin/python skills/youtube-visual-summary/scripts/fetch_youtube.py "URL" --run-root runs
```

The script is idempotent — it will detect the existing run directory and only retry missing captions.

## Download Failure

Try:

```bash
yt-dlp -F URL
```

For caption failures, retry `fetch_youtube.py` with narrower subtitle languages, such as `--sub-langs "en"`.

For frame-source failures, retry with a smaller video-only format:

```bash
.venv/bin/python skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR --format "worstvideo[ext=mp4]/worstvideo"
```

Private, region-limited, members-only, age-restricted, or bot-protected videos may not be supported.

## Slow Video Download

Do not use `bestvideo+bestaudio` for frame extraction. Images do not need audio, and merging separate audio/video streams is slow. Use:

```bash
.venv/bin/python skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR
```

This downloads only a video-only frame source as `_work/frame-source.*`.

The default format targets a balanced 720p-or-lower video-only stream so screenshots are readable without downloading full-quality video or audio.

## Contact Sheet Failure

Run `python3 skills/youtube-visual-summary/scripts/setup_venv.py` to install `Pillow` inside the project-root `.venv`. The rest of the pipeline can still inspect individual frame files, but contact sheets are strongly preferred.

## Weak Frame Candidates

Rerun extraction with denser sampling:

```bash
.venv/bin/python skills/youtube-visual-summary/scripts/extract_frames.py RUN_DIR --max-frames-per-chapter 16
.venv/bin/python skills/youtube-visual-summary/scripts/make_contact_sheets.py RUN_DIR
```
