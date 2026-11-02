# Troubleshooting

## Missing `yt-dlp`

First run:

```bash
uv run .claude/skills/youtube-visual-summary/scripts/install.py
```

Then rerun:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/doctor.py --json
```

Explain that `yt-dlp` is required to read metadata and captions from YouTube and should live inside the project-root `.venv`, not the user's system Python.

## Missing `ffmpeg`

`ffmpeg` extracts candidate frames and cuts study-view clips. The system copy is used when there is one; otherwise `install.py` installs `static-ffmpeg` into `.venv`, which downloads ffmpeg/ffprobe for this OS once (no admin rights). If `doctor.py --json` still shows `checks.ffmpeg.ok: false`, the download failed — check the network and run `install.py` again.

## Missing JS Runtime (deno or node)

yt-dlp requires a JavaScript runtime to solve YouTube's EJS challenges. Without it, some formats may be missing and caption downloads may fail with cryptic errors.

**Check:**

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/doctor.py --json
```

If `checks.js_runtime.ok` is `false`, run `install.py` — it installs the PyPI `deno` package into `.venv` (macOS, Linux, Windows x64). Windows ARM has no deno build: install Node.js LTS for the user as `checks.js_runtime.hint` says (no admin rights).

A system deno or node is used first when there is one. `fetch_youtube.py` passes the chosen runtime to yt-dlp as `--js-runtimes deno:<path>` (or `node:<path>`) and adds `--remote-components ejs:github` (EJS challenge) and `--impersonate chrome` (fewer 429s) when a JS runtime and `curl_cffi` are present.

Note: `--remote-components` is still a current yt-dlp flag (not removed). The EJS challenge ("The page needs to be reloaded") is solved by the **`yt-dlp-ejs` plugin** — bundled via the `yt-dlp[default]` extra — executing JS in deno. yt-dlp alone cannot solve it.

## No Captions

자막(수동/자동 모두)이 하나도 없으면 STT 폴백으로 전사한다. Apple Silicon 맥은 mlx-whisper, 그 밖은 faster-whisper(turbo, int8, beam 1)를 자동으로 고른다(`--engine`으로 고정 가능). STT를 쓸 수 없으면 이유를 알리고 멈춘다 — 텍스트 전용 모드도 전사가 있어야 만들 수 있다.

**사전 확인:**

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/doctor.py --json
```

`features.stt.ok`가 `true`면 폴백 가능. `false`면 사용자에게 먼저 묻고(모델 약 1.5GB) 동의하면 `uv run .claude/skills/youtube-visual-summary/scripts/install.py --with-stt`.

**폴백 절차:**

```bash
# 1. 오디오만 다운로드 → RUN_DIR/_work/audio.mp3 (impersonation과 ffmpeg 위치를 스크립트가 넘긴다)
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_audio.py RUN_DIR

