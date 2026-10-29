#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import existing_work_dir, format_ts, group_selections, place_selections, read_json


def figure_lines(chapter: dict, placed: list, run_dir: Path) -> list[str]:
    lines: list[str] = []
    for sel, target in placed:
        alt = sel.get("caption") or chapter.get("visual_query") or chapter["title"]
        lines.append(f"![{alt}]({target.relative_to(run_dir).as_posix()})")
        lines.append("")
        note = sel.get("caption") or sel.get("reason")
        if note:
            lines.append(f"*Frame: {format_ts(sel['timestamp'])}. {note}*")
            lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Render final visual summary Markdown.")
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    metadata = read_json(internal_dir / "metadata.json")
    chapters = read_json(internal_dir / "chapters.codex.json")
    selected_path = internal_dir / "selected-frames.json"
    # text-only runs never create this file
    selected = read_json(selected_path) if selected_path.exists() else {"selections": []}
    selections = group_selections(selected)
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
        placed = place_selections(chapter_id, selections.get(chapter_id, []), internal_dir, run_dir, images_dir)
        start = format_ts(chapter["start"])
        end = format_ts(chapter["end"])
        lines.append(f"## {chapter['title']} (time: {start} ~ {end})")
        lines.append("")
        if chapter.get("key_point"):
            lines.append(f"> **핵심 정리** — {chapter['key_point']}")
            lines.append("")
        lines.extend(figure_lines(chapter, placed.pop(None, []), run_dir))
        paragraphs = chapter.get("summary_paragraphs", [])
        if paragraphs:
            for para in paragraphs:
                lines.append(para)
                lines.append("")
        bullets = chapter.get("summary_bullets", [])
        for i, bullet in enumerate(bullets):
            lines.append(f"- {bullet}")
            if i in placed:
                lines.append("")
                lines.extend(figure_lines(chapter, placed.pop(i), run_dir))
        # after_bullet past the last bullet lands at the end
        for rest in placed.values():
            lines.append("")
            lines.extend(figure_lines(chapter, rest, run_dir))
        lines.append("")
        prompt = chapter.get("prompt")
        if prompt:
            lines.append(f"### {prompt.get('title') or '따라 하기 프롬프트'}")
            lines.append("")
            lines.append("```text")
            lines.append(prompt["text"].rstrip())
            lines.append("```")
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
