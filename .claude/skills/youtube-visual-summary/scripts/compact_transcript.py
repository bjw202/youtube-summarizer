#!/usr/bin/env python3
"""Write a compact, line-per-sentence transcript for reading long videos.

transcript.json repeats keys, end times and quotes on every short segment. This
writes the same text as `[mm:ss] sentence` lines (about 20% smaller on Korean
runs, measured) and joins segments until a sentence ends (or --max-chars is
reached), so each line is one readable thought with its time.

Outputs (in RUN_DIR/_work/):
  transcript.compact.txt            the whole video
  transcript.compact.partNN.txt     only when the video is longer than --part-minutes;
                                    one file per --part-minutes, cut at line boundaries

usage: compact_transcript.py RUN_DIR [--part-minutes 30] [--max-chars 240]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import existing_work_dir, format_ts, read_json

SENTENCE_END = re.compile(r"[.!?。？！]['\"”’)]*$|(?:다|요|죠|까|니다|습니다)[.!?]?$")


def compact_lines(segments: list[dict], max_chars: int) -> list[tuple[float, str]]:
    lines: list[tuple[float, str]] = []
    start: float | None = None
    buf: list[str] = []
    for seg in segments:
        text = " ".join(str(seg.get("text", "")).split())
        if not text:
            continue
        if start is None:
            start = float(seg.get("start", 0))
        buf.append(text)
        joined = " ".join(buf)
        if SENTENCE_END.search(joined) or len(joined) >= max_chars:
            lines.append((start, joined))
            start, buf = None, []
    if buf and start is not None:
        lines.append((start, " ".join(buf)))
    return lines


def render(lines: list[tuple[float, str]]) -> str:
    return "".join(f"[{format_ts(t)}] {text}\n" for t, text in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write _work/transcript.compact.txt ([mm:ss] sentence lines).")
    parser.add_argument("run_dir")
    parser.add_argument("--part-minutes", type=float, default=30.0,
                        help="split into parts of this many minutes when the video is longer (default 30)")
    parser.add_argument("--max-chars", type=int, default=240, help="cut a line that grows past this length")
    args = parser.parse_args()

    internal = existing_work_dir(Path(args.run_dir))
    segments = read_json(internal / "transcript.json").get("segments", [])
    lines = compact_lines(segments, args.max_chars)
    out = internal / "transcript.compact.txt"
    out.write_text(render(lines), encoding="utf-8")

    for old in internal.glob("transcript.compact.part*.txt"):
        old.unlink()
    span = args.part_minutes * 60
    end = max((float(s.get("end", 0)) for s in segments), default=0.0)
    parts: list[Path] = []
    if lines and end > span:
        buckets: dict[int, list[tuple[float, str]]] = {}
        for t, text in lines:
            buckets.setdefault(int(t // span), []).append((t, text))
        for n, idx in enumerate(sorted(buckets), 1):
            part = internal / f"transcript.compact.part{n:02d}.txt"
            part.write_text(render(buckets[idx]), encoding="utf-8")
            parts.append(part)

    size_json = (internal / "transcript.json").stat().st_size
    print(f"{out}  {len(lines)} lines, {out.stat().st_size // 1024} KB "
          f"(transcript.json {size_json // 1024} KB), video {format_ts(end)}")
    for part in parts:
        text = part.read_text(encoding="utf-8").splitlines()
        print(f"{part}  {text[0][:9]} ~ {text[-1][:9]}  {len(text)} lines")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
