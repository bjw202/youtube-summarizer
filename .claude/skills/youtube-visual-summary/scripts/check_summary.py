#!/usr/bin/env python3
"""Check a run's chapters and summary before rendering or delivering it.

FAIL (exit 1) — structure is wrong:
  * a chapter starts or ends outside the video (0 … duration), or ends before it starts
  * two chapters overlap, or a gap between neighbours is longer than --max-gap seconds
  * a chapter has no selected image (skipped for text-only runs: no selected-frames.json)
  * a selected image file is missing
  * a chapter has no ``key_point`` (the one-line takeaway: the summary's 핵심 callout and
    the study view's lead sentence). With --allow-missing-key-point this is a WARN —
    for runs written before 2026-11-02, when the field was not yet in SKILL.md, and
    for clean_run.py (adding a key point never needs the source video)
WARN (exit 0, or 1 with --strict) — worth a second look:
  * the video's start or end is not covered by any chapter (intro/outro left out)
  * a number in the summary text does not appear in the transcript
    (numbers of two or more digits and decimals; the transcript may spell it in words;
    "17장"/"챕터 17" pointing at one of this summary's chapters is not a number).
    Numbers listed in the chapter's ``verified_numbers`` — read off a slide, chart or
    other screen text and checked on the frame — are not warned about
  * chapters that do not follow _work/chapter-plan.json (plan_chapters.py): a different
    number of chapters, or a start/end more than 1 s from the plan

usage: check_summary.py RUN_DIR [--max-gap 2] [--strict] [--json] [--allow-missing-key-point]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from common import existing_work_dir, first_existing, format_ts, read_json

NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
CODE_RE = re.compile(r"`[^`]*`")
# references to the summary's own chapters ("17장에서 다시 본다", "챕터 14"): not data
CHAPTER_REF_RE = re.compile(r"(?<![\w.])(\d{1,3})\s?장|(?:챕터|[Cc]hapter)\s?(\d{1,3})(?!\d)")
TEXT_FIELDS = ("title", "summary_bullets", "summary_paragraphs", "key_point")


def chapter_text(ch: dict) -> str:
    parts: list[str] = []
    for field in TEXT_FIELDS:
        value = ch.get(field)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
    return "\n".join(parts)


def verified_numbers(ch: dict) -> set[str]:
    """``verified_numbers``: numbers checked on screen (a chart, a slide), not spoken.
    Items are strings ("54") or {"value": "54", "seen": "56:08 원그래프"}."""
    out = set()
    for item in ch.get("verified_numbers") or []:
        value = item.get("value") if isinstance(item, dict) else item
        if value is not None:
            out.add(str(value).replace(",", "").rstrip("%").strip())
    return out


def numbers_in(text: str, chapter_count: int = 0) -> set[str]:
    """Numbers worth checking: two or more digits, or with a decimal point.
    Left out: clock times (12:30), `code` spans (screen text such as file names
    and terminal output, not speech), zero-padded list numbers (01, 02) and references
    to this summary's chapters ("17장", "챕터 14") up to ``chapter_count``."""
    text = CODE_RE.sub(" ", text)
    text = TIME_RE.sub(" ", text)
    text = CHAPTER_REF_RE.sub(
        lambda m: " " if int(m.group(1) or m.group(2)) <= chapter_count else m.group(0), text)
    found = set()
    for raw in NUMBER_RE.findall(text):
        num = raw.replace(",", "").rstrip(".")
        if num.startswith("0") and "." not in num:
            continue
        if len(num.replace(".", "")) >= 2 or "." in num:
            found.add(num)
    return found