# 2. 전사 (한국어 영상은 --language ko; 영어 등은 생략 시 자동 감지)
uv run python .claude/skills/youtube-visual-summary/scripts/stt_transcribe.py RUN_DIR/_work/audio.mp3 RUN_DIR "URL" --language ko
```

- 10분 청크 캐시(mlx는 `_work/stt_chunks/`, faster-whisper는 `_work/stt_chunks_faster_whisper/`)로 재개 가능. 중단되면 같은 명령으로 이어서.
- faster-whisper 1.2.1은 PyAV 19와 함께 쓰면 파일 경로 입력에서 TypeError를 낸다. 그래서 스크립트가 ffmpeg로 16kHz mono float 배열을 만들어 넘긴다.
- 결과는 `build_transcript.py` 호환 `transcript.json` → 이후 chapters/프레임/render 파이프라인을 동일하게 재사용.
- **자막도 음성 인식도 쓸 수 없으면 여기서 멈춘다.** 텍스트 전용 모드는 영상 화면(프레임)만 빼는 모드이지 전사(`transcript.json`)가 없어도 되는 모드가 아니다 — 챕터 나누기와 요약이 전사를 읽기 때문이다. 사용자에게 이유(이 영상에 자막이 없고, 이 컴퓨터에서 음성 인식을 쓸 수 없거나 사용자가 원하지 않음)를 알리고, 할 수 있는 길(음성 인식을 설치한 뒤 다시 실행, 자막이 있는 다른 영상)을 제시한 뒤 끝낸다.

## Caption Download 429 (Too Many Requests)

YouTube's bot detection returns 429 to non-browser clients. **Browser impersonation (`curl_cffi`) is the primary defense** — without it, caption (and often metadata) downloads fail repeatedly. Verify it is active:

```bash
uv run yt-dlp --list-impersonate-targets   # should list Chrome/Safari rows, not "(unavailable)"
```

If all targets show `unavailable`, curl_cffi is missing or outside the version range yt-dlp accepts (yt-dlp pins it; installing another version by hand silently disables impersonation). `doctor.py` checks exactly this (`checks.impersonation`). Reinstall with the pinned extra:

```bash
uv run .claude/skills/youtube-visual-summary/scripts/install.py   # installs yt-dlp[default,curl-cffi]
```

On top of impersonation, the script mitigates 429 by:

1. Downloading each language individually (ko, then en)
2. Retrying up to 2 times with exponential backoff (3s, 6s)
3. Continuing with partial results — if at least one language succeeds, the workflow proceeds

If 429 still persists across all languages (e.g. you hit a translation-subtitle CDN that is rate-limiting hard), wait a few minutes and retry:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_youtube.py "URL" --run-root runs
```

The script is idempotent — it will detect the existing run directory and only retry missing captions.

## Download Failure

Try:

```bash
yt-dlp -F URL
```

For frame-source 403 / "Video unavailable", see the next section.

For caption failures, retry `fetch_youtube.py` with narrower subtitle languages, such as `--sub-langs "en"`.

For frame-source failures, retry with a smaller video-only format:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR --format "worstvideo[ext=mp4]/worstvideo"
```

Private, region-limited, members-only, age-restricted, or bot-protected videos may not be supported.

## Video Download 403 / "Video unavailable" (frame source)

증상: 자막·메타데이터는 받아지는데 `fetch_frame_source.py`만 실패한다. `yt-dlp -F URL`은 포맷 목록을 정상 출력한다(= 영상은 공개 상태, 문제는 접속 방식).

- `HTTP Error 403: Forbidden` — yt-dlp가 고른 player client의 스트림 URL을 YouTube가 거절한다.
- `Video unavailable` / `Requested format is not available` — 고정한 client(`web_embedded` 등)가 그 영상의 포맷을 주지 않는다.

원인: **어떤 player client가 통하는지는 몇 주 단위로 바뀐다.** 2026-08-14에는 기본값(`android_vr`)이 403이고 `web_embedded,web_safari`가 통했지만, 2026-09-21에는 그 고정값이 "Video unavailable"을 냈고 yt-dlp 2026.8.19의 새 기본값(`visionos`)이 통했다(yt-dlp 2026.07.04의 기본값은 여전히 403).

조치 순서:

1. **yt-dlp를 올린다.** `uv run .claude/skills/youtube-visual-summary/scripts/install.py` (`install.py`는 돌 때마다 yt-dlp·yt-dlp-ejs를 최신으로 올린다. 평소에는 `doctor.py`가 30일 넘은 yt-dlp를 `ok: false`로 알려 Phase 2에서 돌게 된다). 대부분 여기서 끝난다.
2. 스크립트는 client를 고정하지 않고 `common.VIDEO_CLIENT_FALLBACKS` 순서(기본값 → `mweb` → `web_embedded,web_safari`)로 자동 재시도하며, 성공한 client를 `_work/frame-source.json`의 `player_client`에 남긴다. `mweb`은 PO 토큰 없이 360p 통합 포맷(18)만 주지만 프레임 추출에는 쓸 수 있다.
3. 전부 실패하면 client별로 직접 확인한다: `uv run yt-dlp -f 160 --impersonate chrome --extractor-args "youtube:player_client=<client>" URL` (`tv`, `ios`, `web` 등). 통하는 client를 `VIDEO_CLIENT_FALLBACKS`에 추가한다.
4. 비디오 다운로드에는 `--remote-components`를 넣지 않는다(SABR 스트리밍 없이 받을 수 있는 client가 후보에서 빠진다).

텍스트 전용으로 먼저 마무리한 run은 나중에 Phase 5부터 이어서 돌리면 된다(`chapters.codex.json`의 `visual_query`가 남아 있다).

## 학습 보기: 유튜브 플레이어 오류 153 (로컬 HTML)

증상: `file://`로 연 HTML의 유튜브 iframe이 "동영상 플레이어 구성 오류" / "오류 153"을 낸다. `www.youtube.com`, `youtube-nocookie.com` 둘 다 같다.

