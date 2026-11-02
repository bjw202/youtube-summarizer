#!/usr/bin/env python3
"""Compute chapter boundaries for Phase 4 — the same video gives the same chapters.

  uv run python .claude/skills/youtube-visual-summary/scripts/plan_chapters.py RUN_DIR --level detailed
  uv run python .claude/skills/youtube-visual-summary/scripts/plan_chapters.py RUN_DIR --level detailed --anchor 881.75 --anchor 972.25

Writes RUN_DIR/_work/chapter-plan.json and prints the table. Claude then writes
chapters.codex.json with exactly these start/end times (titles and text are Claude's).
check_summary.py warns when chapters.codex.json and the plan disagree.

Starting point: uploader chapters (metadata.json "chapters") → else the description's
timestamp list (two or more "m:ss title" lines starting at 0:00) → else the whole video.

Rules (references/summary-levels.md "챕터 나누기 수치"):
  * short     merge neighbours: add the next chapter while the group is under 5 min,
              or while the group stays within 15 min
  * normal    split chapters over 10 min into ceil(len / 8 min) pieces
  * detailed  split chapters over 6 min into ceil(len / 5 min) pieces
  * normal/detailed: a chapter under 60 s is merged into its neighbour only when its
    title says greeting / ad / teaser / outro (GREETING); a named concept stays
  * no uploader chapters: ceil(duration / target) pieces of the whole video
    (target short 10 min, normal 5.5, detailed 3.5)

Sentences come from the caption file: YouTube auto captions carry a time per word, so a
sentence starts at the word after one ending in . ? ! (exact). Captions without word times
fall back to transcript.json segments, sentence starts placed by character position
(estimate). A *transition sentence* starts with a hand-over phrase (TRANSITION).

  boundary  an uploader boundary B moves to the start of the transition sentence nearest
            to B within ±15 s (tie → the earlier one); with none there, B stays
  split     between pieces of one chapter (len L, n pieces): ideal point start + k·L/n,
            window ideal ± 0.3·L/n (two pieces → each 35~65 % of L), every piece ≥ 2 min.
            Pick ① the transition sentence nearest the ideal point in the window,
            ② else the sentence start nearest it, ③ else the ideal point itself
  --anchor T  (Phase 6) T = manifest timestamp of the first candidate frame whose on-screen
            topic bar shows the new text (a new slide under the old bar does not count).
            Pass every bar change seen; repeatable. For each split point the script takes,
            among the anchors inside its window, the one nearest the ideal point (tie → the
            earlier) and, if that anchor is more than 20 s from the split point, moves the
            split to the sentence start nearest it. Anchors outside every window are ignored.
            Uploader boundaries never move by --anchor. Anchors are kept in the plan, so a
            re-run gives the same result.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

from common import HarnessError, existing_work_dir, format_ts, read_json, use_utf8_stdio, write_json
from find_moment import word_times

LEVELS = {  # split chapters longer than max_len into pieces of about piece_len (seconds)
    "short": {"merge_min": 300, "merge_max": 900, "target": 600},
    "normal": {"max_len": 600, "piece_len": 480, "target": 330},
    "detailed": {"max_len": 360, "piece_len": 300, "target": 210},
}
SNAP = 15.0          # seconds an uploader boundary may move to a transition sentence
WINDOW = 0.3         # split window: ideal point ± WINDOW · (L / n)
MIN_PIECE = 120.0    # no split piece shorter than this
ANCHOR_SHIFT = 20.0  # an --anchor moves a split point only when it is more than this away
SHORT_CHAPTER = 60.0
# hand-over phrases at a sentence start. Not "그럼"/"그러면": mid-thought fillers in
# Korean lectures (stroke lecture 39:46 "그럼 여러분들 가시면서…" is no new topic)
TRANSITION = re.compile(
    r"^(자[,.\s]|자$|그렇다면|그다음|다음으로|다음은|이번에는|이번엔|첫\s?번째|두\s?번째|세\s?번째|네\s?번째|"
    r"다섯\s?번째|마지막으로|또\s?한\s?가지|또\s?하나|한편|정리하면|결론적으로|"
    r"so[,\s]|now[,\s]|next|first|second|third|finally|let'?s|okay|ok[,\s]|all right|alright|moving on|in summary)",
    re.IGNORECASE)
GREETING = re.compile(r"인트로|오프닝|인사|광고|협찬|구독|아웃트로|엔딩|예고|티저|intro|opening|sponsor|ad\b|"
                      r"subscribe|outro|ending|teaser|trailer", re.IGNORECASE)
END_RE = re.compile(r"[.?!。]$")
TS_LINE = re.compile(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s*[-–—:]?\s*(.+?)\s*$")


def parse_clock(value: str) -> float:
    seconds = 0.0
    for part in value.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def source_chapters(meta: dict, duration: float) -> tuple[str, list[dict]]:
    chapters = meta.get("chapters") or []
    if chapters:
        return "uploader", [{"start": float(c["start_time"]), "end": float(c["end_time"]), "title": c.get("title", "")}
                            for c in chapters]
    marks = []
    for line in (meta.get("description") or "").splitlines():
        m = TS_LINE.match(line)
        if m:
            marks.append((parse_clock(m.group(1)), m.group(2)))
    if len(marks) >= 2 and marks[0][0] == 0:
        out = [{"start": t, "end": marks[i + 1][0] if i + 1 < len(marks) else duration, "title": title}
               for i, (t, title) in enumerate(marks)]
        return "description", [c for c in out if c["end"] > c["start"]]
    return "none", [{"start": 0.0, "end": duration, "title": ""}]


def sentences(internal: Path, transcript: dict) -> tuple[str, list[tuple[float, str]]]:
    """(time, first words) of every sentence start."""
    vtt = internal / "captions" / str(transcript.get("caption_file") or "")
    words = word_times(vtt) if vtt.is_file() and vtt.suffix == ".vtt" else []
    out: list[tuple[float, str]] = []
    if words:
        for i, (t, w) in enumerate(words):
            if i == 0 or END_RE.search(words[i - 1][1]):
                out.append((round(t, 2), " ".join(x for _, x in words[i:i + 6])))
        return "word", out
    for seg in transcript.get("segments", []):
        text, t0, t1 = seg.get("text", ""), float(seg["start"]), float(seg["end"])
        for m in re.finditer(r"(?:^|(?<=[.?!。]))\s*(\S[^.?!。]*)", text):
            out.append((round(t0 + (t1 - t0) * m.start(1) / max(1, len(text)), 2), m.group(1)[:60]))
    return "estimate", out


def nearest(cands: list[tuple[float, str]], target: float) -> tuple[float, str] | None:
    return min(cands, key=lambda c: (abs(c[0] - target), c[0]), default=None)


def snap_boundary(b: float, sents: list[tuple[float, str]]) -> tuple[float, str, str]:
    hit = nearest([s for s in sents if abs(s[0] - b) <= SNAP and TRANSITION.match(s[1])], b)
    return (hit[0], "boundary: transition", hit[1]) if hit else (b, "boundary: uploader", "")


def split_points(start: float, end: float, n: int, sents: list[tuple[float, str]]) -> list[dict]:
    length = end - start
    points, prev = [], start
    for k in range(1, n):
        ideal = start + k * length / n
        lo = max(ideal - WINDOW * length / n, prev + MIN_PIECE)
        hi = min(ideal + WINDOW * length / n, end - MIN_PIECE * (n - k))
        inside = [s for s in sents if lo <= s[0] <= hi]
        pick = nearest([s for s in inside if TRANSITION.match(s[1])], ideal)
        rule = "split: transition"
        if not pick:
            pick, rule = nearest(inside, ideal), "split: sentence"
        if not pick:
            pick, rule = (round(ideal, 2), ""), "split: even"
        points.append({"time": pick[0], "rule": rule, "text": pick[1], "ideal": round(ideal, 2),
                       "window": [round(lo, 2), round(hi, 2)]})
        prev = pick[0]
    return points


def plan(run_dir: Path, level: str, anchors: list[float]) -> dict:
    internal = existing_work_dir(run_dir)
    meta = read_json(internal / "metadata.json")
    transcript = read_json(internal / "transcript.json")
    duration = float(meta.get("duration") or transcript["segments"][-1]["end"])
    origin, base = source_chapters(meta, duration)
    timing, sents = sentences(internal, transcript)
    rules = LEVELS[level]

    if level == "short" and origin != "none":
        groups: list[dict] = []
        for c in base:
            g = groups[-1] if groups else None
            if g and ((g["end"] - g["start"]) < rules["merge_min"]
                      or (c["end"] - g["start"]) <= rules["merge_max"]):
                g["end"], g["titles"] = c["end"], g["titles"] + [c["title"]]
            else:
                groups.append({"start": c["start"], "end": c["end"], "titles": [c["title"]]})
        base = [{"start": g["start"], "end": g["end"], "title": " / ".join(t for t in g["titles"] if t)} for g in groups]
    elif origin != "none":
        merged: list[dict] = []
        for i, c in enumerate(base):
            if c["end"] - c["start"] < SHORT_CHAPTER and GREETING.search(c["title"] or "") and len(base) > 1:
                if i + 1 < len(base):
                    base[i + 1] = {**base[i + 1], "start": c["start"]}
                elif merged:
                    merged[-1]["end"] = c["end"]
                continue
            merged.append(dict(c))
        base = merged

    chapters: list[dict] = []
    for i, c in enumerate(base):
        start, start_rule, start_text = (0.0, "video start", "") if i == 0 else snap_boundary(c["start"], sents)
        end = snap_boundary(base[i + 1]["start"], sents)[0] if i + 1 < len(base) else max(c["end"], duration)
        length = end - start
        if origin == "none":
            n = max(1, math.ceil(length / rules["target"]))
        elif level != "short" and length > rules["max_len"]:
            n = math.ceil(length / rules["piece_len"])
        else:
            n = 1
        pts = split_points(start, end, n, sents) if n > 1 else []
        for p in pts:   # Phase 6: the on-screen topic bar changed inside this split's window
            lo, hi = p["window"]
            inside = [a for a in anchors if lo <= a <= hi]
            if not inside:
                continue
            a = min(inside, key=lambda t: (abs(t - p["ideal"]), t))   # one per split, nearest the ideal point
            if abs(a - p["time"]) <= ANCHOR_SHIFT:
                continue
            hit = nearest([s for s in sents if lo <= s[0] <= hi], a)
            if hit:
                p.update(time=hit[0], rule=f"split: anchor {a:g}", text=hit[1])
        edges = [(start, start_rule, start_text)] + [(p["time"], p["rule"], p["text"]) for p in pts]
        for k, (t0, rule, text) in enumerate(edges):
            t1 = edges[k + 1][0] if k + 1 < len(edges) else end
            chapters.append({"start": round(t0, 2), "end": round(t1, 2), "uploader_title": c["title"],
                             "piece": f"{k + 1}/{len(edges)}", "start_rule": rule, "start_text": text})
    for i, c in enumerate(chapters, 1):
        c["id"] = f"chapter-{i:02d}"
    return {"level": level, "source": origin, "sentence_times": timing, "anchors": anchors,
            "duration": duration, "chapters": chapters}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute chapter boundaries and split points (Phase 4).")
    parser.add_argument("run_dir")
    parser.add_argument("--level", choices=sorted(LEVELS), required=True)
    parser.add_argument("--anchor", type=float, action="append", default=None,
                        help="Phase 6: manifest timestamp where a new on-screen topic bar first shows; pass every change, repeatable")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    out = existing_work_dir(run_dir) / "chapter-plan.json"
    anchors = args.anchor
    if anchors is None:   # keep earlier anchors of the same level
        old = read_json(out) if out.exists() else {}
        anchors = old.get("anchors", []) if old.get("level") == args.level else []
    result = plan(run_dir, args.level, sorted(set(anchors)))
    write_json(out, result)
    print(f"{len(result['chapters'])} chapters ({args.level}, from {result['source']} chapters, "
          f"sentence times: {result['sentence_times']}) → {out}")
    for c in result["chapters"]:
        text = f"  “{c['start_text'][:40]}”" if c["start_text"] else ""
        print(f"  {c['id']}  {format_ts(c['start'])}–{format_ts(c['end'])}  {c['end'] - c['start']:6.1f}s  "
              f"{c['piece']:4} {c['start_rule'][:28]:28} {c['uploader_title'][:30]}{text}")
    return 0


if __name__ == "__main__":
    use_utf8_stdio()
    raise SystemExit(main())
