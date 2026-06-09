#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

from common import HarnessError, existing_work_dir, read_json, relpath, require_executable, run, write_json


def sample_times(start: float, end: float, max_frames: int) -> list[float]:
    if end <= start:
        return [start]
    duration = end - start
    count = min(max_frames, max(3, math.ceil(duration / 15) + 1))
    if count == 1:
        return [start + duration / 2]
    margin = min(2.0, duration * 0.08)
    usable_start = start + margin
    usable_end = end - margin
    if usable_end <= usable_start:
        usable_start, usable_end = start, end
    step = (usable_end - usable_start) / (count - 1)
    return [round(usable_start + step * i, 2) for i in range(count)]


def find_frame_source(run_dir: Path) -> Path:
    internal_dir = existing_work_dir(run_dir)
    candidates = [
        p for p in sorted(internal_dir.glob("frame-source.*"))
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in {".mp4", ".webm", ".mkv"}
    ]
    candidates.extend(
        p for p in sorted(internal_dir.glob("video-preview.*"))
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in {".mp4", ".webm", ".mkv"}
    )
    if not candidates:
        raise HarnessError("missing frame source video; run fetch_frame_source.py RUN_DIR first")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract candidate frames for each Codex chapter.")
    parser.add_argument("run_dir")
    parser.add_argument("--max-frames-per-chapter", type=int, default=8)
    parser.add_argument("--width", type=int, default=1280)
    args = parser.parse_args()

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
        for idx, ts in enumerate(sample_times(float(chapter["start"]), float(chapter["end"]), args.max_frames_per_chapter), 1):
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
                f"scale={args.width}:-1",
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
