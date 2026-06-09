#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_mod
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from common import HarnessError, existing_work_dir, first_existing, format_ts, read_json


KST = timezone(timedelta(hours=9))

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_PATH = SKILL_DIR / "assets" / "html-template.html"


def escape(text: str) -> str:
    return html_mod.escape(str(text))


def build_tags(chapters: list[dict]) -> str:
    parts = []
    for ch in chapters:
        title = escape(ch.get("title", ""))
        parts.append(f'<span class="tag">#{title}</span>')
    return "\n    ".join(parts)


def build_toc(chapters: list[dict]) -> str:
    parts = []
    for ch in chapters:
        cid = ch.get("id", "")
        title = escape(ch.get("title", ""))
        start = format_ts(ch.get("start", 0))
        end = format_ts(ch.get("end", 0))
        parts.append(
            f'<li><a href="#{cid}">{title} '
            f'<span class="chapter-time">{start} ~ {end}</span></a></li>'
        )
    return "\n      ".join(parts)


def build_chapters(
    chapters: list[dict],
    selections: dict[str, dict],
    internal_dir: Path,
    images_dir: Path,
) -> str:
    parts: list[str] = []
    for ch in chapters:
        cid = ch.get("id", "")
        title = escape(ch.get("title", ""))
        start = format_ts(ch.get("start", 0))
        end = format_ts(ch.get("end", 0))

        section = f'<section class="chapter" id="{cid}">\n'
        section += f'  <h2 class="chapter-heading">{title} <span class="chapter-time">{start} ~ {end}</span></h2>\n'

        sel = selections.get(cid)
        if sel:
            source = first_existing(
                internal_dir / sel["image_path"],
                images_dir.parent / sel["image_path"],
            )
            if source.exists():
                target = images_dir / f"{cid}{source.suffix}"
                shutil.copy2(source, target)
                alt = escape(ch.get("visual_query") or ch.get("title", ""))
                img_rel = target.relative_to(images_dir.parent).as_posix()
                ts_str = format_ts(sel.get("timestamp", 0))
                reason = escape(sel.get("reason", ""))
                section += f'\n  <div class="chapter-image">\n'
                section += f'    <img src="{img_rel}" alt="{alt}" loading="lazy">\n'
                section += f'    <div class="chapter-image-caption">Frame: {ts_str}. {reason}</div>\n'
                section += f'  </div>\n'

        bullets = ch.get("summary_bullets", [])
        if bullets:
            section += '\n  <ul class="summary-list">\n'
            for bullet in bullets:
                section += f"    <li>{escape(bullet)}</li>\n"
            section += "  </ul>\n"

        section += "</section>"
        parts.append(section)

    return "\n\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render final visual summary HTML.")
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    metadata = read_json(internal_dir / "metadata.json")
    chapters_data = read_json(internal_dir / "chapters.codex.json")
    selected = read_json(internal_dir / "selected-frames.json")
    selections = {item["chapter_id"]: item for item in selected.get("selections", [])}
    images_dir = run_dir / "images"
    images_dir.mkdir(exist_ok=True)

    if not TEMPLATE_PATH.exists():
        raise HarnessError(f"HTML template not found: {TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    url = metadata.get("webpage_url") or read_json(internal_dir / "input.json").get("url", "")
    title = metadata.get("title") or "YouTube Visual Summary"
    channel = metadata.get("channel") or metadata.get("uploader") or "Unknown"
    duration = format_ts(float(metadata.get("duration") or 0))
    summary_level = chapters_data.get("summary_level", "normal")
    chapters = chapters_data.get("chapters", [])
    timestamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    result = template
    result = result.replace("{{TITLE}}", escape(title))
    result = result.replace("{{URL}}", escape(url))
    result = result.replace("{{CHANNEL}}", escape(channel))
    result = result.replace("{{DURATION}}", duration)
    result = result.replace("{{SUMMARY_LEVEL}}", summary_level)
    result = result.replace("{{TAGS}}", build_tags(chapters))
    result = result.replace("{{TOC}}", build_toc(chapters))
    result = result.replace("{{CHAPTERS}}", build_chapters(chapters, selections, internal_dir, images_dir))
    result = result.replace("{{TIMESTAMP}}", timestamp)

    out = run_dir / "summary.html"
    out.write_text(result, encoding="utf-8")
    print(out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
