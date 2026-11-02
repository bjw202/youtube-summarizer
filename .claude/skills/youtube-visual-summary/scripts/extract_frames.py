#!/usr/bin/env python3
"""Extract candidate frames for each chapter in chapters.codex.json.

Two kinds of candidates per chapter, both recorded in frames/manifest.json with
their ``source``:

  interval  evenly spaced (``{chapter}-f001`` …) — the original behaviour, same
            ids and timestamps as before
  scene     moments where the picture changes (``{chapter}-s001`` …) — catches a
            slide that is on screen for only ~20 s between two interval frames.
            One low-resolution ffmpeg pass over the whole video, split into
            segments decoded in parallel (VP9 cannot skip non-key frames, so a
            single pass over a 1-hour 1080p video took 89 s). Duplicates are
            dropped (difference hash + colour thumbnail, see same_picture /
            same_shot), and each chapter keeps at most --max-scene-frames.
            --no-scenes turns this off.

            A change within MIN_GAP seconds of another candidate is no longer
            dropped for the time alone: an evenly spaced frame taken 1 s before a
            slide appears shows the speaker, not the slide (stroke lecture, 11:13
            pie chart). It is dropped only when its picture is the same *shot* as
            a candidate already kept (looser than same_picture, so a cut back to
            a camera angle the chapter already has does not add a candidate).

            A chapter owns the changes from CHAPTER_LEAD (2 s) before its start
            to CHAPTER_LEAD before its end, so a slide that appears a moment
            before the boundary is a candidate of the chapter it opens (stroke
            lecture: pie chart at 673.65 s, chapter 3 from 674.0 s).

            When the earliest candidate showing the same picture is an evenly
            spaced frame taken after the change (and before the next change),
            the change is where that picture began: the scene frame takes that
            frame's place (manifest ``scene_detection.replaced_interval``). The
            number of candidates stays the same, and a slide is found by scene
            detection, not by an evenly spaced frame happening to land on it.

            Every scene change that did not become a candidate is listed in
            manifest ``scene_detection.rejected`` with the reason, the candidate
            it duplicates and the distances (hash bits of 64, mean colour 0~255).

Add one frame by hand-picked time (replaces grabbing it with ffmpeg and editing
the manifest):

  extract_frames.py RUN_DIR --at 11:15 [--at 675.5 …] [--chapter chapter-03]
    → {chapter}-m001 …, source "manual"; the rest of the manifest is untouched.
      Without --chapter the chapter is found from the time.

A full re-run keeps earlier manual frames of chapters that still exist.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common import (CHILD_ENV, HarnessError, existing_work_dir, find_frame_source, format_ts, read_json,
                    relpath, require_executable, run, write_json)

SCENE_THRESHOLD = 0.3   # ffmpeg scene score (0~1) that counts as a picture change
SCENE_WIDTH = 160       # detection works on tiny frames
SCENE_FPS = 4           # …at a few frames per second
SCENE_SETTLE = 0.6      # grab slightly after the change so slide text has appeared
CHAPTER_LEAD = 2.0      # a change up to this many seconds before a chapter starts belongs to that chapter
SEGMENT_OVERLAP = 2.0   # seconds each parallel segment re-reads before its start
MIN_GAP = 3.0           # seconds: a scene change this close to another candidate must show a different shot
HASH_DISTANCE = 6       # of 64 bits: closer pictures count as the same picture…
COLOUR_DISTANCE = 12    # …if their 16x9 thumbnails also differ by at most this much per channel (0~255)
# Same shot (camera angle) — used only for changes within MIN_GAP of another candidate.
# Measured on the stroke lecture (63 min, 2 cameras + slides): a cut back to a camera
# angle the chapter already had scored ≤10 bits / ≤6.7 colour against that frame; the
# slides it must keep scored ≥19 bits / ≥33 colour against every candidate.
SHOT_HASH_DISTANCE = 12
SHOT_COLOUR_DISTANCE = 10


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


def video_duration(ffprobe: str, video: Path) -> float:
    out = run([ffprobe, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(video)]).stdout.strip()
    return float(out or 0)


def detect_segment(ffmpeg: str, video: Path, start: float, length: float, threshold: float) -> list[tuple[float, float]]:
    """(time, score) of picture changes inside one segment of the video."""
    vf = (f"fps={SCENE_FPS},scale={SCENE_WIDTH}:-2,select='gt(scene,{threshold})',"
          f"metadata=print:key=lavfi.scene_score")
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(video),
         "-an", "-sn", "-dn", "-vf", vf, "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=CHILD_ENV)
    if proc.returncode != 0:
        raise HarnessError(f"scene detection failed at {format_ts(start)}: {proc.stderr.strip()[-400:]}")
    hits, pending = [], None
    for line in proc.stderr.splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            pending = float(m.group(1))
            continue
        m = re.search(r"lavfi\.scene_score=([0-9.]+)", line)
        if m and pending is not None:
            hits.append((round(start + pending, 2), float(m.group(1))))
            pending = None
    return hits


def detect_scenes(ffmpeg: str, ffprobe: str, video: Path, threshold: float, jobs: int) -> tuple[list[tuple[float, float]], float]:
    """Picture changes over the whole video and the seconds it took."""
    began = time.monotonic()
    duration = video_duration(ffprobe, video)
    if duration <= 0:
        return [], 0.0
    parts = max(1, min(jobs, math.ceil(duration / 60)))
    size = duration / parts
    def segment(i: int) -> list[tuple[float, float]]:
        # start a little early: the first frame of a segment has nothing to compare
        # with, so a change right at the boundary would be missed; the overlap is
        # decoded twice and its hits are dropped from the later segment
        nominal = i * size
        begin = max(0.0, nominal - SEGMENT_OVERLAP)
        hits = detect_segment(ffmpeg, video, begin, size + (nominal - begin), threshold)
        return [h for h in hits if h[0] >= nominal]

    with ThreadPoolExecutor(max_workers=parts) as pool:
        hits = sorted(h for part in pool.map(segment, range(parts)) for h in part)
    return hits, round(time.monotonic() - began, 1)


def grab(ffmpeg: str, video: Path, ts: float, out: Path, width: int) -> None:
    run([ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{ts:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={width}:-1,format=yuvj420p", "-q:v", "2", "-y", str(out)])


def fingerprint(path: Path) -> tuple[int, list[int]]:
    """(64-bit difference hash, 16x9 colour thumbnail). The hash ignores colour —
    an all-red and an all-blue frame hash the same — so both must be close."""
    from PIL import Image

    with Image.open(path) as im:
        # tobytes(): one byte per channel, row by row — the same values getdata() gave,
        # without the getdata() deprecation (removed in Pillow 14)
        grey = list(im.convert("L").resize((9, 8)).tobytes())
        thumb = list(im.convert("RGB").resize((16, 9)).tobytes())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (grey[row * 9 + col] > grey[row * 9 + col + 1])
    return bits, thumb


def distance(a: tuple[int, list[int]], b: tuple[int, list[int]]) -> tuple[int, float]:
    """(differing hash bits of 64, mean colour difference per channel 0~255)."""
    return bin(a[0] ^ b[0]).count("1"), sum(abs(x - y) for x, y in zip(a[1], b[1])) / len(a[1])


def same_picture(a: tuple[int, list[int]], b: tuple[int, list[int]]) -> bool:
    bits, colour = distance(a, b)
    return bits <= HASH_DISTANCE and colour <= COLOUR_DISTANCE


def same_shot(a: tuple[int, list[int]], b: tuple[int, list[int]]) -> bool:
    bits, colour = distance(a, b)
    return bits <= SHOT_HASH_DISTANCE and colour <= SHOT_COLOUR_DISTANCE


def parse_time(value: str) -> float:
    """'675.5', '11:15' or '1:02:03'."""
    parts = [float(p) for p in value.strip().split(":")]
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def frame_entry(chapter_id: str, frame_id: str, ts: float, out: Path, internal_dir: Path, source: str, **extra) -> dict:
    entry = {"chapter_id": chapter_id, "frame_id": frame_id, "timestamp": ts,
             "image_path": relpath(out, internal_dir), "source": source}
    entry.update(extra)
    return entry


def add_manual(args, ffmpeg: str, video: Path, internal_dir: Path, chapters: list[dict]) -> int:
    manifest_path = internal_dir / "frames" / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {"frames": []}
    by_id = {c["id"]: c for c in chapters}
    for raw in args.at:
        ts = parse_time(raw)
        if args.chapter:
            chapter = by_id.get(args.chapter)
            if not chapter:
                raise HarnessError(f"unknown chapter: {args.chapter}")
        else:
            chapter = next((c for c in chapters if float(c["start"]) <= ts < float(c["end"])), None)
            if not chapter:
                raise HarnessError(f"{raw} is outside every chapter — pass --chapter")
        cid = chapter["id"]
        taken = {f["frame_id"] for f in manifest["frames"]}
        n = 1
        while f"{cid}-m{n:03d}" in taken:
            n += 1
        frame_id = f"{cid}-m{n:03d}"
        out = internal_dir / "frames" / cid / f"{frame_id}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        grab(ffmpeg, video, ts, out, args.width)
        manifest["frames"].append(frame_entry(cid, frame_id, round(ts, 2), out, internal_dir, "manual"))
        print(f"{frame_id}  {format_ts(ts)}  {relpath(out, internal_dir)}")
    manifest["frames"].sort(key=lambda f: (f["chapter_id"], f["timestamp"]))
    write_json(manifest_path, manifest)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract candidate frames for each chapter in chapters.codex.json.")
    parser.add_argument("run_dir")
    parser.add_argument("--max-frames-per-chapter", type=int, default=None,
                        help="cap of evenly spaced frames per chapter (default 8; 16 with --interval)")
    parser.add_argument("--interval", type=float, default=None,
                        help="fixed spacing in seconds, e.g. 2.5 for short per-term chapters")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--no-scenes", action="store_true", help="evenly spaced candidates only")
    parser.add_argument("--max-scene-frames", type=int, default=6, help="cap of scene-change frames per chapter")
    parser.add_argument("--scene-threshold", type=float, default=SCENE_THRESHOLD,
                        help=f"ffmpeg scene score that counts as a change (default {SCENE_THRESHOLD})")
    parser.add_argument("--jobs", type=int, default=max(2, min(8, (os.cpu_count() or 4) // 2)),
                        help="video segments decoded in parallel for scene detection")
    parser.add_argument("--at", action="append", default=[],
                        help="add one frame at this time (seconds or mm:ss) to the existing manifest; repeatable")
    parser.add_argument("--chapter", default=None, help="with --at: the chapter to file it under")
    args = parser.parse_args()
    max_frames = args.max_frames_per_chapter or (16 if args.interval else 8)

    ffmpeg = require_executable("ffmpeg")
    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    video = find_frame_source(run_dir)
    chapters_path = internal_dir / "chapters.codex.json"
    if not chapters_path.exists():
        raise HarnessError("missing _work/chapters.codex.json; write the chapters (SKILL.md Phase 4) before frame extraction. (The file name is historical and kept for compatibility with existing runs.)")
    chapters = read_json(chapters_path).get("chapters", [])

    if args.at:
        return add_manual(args, ffmpeg, video, internal_dir, chapters)

    manifest_path = internal_dir / "frames" / "manifest.json"
    old = read_json(manifest_path) if manifest_path.exists() else {"frames": []}
    chapter_ids = {c["id"] for c in chapters}
    kept_manual = [f for f in old.get("frames", []) if f.get("source") == "manual" and f["chapter_id"] in chapter_ids]

    scenes: list[tuple[float, float]] = []
    scene_info: dict = {"enabled": not args.no_scenes}
    if not args.no_scenes:
        scenes, seconds = detect_scenes(ffmpeg, require_executable("ffprobe"), video, args.scene_threshold, args.jobs)
        scene_info.update({"seconds": seconds, "threshold": args.scene_threshold, "detected": len(scenes),
                           "jobs": args.jobs})
        print(f"[scenes] {len(scenes)} picture changes found in {seconds}s ({args.jobs} parallel segments)")

    manifest: dict = {"frames": [], "scene_detection": scene_info}
    frames_root = internal_dir / "frames"
    kept_scene = 0
    rejected: list[dict] = []
    replaced: list[dict] = []
    change_times = sorted(t for t, _ in scenes)

    def same_stretch(change: float, frame_time: float) -> bool:
        """The frame was taken after this change and before the next one."""
        nxt = next((c for c in change_times if c > change), math.inf)
        return change < frame_time < nxt

    placed = set()   # scene changes already given to a chapter
    for position, chapter in enumerate(chapters):
        chapter_id = chapter["id"]
        start, end = float(chapter["start"]), float(chapter["end"])
        chapter_dir = frames_root / chapter_id
        chapter_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        known: list[tuple[str, float, tuple[int, list[int]]]] = []   # (frame_id, time, fingerprint) of candidates
        for idx, ts in enumerate(sample_times(start, end, max_frames, args.interval), 1):
            frame_id = f"{chapter_id}-f{idx:03d}"
            out = chapter_dir / f"{frame_id}.jpg"
            grab(ffmpeg, video, ts, out, args.width)
            entries.append(frame_entry(chapter_id, frame_id, ts, out, internal_dir, "interval"))
            if scenes:
                known.append((frame_id, ts, fingerprint(out)))
        manual_here = [m for m in kept_manual if m["chapter_id"] == chapter_id]
        for old_stale in chapter_dir.glob(f"{chapter_id}-s*.jpg"):
            old_stale.unlink()   # scene ids are renumbered every run
        if scenes:
            for m in manual_here:
                path = internal_dir / m["image_path"]
                if path.is_file():
                    known.append((m["frame_id"], float(m["timestamp"]), fingerprint(path)))
            # A chapter owns the changes from CHAPTER_LEAD s before its start to CHAPTER_LEAD s
            # before its end: a slide that appears just before the boundary belongs to the
            # chapter it opens (stroke lecture: the pie chart cut at 673.65 s, chapter 3 at 674.0 s)
            own_from = start - CHAPTER_LEAD if position > 0 else start
            own_to = end - CHAPTER_LEAD if position < len(chapters) - 1 else end
            in_chapter = [(t, s) for t, s in scenes if own_from <= t < own_to and t not in placed]
            placed.update(t for t, _ in in_chapter)
            inside = []
            for t, score in in_chapter:
                if position == len(chapters) - 1 and t >= end - 1.0:
                    rejected.append({"time": t, "score": round(score, 3), "chapter_id": chapter_id,
                                     "reason": "chapter_edge"})   # the cut to the end screen
                else:
                    inside.append((t, score))
            n = 0
            probe = chapter_dir / f"{chapter_id}-probe.jpg"
            interval_ids = {e["frame_id"] for e in entries if e["source"] == "interval"}
            for t, score in sorted(inside, key=lambda h: -h[1]):   # strongest changes first
                base = {"time": t, "score": round(score, 3), "chapter_id": chapter_id}
                if n >= args.max_scene_frames:
                    rejected.append({**base, "reason": "chapter_cap", "cap": args.max_scene_frames})
                    continue
                ts = round(min(max(t + SCENE_SETTLE, start + 0.3), end - 0.5), 2)
                grab(ffmpeg, video, ts, probe, args.width)
                h = fingerprint(probe)
                dists = sorted(((fid, ft, *distance(h, fp)) for fid, ft, fp in known), key=lambda d: d[1])  # earliest first
                dup = next((d for d in dists if d[2] <= HASH_DISTANCE and d[3] <= COLOUR_DISTANCE), None)
                near = [d for d in dists if abs(ts - d[1]) < MIN_GAP]
                shot = (next((d for d in dists if d[2] <= SHOT_HASH_DISTANCE and d[3] <= SHOT_COLOUR_DISTANCE), None)
                        if near else None)
                why = ("same_picture", dup) if dup else ("near_time_same_shot", shot) if shot else None
                if why and why[1][0] in interval_ids and same_stretch(t, why[1][1]):
                    # an evenly spaced frame shows the picture this change brought in: the change
                    # is where that picture began, so it takes the evenly spaced frame's place
                    # (one candidate either way — no extra camera angles)
                    gone = why[1][0]
                    entries = [e for e in entries if e["frame_id"] != gone]
                    known = [k for k in known if k[0] != gone]
                    interval_ids.discard(gone)
                    (chapter_dir / f"{gone}.jpg").unlink(missing_ok=True)
                    replaced.append({"interval": gone, "by": f"{chapter_id}-s{n + 1:03d}", "time": t,
                                     "hash_distance": why[1][2], "colour_distance": round(why[1][3], 1)})
                    why = None
                if why:
                    reason, (fid, ft, bits, colour) = why
                    rejected.append({**base, "timestamp": ts, "reason": reason, "duplicate_of": fid,
                                     "hash_distance": bits, "colour_distance": round(colour, 1),
                                     **({"gap": round(abs(ts - near[0][1]), 2), "near": near[0][0]} if near else {})})
                    continue
                frame_id = f"{chapter_id}-s{n + 1:03d}"
                out = chapter_dir / f"{frame_id}.jpg"
                probe.replace(out)
                known.append((frame_id, ts, h))
                entries.append(frame_entry(chapter_id, frame_id, ts, out, internal_dir, "scene",
                                           scene_score=round(score, 3)))
                n += 1
            probe.unlink(missing_ok=True)
            kept_scene += n
        entries += manual_here
        manifest["frames"] += sorted(entries, key=lambda e: e["timestamp"])
    if scenes:
        rejected += [{"time": t, "score": round(s, 3), "reason": "outside_chapters"} for t, s in scenes if t not in placed]
        scene_info["kept"] = kept_scene
        scene_info["rejected"] = sorted(rejected, key=lambda r: r["time"])
        scene_info["replaced_interval"] = replaced
        reasons: dict[str, int] = {}
        for r in rejected:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        print(f"[scenes] {kept_scene} scene candidates kept ({len(replaced)} in place of an evenly spaced frame "
              f"showing the same picture); not kept: "
              + (", ".join(f"{k} {v}" for k, v in sorted(reasons.items())) or "none")
              + " (manifest scene_detection.rejected)")
    write_json(manifest_path, manifest)
    print(manifest_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
