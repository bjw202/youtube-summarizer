#!/usr/bin/env python3
"""Download a video's audio as RUN_DIR/_work/audio.mp3 for speech recognition.

Uses the same yt-dlp setup as the video download (browser impersonation, and the
ffmpeg that common.find_tool picked — yt-dlp needs it to make the mp3), so it
works where ffmpeg exists only inside .venv. Skips the download if the file exists.

usage: fetch_audio.py RUN_DIR [URL]   (URL defaults to _work/input.json)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import build_yt_dlp_video_args, existing_work_dir, read_json, require_executable, run


def main() -> int:
    parser = argparse.ArgumentParser(description="Download audio (mp3) for stt_transcribe.py.")
    parser.add_argument("run_dir")
    parser.add_argument("url", nargs="?", default=None)
    args = parser.parse_args()

    internal = existing_work_dir(Path(args.run_dir))
    out = internal / "audio.mp3"
    if out.exists() and out.stat().st_size > 0:
        print(out.resolve())
        return 0
    url = args.url or read_json(internal / "input.json")["url"]
    yt_dlp = require_executable("yt-dlp")
    run([*build_yt_dlp_video_args(yt_dlp), "-f", "ba", "-x", "--audio-format", "mp3", "--no-playlist",
         "-o", str(internal / "audio.%(ext)s"), url])
    print(out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
