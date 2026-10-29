#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_mod
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from common import HarnessError, existing_work_dir, format_ts, group_selections, place_selections, read_json


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


def build_figures(ch: dict, placed: list, run_dir: Path, url: str) -> str:
    out = ""
    for sel, target in placed:
        alt = escape(sel.get("caption") or ch.get("visual_query") or ch.get("title", ""))
        img_rel = target.relative_to(run_dir).as_posix()
        ts = sel.get("timestamp", 0)
        ts_str = format_ts(ts)
        if url:
            ts_str = (f'<a href="{escape(watch_url(url, ts))}" target="_blank" rel="noopener">'
                      f'{ts_str}</a>')
        note = render_inline(sel.get("caption") or sel.get("reason", ""))
        out += '\n  <div class="chapter-image">\n'
        out += f'    <img src="{img_rel}" alt="{alt}" loading="lazy">\n'
        out += f'    <div class="chapter-image-caption">Frame: {ts_str}. {note}</div>\n'
        out += '  </div>\n'
    return out


def build_chapters(
    chapters: list[dict],
    selections: dict[str, list[dict]],
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

        placed = place_selections(cid, selections.get(cid, []), internal_dir, images_dir.parent, images_dir)
        section += build_figures(ch, placed.pop(None, []), images_dir.parent, url)

        paragraphs = ch.get("summary_paragraphs", [])
        if paragraphs:
            section += '\n  <div class="summary-text">\n'
            for para in paragraphs:
                section += f"    <p>{render_inline(para)}</p>\n"
            section += "  </div>\n"

        bullets = ch.get("summary_bullets", [])
        if bullets:
            section += '\n  <ul class="summary-list">\n'
            for i, bullet in enumerate(bullets):
                section += f"    <li>{render_inline(bullet)}</li>\n"
                if i in placed and i < len(bullets) - 1:
                    # close the list so the figure spans the column, then resume
                    section += "  </ul>\n"
                    section += build_figures(ch, placed.pop(i), images_dir.parent, url)
                    section += '  <ul class="summary-list">\n'
            section += "  </ul>\n"
        for rest in placed.values():
            section += build_figures(ch, rest, images_dir.parent, url)

        prompt = ch.get("prompt")
        if prompt:
            label = escape(prompt.get("title") or "따라 하기 프롬프트")
            section += '\n  <div class="prompt-card">\n'
            section += (f'    <div class="prompt-head"><span class="prompt-label">{label}</span>'
                        f'<button class="prompt-copy" type="button">복사</button></div>\n')
            section += f'    <pre>{escape(prompt["text"].rstrip())}</pre>\n'
            section += "  </div>\n"

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
    selected_path = internal_dir / "selected-frames.json"
    # text-only runs never create this file
    selected = read_json(selected_path) if selected_path.exists() else {"selections": []}
    selections = group_selections(selected)
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
