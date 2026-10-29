#!/usr/bin/env python3
"""Cut one local clip per study scene: clips/{item}.mp4, clips/{item}--{sub}.mp4.

Local clips are the only reliable way to play a video segment from a file://
page — YouTube iframes there fail with player error 153 (no referrer). Clips
are re-encoded (frame-accurate cuts) and must carry audio, so every source run
needs a frame source fetched with ``fetch_frame_source.py --with-audio``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import HarnessError, find_frame_source, has_audio_stream, require_executable, run
from study_spec import iter_scenes, load_study, resolve_scene


def main() -> int:
    parser = argparse.ArgumentParser(description="Cut per-scene local clips for the study view.")
    parser.add_argument("run_dir")
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--force", action="store_true", help="re-cut clips that already exist")
    args = parser.parse_args()

    ffmpeg = require_executable("ffmpeg")
    run_dir = Path(args.run_dir).resolve()
    spec = load_study(run_dir)
    clips_dir = run_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    audio_sources: dict[str, Path] = {}

    def audio_source(src: dict) -> Path:
        key = str(src["key"])
        if key not in audio_sources:
            video = find_frame_source(src["run_dir"])
            if not has_audio_stream(video):
                raise HarnessError(
                    f"frame source has no audio: {video}\n"
                    f"re-fetch it: fetch_frame_source.py {src['run_dir']} --with-audio"
                )
            audio_sources[key] = video
        return audio_sources[key]

    done = skipped = 0
    for name, scene in iter_scenes(spec):
        out = clips_dir / f"{name}.mp4"
        if out.exists() and out.stat().st_size > 10_000 and not args.force:
            skipped += 1
            continue
        s = resolve_scene(spec, scene)
        run([
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-ss", f"{s['clip_start']:.2f}", "-i", str(audio_source(s["source"])), "-t", f"{s['clip_dur']:.2f}",
            "-vf", f"scale=-2:{args.height}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-y", str(out),
        ])
        done += 1
        print(f"[cut] {name} ({s['clip_dur']:.1f}s)")

    print(f"clips: {done} cut, {skipped} reused → {clips_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
