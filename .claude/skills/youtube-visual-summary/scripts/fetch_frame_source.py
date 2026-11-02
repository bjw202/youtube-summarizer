#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from timing import mark as timing_mark
from common import (
    VIDEO_CLIENT_FALLBACKS, VIDEO_SUFFIXES, HarnessError, build_yt_dlp_video_args, existing_work_dir,
    has_audio_stream, read_json, require_executable, run, write_json,
)


DEFAULT_FORMAT = "bv*[height<=720][ext=mp4]/bv*[height<=720]/bv*[height<=480][ext=mp4]/bv*[height<=480]/worstvideo"
# Study view: one 1080p file with sound serves both frame extraction and clip
# cutting. A separate silent frame source + audio source pair invited cutting
# clips from the silent one (happened on the first glossary run).
WITH_AUDIO_FORMAT = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a low-resolution video-only frame source.")
    parser.add_argument("run_dir")
    parser.add_argument("--format", default=None)
    parser.add_argument("--with-audio", action="store_true",
                        help="1080p video+audio in one mp4 (needed for study-view clips)")
    args = parser.parse_args()
    fmt = args.format or (WITH_AUDIO_FORMAT if args.with_audio else DEFAULT_FORMAT)

    yt_dlp = require_executable("yt-dlp")
    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    input_path = internal_dir / "input.json"
    if not input_path.exists():
        raise HarnessError(f"missing input.json: {input_path}")
    url = read_json(input_path)["url"]

    # _work/timing.log: the download runs in the background during Phase 4, so it marks
    # itself ("download start" / "download end", or "download failed")
    timing_mark(run_dir, "download", "start")
    try:
        return download(args, fmt, yt_dlp, internal_dir, url, run_dir)
    except BaseException:
        timing_mark(run_dir, "download", "failed")
        raise


def download(args: argparse.Namespace, fmt: str, yt_dlp: str, internal_dir: Path, url: str, run_dir: Path) -> int:
    for old_part in internal_dir.glob("frame-source.*.part"):
        old_part.unlink()
    if args.with_audio:
        # yt-dlp skips a file that already exists, so a silent source from an
        # earlier plain run would survive. Drop it so the audio version lands.
        for old in internal_dir.glob("frame-source.*"):
            if old.suffix.lower() in VIDEO_SUFFIXES and not has_audio_stream(old):
                old.unlink()

    # Video data uses impersonation only (no --remote-components), and the
    # player client is not pinned: try yt-dlp's default first, then the
    # fallbacks. See common.build_yt_dlp_video_args for why.
    errors: list[str] = []
    used_client = None
    for client in VIDEO_CLIENT_FALLBACKS:
        cmd = [
            *build_yt_dlp_video_args(yt_dlp, client),
            "-f",
            fmt,
            *(["--merge-output-format", "mp4"] if args.with_audio else []),
            "--no-playlist",
            "-o",
            str(internal_dir / "frame-source.%(ext)s"),
            url,
        ]
        try:
            run(cmd)
            used_client = client or "default"
            break
        except HarnessError as exc:
            last_line = str(exc).strip().splitlines()[-1]
            errors.append(f"[{client or 'default'}] {last_line}")
            for leftover in internal_dir.glob("frame-source.*"):
                if leftover.name != "frame-source.json":
                    leftover.unlink()
    else:
        raise HarnessError(
            "frame source download failed on every player client:\n  "
            + "\n  ".join(errors)
            + "\nUpgrade yt-dlp first (re-run: uv run .claude/skills/youtube-visual-summary/scripts/install.py), then see references/troubleshooting.md."
        )

    sources = sorted(
        p for p in internal_dir.glob("frame-source.*")
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in VIDEO_SUFFIXES
    )
    if not sources:
        raise HarnessError("frame source video was not downloaded")

    has_audio = has_audio_stream(sources[0])
    if args.with_audio and not has_audio:
        raise HarnessError(f"--with-audio download has no audio stream: {sources[0]}")
    write_json(
        internal_dir / "frame-source.json",
        {
            "source_path": sources[0].name,
            "format": fmt,
            "player_client": used_client,
            "has_audio": has_audio,
            "purpose": "frame extraction + study-view clips" if has_audio
            else "video-only low-resolution source for frame extraction",
        },
    )
    print(sources[0].resolve())
    timing_mark(run_dir, "download", "end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
