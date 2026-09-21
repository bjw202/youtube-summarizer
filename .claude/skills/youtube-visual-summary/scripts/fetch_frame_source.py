#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import VIDEO_CLIENT_FALLBACKS, HarnessError, build_yt_dlp_video_args, existing_work_dir, read_json, require_executable, run, write_json


DEFAULT_FORMAT = "bv*[height<=720][ext=mp4]/bv*[height<=720]/bv*[height<=480][ext=mp4]/bv*[height<=480]/worstvideo"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a low-resolution video-only frame source.")
    parser.add_argument("run_dir")
    parser.add_argument("--format", default=DEFAULT_FORMAT)
    args = parser.parse_args()

    yt_dlp = require_executable("yt-dlp")
    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    input_path = internal_dir / "input.json"
    if not input_path.exists():
        raise HarnessError(f"missing input.json: {input_path}")
    url = read_json(input_path)["url"]

    for old_part in internal_dir.glob("frame-source.*.part"):
        old_part.unlink()

    # Video data uses impersonation only (no --remote-components), and the
    # player client is not pinned: try yt-dlp's default first, then the
    # fallbacks. See common.build_yt_dlp_video_args for why.
    errors: list[str] = []
    used_client = None
    for client in VIDEO_CLIENT_FALLBACKS:
        cmd = [
            *build_yt_dlp_video_args(yt_dlp, client),
            "-f",
            args.format,
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
            + "\nUpgrade yt-dlp first (re-run setup_venv.py), then see references/troubleshooting.md."
        )

    sources = sorted(
        p for p in internal_dir.glob("frame-source.*")
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in {".mp4", ".webm", ".mkv"}
    )
    if not sources:
        raise HarnessError("frame source video was not downloaded")

    write_json(
        internal_dir / "frame-source.json",
        {
            "source_path": sources[0].name,
            "format": args.format,
            "player_client": used_client,
            "purpose": "video-only low-resolution source for frame extraction",
        },
    )
    print(sources[0].resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
