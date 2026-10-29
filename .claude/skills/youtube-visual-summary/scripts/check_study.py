#!/usr/bin/env python3
"""QA for a rendered study view. Exits 1 and lists every problem found.

Checks: each scene has a clip with an audio stream, every image the page
references exists, in-page anchors resolve, and no template placeholder is left.
Attribute values are HTML-unescaped before comparing (``&amp;`` false alarms).
"""
from __future__ import annotations

import argparse
import html as html_mod
import re
from pathlib import Path

from common import has_audio_stream
from study_spec import iter_scenes, load_study


def main() -> int:
    parser = argparse.ArgumentParser(description="Check study.html, its clips and images.")
    parser.add_argument("run_dir")
    parser.add_argument("--allow-missing-clips", action="store_true",
                        help="rendered on purpose without clips (play opens YouTube)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    page = run_dir / "study.html"
    if not page.exists():
        print(f"FAIL missing {page} — run render_study.py first")
        return 1
    text = page.read_text(encoding="utf-8")
    spec = load_study(run_dir)
    problems: list[str] = []

    for name, _ in iter_scenes(spec):
        clip = run_dir / "clips" / f"{name}.mp4"
        if not clip.exists():
            if not args.allow_missing_clips:
                problems.append(f"clip missing: {clip.name}")
        elif not has_audio_stream(clip):
            problems.append(f"clip has no audio: {clip.name} (source fetched without --with-audio?)")

    attrs = [html_mod.unescape(v) for v in re.findall(r'(?:src|href)="([^"]+)"', text)]
    for value in attrs:
        if value.startswith("images/") and not (run_dir / value).exists():
            problems.append(f"image missing: {value}")
    ids = set(re.findall(r'\bid="([^"]+)"', text))
    for value in attrs:
        if value.startswith("#") and value[1:] not in ids:
            problems.append(f"broken anchor: {value}")
    for left in sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", text))):
        problems.append(f"placeholder left: {left}")

    if problems:
        for p in problems:
            print(f"FAIL {p}")
        return 1
    scenes = sum(1 for _ in iter_scenes(spec))
    print(f"OK {len(spec['items'])} items, {scenes} scenes, {len(attrs)} links checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
