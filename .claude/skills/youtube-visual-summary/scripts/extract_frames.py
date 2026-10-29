#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

from common import HarnessError, existing_work_dir, find_frame_source, read_json, relpath, require_executable, run, write_json


def sample_times(start: float, end: float, max_frames: int, interval: float | None = None) -> list[float]:
    """Candidate timestamps for one chapter. By default the spacing grows with
    chapter length (duration/15). ``interval`` fixes the spacing instead — short
    chapters (10~40s, one term or one demo each) otherwise get only 3 frames."""
    if end <= start:
        return [start]
    duration = end - start
    per_chapter = duration / interval if interval else duration / 15
    count = min(max_frames, max(3, math.ceil(per_chapter) + 1))
    if count == 1:
        return [start + duration / 2]
    margin = min(2.0, duration * 0.08)
    usable_start = start + margin
    usable_end = end - margin
    if usable_end <= usable_start:
        usable_start, usable_end = start, end
    step = (usable_end - usable_start) / (count - 1)
    return [round(usable_start + step * i, 2) for i in range(count)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract candidate frames for each Codex chapter.")
    parser.add_argument("run_dir")
    parser.add_argument("--max-frames-per-chapter", type=int, default=None,
                        help="cap per chapter (default 8; 16 with --interval)")
    parser.add_argument("--interval", type=float, default=None,
                        help="fixed spacing in seconds, e.g. 2.5 for short per-term chapters")
    parser.add_argument("--width", type=int, default=1280)
    args = parser.parse_args()
    max_frames = args.max_frames_per_chapter or (16 if args.interval else 8)

    require_executable("ffmpeg")
    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    video = find_frame_source(run_dir)
    chapters_path = internal_dir / "chapters.codex.json"
    if not chapters_path.exists():
        raise HarnessError("missing chapters.codex.json; Codex must create it before frame extraction")

    chapters = read_json(chapters_path).get("chapters", [])
    manifest = {"frames": []}
    frames_root = internal_dir / "frames"
    for chapter in chapters:
        chapter_id = chapter["id"]
        chapter_dir = frames_root / chapter_id
        chapter_dir.mkdir(parents=True, exist_ok=True)
        for idx, ts in enumerate(sample_times(float(chapter["start"]), float(chapter["end"]), max_frames, args.interval), 1):
            frame_id = f"{chapter_id}-f{idx:03d}"
            out = chapter_dir / f"{frame_id}.jpg"
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{ts:.2f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                f"scale={args.width}:-1,format=yuvj420p",
                "-q:v",
                "2",
                "-y",
                str(out),
            ]
            run(cmd)
            manifest["frames"].append({
                "chapter_id": chapter_id,
                "frame_id": frame_id,
                "timestamp": ts,
                "image_path": relpath(out, internal_dir),
            })
    write_json(internal_dir / "frames" / "manifest.json", manifest)
    print((internal_dir / "frames" / "manifest.json").resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
