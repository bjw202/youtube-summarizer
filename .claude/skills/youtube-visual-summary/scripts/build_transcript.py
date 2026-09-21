#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from common import HarnessError, existing_work_dir, parse_ts, read_json, write_json


TIME_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_vtt(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    segments = []
    i = 0
    while i < len(lines):
        match = TIME_RE.search(lines[i])
        if not match:
            i += 1
            continue
        start = parse_ts(match.group("start"))
        end = parse_ts(match.group("end"))
        i += 1
        text_lines = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i])
            i += 1
        text = clean_text(text_lines)
        if text:
            if segments and abs(segments[-1]["start"] - start) < 0.05 and segments[-1]["text"] == text:
                segments[-1]["end"] = max(segments[-1]["end"], end)
            else:
                segments.append({"start": start, "end": end, "text": text})
        i += 1
    return segments


def word_overlap(left: list[str], right: list[str], max_words: int = 30) -> int:
    limit = min(len(left), len(right), max_words)
    for size in range(limit, 0, -1):
        if left[-size:] == right[:size]:
            return size
    return 0


def collapse_rolling_segments(segments: list[dict], max_duration: float = 14.0) -> list[dict]:
    if not segments:
        return []

    output = []
    seen_words: list[str] = []
    current_words: list[str] = []
    current_start: float | None = None
    current_end = 0.0

    def flush() -> None:
        nonlocal current_words, current_start, current_end
        if current_words and current_start is not None:
            output.append({
                "start": current_start,
                "end": current_end,
                "text": " ".join(current_words),
            })
        current_words = []
        current_start = None
        current_end = 0.0

    for segment in segments:
        words = segment["text"].split()
        if not words:
            continue
        overlap = word_overlap(seen_words, words)
        new_words = words[overlap:]
        if not new_words:
            continue
        if current_start is None:
            current_start = segment["start"]
        current_words.extend(new_words)
        current_end = segment["end"]
        seen_words.extend(new_words)
        if len(seen_words) > 200:
            seen_words = seen_words[-200:]
        duration = current_end - current_start
        ends_sentence = current_words[-1].endswith((".", "?", "!"))
        if duration >= max_duration or (duration >= 6.0 and ends_sentence):
            flush()

    flush()
    return output


def score_caption(path: Path, prefer_lang: str | None = None) -> tuple[int, str]:
    name = path.name.lower()
    score = 0
    if prefer_lang and re.search(rf"\.{re.escape(prefer_lang.lower())}(-[^.]+)?\.vtt$", name):
        score += 1000
    if ".ko" in name:
        score += 100
    if ".en" in name:
        score += 80
    # uploader-provided tracks come as e.g. ".en-j3PyPqV-e1s.vtt"; they beat
    # the auto-generated ".en.vtt", which mangles proper nouns.
    if re.search(r"\.[a-z]{2}-[^.]+\.vtt$", name) and "-orig" not in name:
        score += 15
    if "auto" not in name:
        score += 10
    return (-score, name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize downloaded YouTube captions to transcript.json.")
    parser.add_argument("run_dir")
    parser.add_argument("--lang", default=None, help="caption language to force as canonical, e.g. en (default: ko > en)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    metadata = read_json(internal_dir / "metadata.json")
    caption_files = sorted((internal_dir / "captions").glob("*.vtt"), key=lambda p: score_caption(p, args.lang))
    if not caption_files:
        caption_files = sorted(internal_dir.glob("*.vtt"), key=lambda p: score_caption(p, args.lang))
    if not caption_files:
        raise HarnessError(
            "no VTT captions found. Default workflow stops here; ask before using optional local STT."
        )

    chosen = caption_files[0]
    segments = collapse_rolling_segments(parse_vtt(chosen))
    if not segments:
        raise HarnessError(f"caption file contained no parseable segments: {chosen}")

    transcript = {
        "source": "caption",
        "caption_file": chosen.name,
        "language": chosen.suffixes[-2].lstrip(".") if len(chosen.suffixes) >= 2 else None,
        "video_title": metadata.get("title"),
        "segments": segments,
    }
    write_json(internal_dir / "transcript.json", transcript)
    print((internal_dir / "transcript.json").resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