원인: 2025-11부터 유튜브가 임베드 요청의 referrer를 검사한다. 로컬 파일에는 보낼 출처가 없어서 `<meta name="referrer">`나 `referrerpolicy`로도 고칠 수 없다(UMich TeamDynamix KB "Fixing YouTube Player Error 153", WordPress/gutenberg#73288 등 같은 보고).

조치: 임베드를 쓰지 않는다. `cut_clips.py`로 구간 클립을 만들고 `<video>`로 재생한다(`render_study.py`가 이렇게 렌더한다). 원본으로 가는 길은 `t=` 딥링크로 남긴다. 웹 서버(http/https)에 올린 페이지는 임베드가 될 수 있지만, 이 하네스의 산출물은 로컬 파일이 기본이다.

## 학습 보기: 클립에 소리가 없음

증상: `cut_clips.py`가 `frame source has no audio`로 멈추거나, `check_study.py`가 `clip has no audio`를 낸다.

원인: 기본 `fetch_frame_source.py`는 영상 스트림만(`bv*`) 받는다. 첫 용어집 run에서는 무음 소스와 소리 있는 소스를 따로 받다가 무음 쪽에서 클립을 잘라 다시 작업했다.

조치: `fetch_frame_source.py RUN_DIR --with-audio`로 다시 받는다(무음 파일을 지우고 소리 포함 1080p를 받는다). 같은 영상이라 프레임은 다시 뽑지 않아도 된다. 그다음 `cut_clips.py RUN_DIR --force`로 클립을 새로 자른다.

## Slow Video Download

Do not use `bestvideo+bestaudio` for frame extraction. Images do not need audio, and merging separate audio/video streams is slow. Use:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR
```

This downloads only a video-only frame source as `_work/frame-source.*`.

The default format targets a balanced 720p-or-lower video-only stream so screenshots are readable without downloading full-quality video or audio.

## Contact Sheet Failure

Run `uv run .claude/skills/youtube-visual-summary/scripts/install.py` to install `Pillow` inside the project-root `.venv`. The rest of the pipeline can still inspect individual frame files, but contact sheets are strongly preferred.

## Weak Frame Candidates

Rerun extraction with denser sampling:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/extract_frames.py RUN_DIR --max-frames-per-chapter 16
uv run python .claude/skills/youtube-visual-summary/scripts/make_contact_sheets.py RUN_DIR
```

## 원본 영상이 없다 (`missing frame source video`)

전달을 마친 run은 Phase 9의 `clean_run.py`가 `_work/`의 원본 영상을 지운다(`_work/frame-source.json`에 `source_removed`가 적혀 있다). 장면을 다시 고르거나, 장면을 더 뽑거나(`extract_frames.py --at`), 학습 보기를 나중에 추가하려면 다시 받는다:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR [--with-audio]
```

## 슬라이드가 후보에 없다

`extract_frames.py`는 일정 간격 후보에 더해 화면이 바뀌는 시점도 후보로 뽑는다(`--no-scenes`로 끔). 그래도 빠졌으면 자막에서 그 시각을 찾아 한 장 추가한다: `extract_frames.py RUN_DIR --at 11:15 [--chapter chapter-03]` → `make_contact_sheets.py RUN_DIR`. 화면 전환이 약한 장면(작은 그림이 화면 구석에 겹쳐 나오는 경우)은 검출 점수가 낮아 빠질 수 있다.
