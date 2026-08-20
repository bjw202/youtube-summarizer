#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_mod
import re
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


def render_inline(text: str) -> str:
    """HTML-escape, then apply inline markdown: `code` then **bold**."""
    s = html_mod.escape(str(text))
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


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
            f'<li><a href="#{cid}"><span>{title}'
            f'<span class="toc-time">{start} ~ {end}</span></span></a></li>'
        )
    return "\n      ".join(parts)


def watch_url(url: str, seconds: float) -> str:
    """YouTube URL that starts playback at the given offset."""
    if not url:
        return ""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(seconds)}s"


def build_chapters(
    chapters: list[dict],
    selections: dict[str, dict],
    internal_dir: Path,
    images_dir: Path,
    url: str = "",
) -> str:
    parts: list[str] = []
    for index, ch in enumerate(chapters, start=1):
        cid = ch.get("id", "")
        title = escape(ch.get("title", ""))
        start = format_ts(ch.get("start", 0))
        end = format_ts(ch.get("end", 0))

        time_label = f"{start} ~ {end}"
        if url:
            href = escape(watch_url(url, ch.get("start", 0)))
            time_tag = (
                f'<a class="chapter-time" href="{href}" target="_blank" rel="noopener" '
                f'title="이 지점부터 영상 보기">{time_label}</a>'
            )
        else:
            time_tag = f'<span class="chapter-time">{time_label}</span>'

        section = f'<section class="chapter" id="{cid}">\n'
        section += (
            f'  <h2 class="chapter-heading">'
            f'<span class="chapter-num">{index:02d}</span>'
            f'<span>{title}<br>{time_tag}</span></h2>\n'
        )

        key_point = ch.get("key_point")
        if key_point:
            section += '\n  <div class="keypoint">\n'
            section += '    <span class="keypoint-label">핵심 정리</span>\n'
            section += f"    <p>{render_inline(key_point)}</p>\n"
            section += "  </div>\n"

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

        paragraphs = ch.get("summary_paragraphs", [])
        if paragraphs:
            section += '\n  <div class="summary-text">\n'
            for para in paragraphs:
                section += f"    <p>{render_inline(para)}</p>\n"
            section += "  </div>\n"

        bullets = ch.get("summary_bullets", [])
        if bullets:
            section += '\n  <ul class="summary-list">\n'
            for bullet in bullets:
                section += f"    <li>{render_inline(bullet)}</li>\n"
            section += "  </ul>\n"

        commentary = ch.get("commentary")
        if commentary:
            paras = commentary if isinstance(commentary, list) else [commentary]
            section += '\n  <div class="commentary">\n'
            section += '    <span class="commentary-label">해설</span>\n'
            for para in paras:
                section += f"    <p>{render_inline(para)}</p>\n"
            section += "  </div>\n"

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
    result = result.replace("{{CHAPTERS}}", build_chapters(chapters, selections, internal_dir, images_dir, url))
    result = result.replace("{{TIMESTAMP}}", timestamp)

    out = run_dir / "summary.html"
    out.write_text(result, encoding="utf-8")
    print(out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
