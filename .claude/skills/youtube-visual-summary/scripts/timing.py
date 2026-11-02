#!/usr/bin/env python3
"""Record when each Phase starts and ends, in RUN_DIR/_work/timing.log.

  uv run python .claude/skills/youtube-visual-summary/scripts/timing.py RUN_DIR "Phase 5" start
  uv run python .claude/skills/youtube-visual-summary/scripts/timing.py RUN_DIR "Phase 5" end
  uv run python .claude/skills/youtube-visual-summary/scripts/timing.py RUN_DIR --summary

Each mark appends one tab-separated line: local time, phase, start|end.
fetch_youtube.py writes the "Phase 3" start itself (RUN_DIR does not exist
before it runs); fetch_frame_source.py writes "download" start and end (or
"failed") itself, because it runs in the background during Phase 4. --summary prints every
phase's duration, overlaps included, and the time from the first mark to the
last.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from common import HarnessError, existing_work_dir, use_utf8_stdio

FMT = "%Y-%m-%d %H:%M:%S"


def log_path(run_dir: Path) -> Path:
    return existing_work_dir(run_dir) / "timing.log"


def mark(run_dir: Path, phase: str, edge: str, when: datetime | None = None) -> str:
    line = f"{(when or datetime.now()).strftime(FMT)}\t{phase}\t{edge}\n"
    with log_path(run_dir).open("a", encoding="utf-8") as f:
        f.write(line)
    return line.strip()


def span(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}분 {seconds % 60:02d}초" if seconds >= 60 else f"{seconds}초"


def summary(run_dir: Path) -> str:
    path = log_path(run_dir)
    if not path.exists():
        raise HarnessError(f"no {path} — mark phases first")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            rows.append((datetime.strptime(parts[0], FMT), parts[1], parts[2]))
    starts: dict[str, datetime] = {}
    out = []
    for when, phase, edge in rows:
        if edge == "start":
            starts[phase] = when
        elif edge in ("end", "failed") and phase in starts:
            began = starts.pop(phase)
            note = "  (failed)" if edge == "failed" else ""
            out.append(f"{phase:16} {began:%H:%M:%S} – {when:%H:%M:%S}  {span((when - began).total_seconds())}{note}")
    for phase, began in starts.items():
        out.append(f"{phase:16} {began:%H:%M:%S} – (no end mark)")
    if rows:
        total = (max(r[0] for r in rows) - min(r[0] for r in rows)).total_seconds()
        out.append(f"{'total':16} {min(r[0] for r in rows):%H:%M:%S} – {max(r[0] for r in rows):%H:%M:%S}  {span(total)}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark Phase start/end times in _work/timing.log.")
    parser.add_argument("run_dir")
    parser.add_argument("phase", nargs="?", help='e.g. "Phase 5"')
    parser.add_argument("edge", nargs="?", choices=("start", "end"))
    parser.add_argument("--summary", action="store_true", help="print durations instead of marking")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    if args.summary:
        print(summary(run_dir))
        return 0
    if not args.phase or not args.edge:
        parser.error('give PHASE and start|end, or --summary')
    print(mark(run_dir, args.phase, args.edge))
    return 0


if __name__ == "__main__":
    use_utf8_stdio()
    raise SystemExit(main())
