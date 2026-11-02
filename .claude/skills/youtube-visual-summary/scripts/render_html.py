#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_mod
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from common import TOOL_URL, existing_work_dir, format_ts, group_selections, load_page_template, place_selections, read_json


KST = timezone(timedelta(hours=9))

LEVEL_LABELS = {"short": "간단 정리", "normal": "보통 정리", "detailed": "상세 정리"}
PLAY_ICON = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>'


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
    for index, ch in enumerate(chapters, start=1):
        cid = ch.get("id", "")
        title = escape(ch.get("title", ""))
        parts.append(f'<li><a href="#{cid}"><span class="no">{index:02d}</span><span>{title}</span></a></li>')
    return "\n    ".join(parts)


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
        out += '\n  <figure class="figure">\n'
        out += f'    <img src="{img_rel}" alt="{alt}" loading="lazy">\n'
        out += f'    <figcaption>{ts_str} · {note}</figcaption>\n'
        out += '  </figure>\n'
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
                f'<a class="time-chip" href="{href}" target="_blank" rel="noopener" '
                f'title="이 지점부터 영상 보기">{PLAY_ICON}{time_label}</a>'
            )
        else:
            time_tag = f'<span class="time-chip">{time_label}</span>'

        section = f'<section class="chapter" id="{cid}">\n'
        section += (
            f'  <header class="ch-head">\n'
            f'    <p class="kicker">CHAPTER {index:02d}</p>\n'
            f'    <h2>{title}</h2>\n'
            f'    {time_tag}\n'
            f'  </header>\n'
        )

        key_point = ch.get("key_point")
        if key_point:
            section += '\n  <div class="callout key">\n'
            section += '    <span class="callout-label">핵심</span>\n'
            section += f"    <p>{render_inline(key_point)}</p>\n"
            section += "  </div>\n"

        placed = place_selections(cid, selections.get(cid, []), internal_dir, images_dir.parent, images_dir)
        section += build_figures(ch, placed.pop(None, []), images_dir.parent, url)

        paragraphs = ch.get("summary_paragraphs", [])
        if paragraphs:
            section += '\n  <div class="prose">\n'
            for para in paragraphs:
                section += f"    <p>{render_inline(para)}</p>\n"
            section += "  </div>\n"

        bullets = ch.get("summary_bullets", [])
        if bullets:
            section += '\n  <ul class="points">\n'
            for i, bullet in enumerate(bullets):
                section += f"    <li>{render_inline(bullet)}</li>\n"
                if i in placed and i < len(bullets) - 1:
                    # close the list so the figure spans the column, then resume
                    section += "  </ul>\n"
                    section += build_figures(ch, placed.pop(i), images_dir.parent, url)
                    section += '  <ul class="points">\n'
            section += "  </ul>\n"
        for rest in placed.values():
            section += build_figures(ch, rest, images_dir.parent, url)

        prompt = ch.get("prompt")
        if prompt:
            label = escape(prompt.get("title") or "따라 하기 프롬프트")
            section += '\n  <div class="prompt">\n'
            section += (f'    <div class="prompt-head"><span>{label}</span>'
                        f'<button class="copy" type="button">복사</button></div>\n')
            section += f'    <pre class="prompt-text">{escape(prompt["text"].rstrip())}</pre>\n'
            section += "  </div>\n"

        commentary = ch.get("commentary")
        if commentary:
            paras = commentary if isinstance(commentary, list) else [commentary]
            section += '\n  <div class="callout note">\n'
            section += '    <span class="callout-label">해설</span>\n'
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

    template = load_page_template("html-template.html")  # base.css inlined

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
    result = result.replace("{{LEVEL_LABEL}}", LEVEL_LABELS.get(summary_level.split("-")[0], summary_level))
    result = result.replace("{{CHAPTER_COUNT}}", str(len(chapters)))
    result = result.replace("{{TOOL_URL}}", TOOL_URL)
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
