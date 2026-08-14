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

`fetch_youtube.py` automatically adds `--remote-components ejs:github` (EJS challenge) and `--impersonate chrome` (429 relief) when a JS runtime and `curl_cffi` are present. Installing the runtime is the only manual step.

Note: `--remote-components` is still a current yt-dlp flag (not removed). The EJS challenge ("The page needs to be reloaded") is solved by the **`yt-dlp-ejs` plugin** — bundled via the `yt-dlp[default]` extra — executing JS in deno. yt-dlp alone cannot solve it.

## No Captions

자막(수동/자동 모두)이 하나도 없으면 STT 폴백으로 전사한다. Apple Silicon의 mlx-whisper를 쓴다(비 Apple Silicon에서는 불가 → 텍스트 전용).

**사전 확인:**

```bash
.venv/bin/python skills/youtube-visual-summary/scripts/env_check.py --json
```

`has_stt` 가 `true` 면 폴백 가능.

**폴백 절차:**

```bash
# 1. 오디오만 다운로드 (impersonation 필수 — 비디오와 같은 403/429 이유)
.venv/bin/yt-dlp -f "ba" -x --audio-format mp3 --no-playlist --impersonate chrome \
  -o RUN_DIR/_work/audio.%(ext)s "URL"

# 2. mlx-whisper 전사 (한국어 영상은 --language ko; 영어 등은 생략 시 자동 감지)
.venv/bin/python skills/youtube-visual-summary/scripts/stt_transcribe.py RUN_DIR/_work/audio.mp3 RUN_DIR "URL" --language ko
```

- 10분 청크 캐시(`_work/stt_chunks/`)로 재개 가능. 중단되면 같은 명령으로 이어서.
- 결과는 `build_transcript.py` 호환 `transcript.json` → 이후 chapters/프레임/render 파이프라인을 동일하게 재사용.
- 비 Apple Silicon이거나 사용자가 STT를 거부하면 텍스트 전용 모드로 진행.

## Caption Download 429 (Too Many Requests)

YouTube's bot detection returns 429 to non-browser clients. **Browser impersonation (`curl_cffi`) is the primary defense** — without it, caption (and often metadata) downloads fail repeatedly. Verify it is active:

```bash
.venv/bin/yt-dlp --list-impersonate-targets   # should list Chrome/Safari rows, not "(unavailable)"
```

If all targets show `unavailable`, curl_cffi is missing or the wrong version. yt-dlp pins `curl-cffi <0.16`, so installing 0.16+ by hand silently disables impersonation. Reinstall with the pinned extra:

```bash
python3 skills/youtube-visual-summary/scripts/setup_venv.py   # installs yt-dlp[default,curl-cffi]
```

On top of impersonation, the script mitigates 429 by:

1. Downloading each language individually (ko, then en)
2. Retrying up to 2 times with exponential backoff (3s, 6s)
3. Continuing with partial results — if at least one language succeeds, the workflow proceeds

If 429 still persists across all languages (e.g. you hit a translation-subtitle CDN that is rate-limiting hard), wait a few minutes and retry:

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
