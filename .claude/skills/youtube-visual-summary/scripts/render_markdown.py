#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from common import HarnessError, existing_work_dir, first_existing, format_ts, read_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Render final visual summary Markdown.")
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    metadata = read_json(internal_dir / "metadata.json")
    chapters = read_json(internal_dir / "chapters.codex.json")
    selected = read_json(internal_dir / "selected-frames.json")
    selections = {item["chapter_id"]: item for item in selected.get("selections", [])}
    images_dir = run_dir / "images"
    images_dir.mkdir(exist_ok=True)

    lines = [
        f"# {metadata.get('title') or 'YouTube Visual Summary'}",
        "",
        f"- Channel: {metadata.get('channel') or metadata.get('uploader') or 'Unknown'}",
        f"- URL: {metadata.get('webpage_url') or read_json(internal_dir / 'input.json').get('url')}",
        f"- Duration: {format_ts(float(metadata.get('duration') or 0))}",
        f"- Summary level: {chapters.get('summary_level', 'normal')}",
        "",
    ]

    for chapter in chapters.get("chapters", []):
        chapter_id = chapter["id"]
        selection = selections.get(chapter_id)
        start = format_ts(chapter["start"])
        end = format_ts(chapter["end"])
        lines.append(f"## {chapter['title']} (time: {start} ~ {end})")
        lines.append("")
        if chapter.get("key_point"):
            lines.append(f"> **핵심 정리** — {chapter['key_point']}")
            lines.append("")
        if selection:
            source = first_existing(internal_dir / selection["image_path"], run_dir / selection["image_path"])
            if not source.exists():
                raise HarnessError(f"selected image does not exist: {source}")
            target = images_dir / f"{chapter_id}{source.suffix}"
            shutil.copy2(source, target)
            alt = chapter.get("visual_query") or chapter["title"]
            lines.append(f"![{alt}]({target.relative_to(run_dir).as_posix()})")
            lines.append("")
            if selection.get("reason"):
                lines.append(f"*Frame: {format_ts(selection['timestamp'])}. {selection['reason']}*")
                lines.append("")
        paragraphs = chapter.get("summary_paragraphs", [])
        if paragraphs:
            for para in paragraphs:
                lines.append(para)
                lines.append("")
        for bullet in chapter.get("summary_bullets", []):
            lines.append(f"- {bullet}")
        lines.append("")
        commentary = chapter.get("commentary")
        if commentary:
            paras = commentary if isinstance(commentary, list) else [commentary]
            lines.append("### 해설")
            lines.append("")
            for para in paras:
                lines.append(para)
                lines.append("")

    out = run_dir / "summary.md"
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
