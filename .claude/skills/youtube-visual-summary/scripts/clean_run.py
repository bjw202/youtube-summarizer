#!/usr/bin/env python3
"""Free disk space after delivery: delete the source video in RUN_DIR/_work.

A one-hour 1080p source is ~1.3 GB of a ~1.5 GB run, and nothing in the finished
pages needs it. It is deleted only when the run is complete:

  1. check_summary.py passes (no FAIL; a missing key_point does not block — adding one
     later never needs the video)
  2. if study.html exists, check_study.py passes
  3. every selected frame is in images/ (render_html.py copied it)
  4. if study.html exists, every scene clip is in clips/

Deleted: video files directly in _work/ (frame-source.*, video-preview.*, other
*.mp4/*.webm/*.mkv) and leftover partial downloads (*.part, *.ytdl). Kept:
frames, contact sheets, transcript, audio.mp3, all JSON. frame-source.json is
marked so later steps know why the video is gone.

To pick frames again or add a study view later, download it again:
  uv run python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR [--with-audio]

Everything it prints — refusals and dry runs included — is also appended to
RUN_DIR/_work/clean_run.log with the time, so the run keeps its before/after size.

usage: clean_run.py RUN_DIR [--dry-run]
exit 0 = deleted (or would delete with --dry-run, or nothing to delete), 1 = run not complete
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import (CHILD_ENV, VIDEO_SUFFIXES, existing_work_dir, group_selections, read_json,
                    selection_image_name, write_json)

SCRIPTS = Path(__file__).resolve().parent
PARTIAL_SUFFIXES = {".part", ".ytdl"}


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def run_check(script: str, run_dir: Path, *extra: str) -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), str(run_dir), *extra], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=CHILD_ENV)
    last = (proc.stdout.strip() or proc.stderr.strip()).splitlines()
    return proc.returncode == 0, (last[0] if last else "")


def video_files(internal: Path) -> list[Path]:
    out = []
    for p in sorted(internal.iterdir()):
        if not p.is_file():
            continue
        suffixes = {s.lower() for s in p.suffixes}
        if p.suffix.lower() in VIDEO_SUFFIXES or suffixes & PARTIAL_SUFFIXES:
            out.append(p)
    return out


def problems_before_cleaning(run_dir: Path, internal: Path) -> list[str]:
    problems = []
    ok, line = run_check("check_summary.py", run_dir, "--allow-missing-key-point")
    if not ok:
        problems.append(f"check_summary.py does not pass: {line}")

    selected = internal / "selected-frames.json"
    if selected.exists():
        for chapter_id, items in group_selections(read_json(selected)).items():
            for n, sel in enumerate(items):
                name = selection_image_name(chapter_id, n, Path(sel["image_path"]).suffix)
                if not (run_dir / "images" / name).is_file():
                    problems.append(f"selected frame not in images/: {name} (run render_html.py)")

    if (run_dir / "study.html").exists():
        ok, line = run_check("check_study.py", run_dir)
        if not ok:
            problems.append(f"check_study.py does not pass: {line}")
        from study_spec import iter_scenes, load_study
        for name, _ in iter_scenes(load_study(run_dir)):
            if not (run_dir / "clips" / f"{name}.mp4").is_file():
                problems.append(f"clip not in clips/: {name}.mp4 (run cut_clips.py)")
    return problems


LOG_NAME = "clean_run.log"
SAID: list[str] = []


def say(line: str) -> None:
    """Print, and keep the line for _work/clean_run.log."""
    SAID.append(line)
    print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete the source video of a finished run.")
    parser.add_argument("run_dir")
    parser.add_argument("--dry-run", action="store_true", help="only report what would be deleted")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    internal = existing_work_dir(run_dir)
    try:
        return clean(args, run_dir, internal)
    finally:
        stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")
        with (internal / LOG_NAME).open("a", encoding="utf-8") as log:
            log.write(f"== {stamp} clean_run.py{' --dry-run' if args.dry_run else ''}\n")
            log.writelines(line + "\n" for line in SAID)


def clean(args: argparse.Namespace, run_dir: Path, internal: Path) -> int:
    targets = video_files(internal)
    before = size_of(run_dir)
    if not targets:
        say(f"nothing to delete — no source video in {internal.name}/ (run folder {human(before)})")
        return 0

    problems = problems_before_cleaning(run_dir, internal)
    if problems:
        say("NOT deleted — the run is not complete yet:")
        for p in problems:
            say(f"  - {p}")
        return 1

    freed = sum(p.stat().st_size for p in targets)
    for p in targets:
        say(f"{'would delete' if args.dry_run else 'delete'}  {p.relative_to(run_dir).as_posix()}  {human(p.stat().st_size)}")
    if args.dry_run:
        say(f"run folder {human(before)} → {human(before - freed)} after cleaning (dry run, nothing deleted)")
        return 0

    for p in targets:
        p.unlink()
    marker = internal / "frame-source.json"
    if marker.exists():
        info = read_json(marker)
        info["source_removed"] = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
        info["source_removed_note"] = ("deleted by clean_run.py after delivery — re-download with "
                                       "fetch_frame_source.py RUN_DIR [--with-audio] to pick frames or cut clips again")
        write_json(marker, info)
    after = size_of(run_dir)
    say(f"run folder {human(before)} → {human(after)} (freed {human(before - after)})")
    say("To pick frames again or add a study view later: "
          "uv run python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR [--with-audio]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
