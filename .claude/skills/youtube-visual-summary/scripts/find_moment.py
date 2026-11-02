#!/usr/bin/env python3
"""Find when a phrase is spoken, to the second — the time to give extract_frames.py --at.

transcript.json lines are about 14 s long (compact transcript lines up to a
minute), too coarse for "여기 보시면" when a slide is on screen for 20 s. This
script looks for the phrase in the caption file the transcript was built from:

  * YouTube auto captions carry a time for every word (<00:11:14.279><c> 보시면</c>)
    → the time of the phrase's first word ("word" in the output)
  * other captions (uploader tracks, speech recognition) have no word times
    → the time is estimated from the phrase's position inside its transcript.json
    segment, characters spread evenly ("estimate" — check the frame)

  uv run python .claude/skills/youtube-visual-summary/scripts/find_moment.py RUN_DIR "여기 보시면" [--chapter chapter-05]

Spaces in the phrase are ignored when matching. Each hit prints the time, its
chapter, the text around it and a ready --at command (phrase time + --settle
seconds: a slide usually appears as the speaker points at it). Grab one frame,
look at it, and if the slide is not there yet try a few seconds later.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import HarnessError, existing_work_dir, parse_ts, read_json, use_utf8_stdio

WORD_RE = re.compile(r"<(\d{1,2}:\d{2}:\d{2}\.\d{3})><c>([^<]*)</c>")
CUE_RE = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?\.\d{3})\s*-->")
TAG_RE = re.compile(r"<[^>]+>")


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def word_times(vtt: Path) -> list[tuple[float, str]]:
    """(time, word) for every word of a YouTube auto-caption file; [] when it has none.
    The first word of a timed line has no tag of its own: it starts with the cue."""
    words: list[tuple[float, str]] = []
    cue_start = None
    for line in vtt.read_text(encoding="utf-8", errors="replace").splitlines():
        m = CUE_RE.match(line)
        if m:
            cue_start = parse_ts(m.group(1))
            continue
        if "<c>" not in line or cue_start is None:
            continue
        first = line.split("<", 1)[0].strip()
        if first:
            words.append((cue_start, first))
        words += [(parse_ts(t), w.strip()) for t, w in WORD_RE.findall(line) if w.strip()]
    return words


def hits_in_words(words: list[tuple[float, str]], phrase: str) -> list[tuple[float, str]]:
    text, owner = "", []
    for i, (_, w) in enumerate(words):
        text += squash(w)
        owner += [i] * len(squash(w))
    out, start = [], 0
    while (pos := text.find(phrase, start)) >= 0:
        i = owner[pos]
        context = " ".join(w for _, w in words[max(0, i - 6): i + 10])
        out.append((words[i][0], context))
        start = pos + 1
    return out


def hits_in_segments(segments: list[dict], phrase: str) -> list[tuple[float, str]]:
    out = []
    for seg in segments:
        flat = squash(seg.get("text", ""))
        start = 0
        while flat and (pos := flat.find(phrase, start)) >= 0:
            t0, t1 = float(seg["start"]), float(seg["end"])
            out.append((round(t0 + (t1 - t0) * pos / len(flat), 2), seg["text"]))
            start = pos + 1
    return out


def mmss(t: float) -> str:
    whole = int(t)
    h, m, s = whole // 3600, whole % 3600 // 60, t - whole // 60 * 60
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m:02d}:{s:04.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Find the second a phrase is spoken (for extract_frames.py --at).")
    parser.add_argument("run_dir")
    parser.add_argument("phrase")
    parser.add_argument("--chapter", help="only hits inside this chapter")
    parser.add_argument("--settle", type=float, default=1.0,
                        help="seconds added to the phrase time in the suggested --at (default 1)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    internal = existing_work_dir(run_dir)
    transcript = read_json(internal / "transcript.json")
    phrase = squash(args.phrase)
    if not phrase:
        raise HarnessError("empty phrase")
    vtt = internal / "captions" / str(transcript.get("caption_file") or "")
    words = word_times(vtt) if vtt.is_file() and vtt.suffix == ".vtt" else []
    kind = "word" if words else "estimate"
    hits = hits_in_words(words, phrase) if words else hits_in_segments(transcript.get("segments", []), phrase)

    chapters_path = internal / "chapters.codex.json"
    chapters = read_json(chapters_path).get("chapters", []) if chapters_path.exists() else []
    def chapter_of(t: float) -> str:
        return next((c["id"] for c in chapters if float(c["start"]) <= t < float(c["end"])), "-")
    if args.chapter:
        hits = [h for h in hits if chapter_of(h[0]) == args.chapter]
    if not hits:
        print(f'no match for "{args.phrase}"' + (f" in {args.chapter}" if args.chapter else ""))
        return 1
    for t, context in hits:
        at = round(t + args.settle, 1)
        cid = chapter_of(t)
        print(f"{mmss(t)}  {kind:8}  {cid:11}  {context[:90]}")
        print(f"          → extract_frames.py RUN_DIR --at {at}" + (f" --chapter {cid}" if cid != "-" else ""))
    return 0


if __name__ == "__main__":
    use_utf8_stdio()
    raise SystemExit(main())