def check(run_dir: Path, max_gap: float, allow_missing_key_point: bool = False) -> dict:
    internal = existing_work_dir(run_dir)
    fails: list[str] = []
    warns: list[str] = []

    metadata = read_json(internal / "metadata.json")
    duration = float(metadata.get("duration") or 0)
    chapters = read_json(internal / "chapters.codex.json").get("chapters", [])
    if not chapters:
        fails.append("chapters.codex.json has no chapters")

    # ── key point (SKILL.md Phase 4: required in every chapter) ──
    no_key = [ch.get("id", "?") for ch in chapters
              if not isinstance(ch.get("key_point"), str) or not ch["key_point"].strip()]
    if no_key:
        line = (f"{len(no_key)} of {len(chapters)} chapters have no key_point "
                f"(one-line takeaway, SKILL.md Phase 4): {', '.join(no_key)}")
        (warns if allow_missing_key_point else fails).append(line)

    # ── time range ──
    # metadata duration is whole seconds and the last caption often ends 1~2 s after it
    # (measured on 111 existing runs: 30 of 31 overshoots were 2.3 s or less)
    slack = 2.5
    for ch in chapters:
        cid, start, end = ch.get("id", "?"), float(ch.get("start", 0)), float(ch.get("end", 0))
        if start < 0 or (duration and start > duration + slack):
            fails.append(f"{cid}: start {format_ts(start)} is outside the video (0 ~ {format_ts(duration)})")
        if duration and end > duration + slack:
            fails.append(f"{cid}: end {format_ts(end)} is past the video length {format_ts(duration)}")
        if end <= start:
            fails.append(f"{cid}: end {format_ts(end)} is not after start {format_ts(start)}")

    # ── overlaps and gaps (in the order written) ──
    for prev, cur in zip(chapters, chapters[1:]):
        p_end, c_start = float(prev.get("end", 0)), float(cur.get("start", 0))
        if c_start < p_end - 0.5:
            fails.append(f"{prev.get('id')} / {cur.get('id')}: overlap {format_ts(c_start)} < {format_ts(p_end)}")
        elif c_start - p_end > max_gap:
            fails.append(f"{prev.get('id')} / {cur.get('id')}: gap {c_start - p_end:.1f}s "
                         f"({format_ts(p_end)} ~ {format_ts(c_start)}) is not covered")
    if chapters and duration:
        first, last = float(chapters[0].get("start", 0)), float(chapters[-1].get("end", 0))
        if first > max_gap:
            warns.append(f"video start 00:00 ~ {format_ts(first)} is not in any chapter")
        if duration - last > max_gap:
            warns.append(f"video end {format_ts(last)} ~ {format_ts(duration)} is not in any chapter")

    # ── chapter plan (plan_chapters.py) ──
    plan_path = internal / "chapter-plan.json"
    if plan_path.exists() and chapters:
        planned = read_json(plan_path).get("chapters", [])
        if len(planned) != len(chapters):
            warns.append(f"{len(chapters)} chapters but chapter-plan.json has {len(planned)} "
                         f"(write the plan's start/end, or re-run plan_chapters.py)")
        else:
            off = [f"{ch.get('id')} {edge} {format_ts(float(ch.get(edge, 0)))} vs plan {format_ts(float(pl[edge]))}"
                   for ch, pl in zip(chapters, planned) for edge in ("start", "end")
                   if abs(float(ch.get(edge, 0)) - float(pl[edge])) > 1.0]
            if off:
                warns.append("chapters differ from chapter-plan.json: " + "; ".join(off))

    # ── images ──
    selected_path = internal / "selected-frames.json"
    text_only = not selected_path.exists()
    if not text_only:
        selections = read_json(selected_path).get("selections", [])
        with_image = {s.get("chapter_id") for s in selections}
        for ch in chapters:
            if ch.get("id") not in with_image:
                fails.append(f"{ch.get('id')}: no selected image")
        for s in selections:
            path = first_existing(internal / s.get("image_path", ""), run_dir / s.get("image_path", ""))
            if not s.get("image_path") or not path.is_file():
                fails.append(f"{s.get('chapter_id')}: image file missing: {s.get('image_path')}")

    # ── numbers against the transcript ──
    transcript_path = internal / "transcript.json"
    unmatched: dict[str, list[str]] = {}
    if transcript_path.exists():
        spoken = " ".join(seg.get("text", "") for seg in read_json(transcript_path).get("segments", []))
        spoken_numbers = {n.replace(",", "") for n in NUMBER_RE.findall(spoken)}
        spoken_flat = spoken.replace(",", "")
        for ch in chapters:
            on_screen = verified_numbers(ch)
            missing = sorted(n for n in numbers_in(chapter_text(ch), len(chapters))
                             if n not in spoken_numbers and n not in spoken_flat and n not in on_screen)
            if missing:
                unmatched[ch.get("id", "?")] = missing
                warns.append(f"{ch.get('id')}: numbers not found in the transcript: {', '.join(missing)}")
    else:
        warns.append("transcript.json missing — numbers not checked")

    return {
        "run_dir": str(run_dir),
        "chapters": len(chapters),
        "duration": duration,
        "text_only": text_only,
        "fails": fails,
        "warns": warns,
        "unmatched_numbers": unmatched,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check chapters, images and numbers of a summary run.")
    parser.add_argument("run_dir")
    parser.add_argument("--max-gap", type=float, default=2.0, help="largest uncovered gap between chapters, seconds")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    parser.add_argument("--allow-missing-key-point", action="store_true",
                        help="missing key_point is a WARN, not a FAIL (runs made before 2026-11-02; clean_run.py)")
    args = parser.parse_args()

    result = check(Path(args.run_dir), args.max_gap, args.allow_missing_key_point)
    failed = bool(result["fails"]) or (args.strict and bool(result["warns"]))
    result["ok"] = not failed
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        mode = "text-only" if result["text_only"] else "with images"
        print(f"{'OK  ' if not failed else 'FAIL'} {result['chapters']} chapters, {mode}, "
              f"video {format_ts(result['duration'])}")
        for line in result["fails"]:
            print("  FAIL " + line)
        for line in result["warns"]:
            print("  WARN " + line)
    return 1 if failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
