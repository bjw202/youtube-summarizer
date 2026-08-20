#!/usr/bin/env python3
"""report.md → report.html 렌더러 (research-synthesis-report 스킬).

사용법:
    .venv/bin/python .claude/skills/research-synthesis-report/scripts/render_report_html.py RUN_DIR

입력: RUN_DIR/report.md
출력: RUN_DIR/report.html

의존: markdown 패키지 (tables, fenced_code, sane_lists, footnotes 확장).
없으면: uv pip install --python .venv/bin/python markdown
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

try:
    import markdown as md_lib
except ImportError:
    sys.exit(
        "markdown 패키지가 없습니다. 설치:\n"
        "  uv pip install --python .venv/bin/python markdown"
    )

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = SKILL_DIR / "assets" / "report-template.html"

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "footnotes"]


def extract_title(md_text: str) -> tuple[str, str]:
    """첫 h1을 제목으로 추출하고 본문에서 제거한다."""
    m = re.search(r"^#\s+(.+?)\s*$", md_text, flags=re.M)
    if not m:
        return "종합 리서치 리포트", md_text
    title = m.group(1).strip()
    body = md_text[: m.start()] + md_text[m.end() :]
    return title, body


def inject_heading_ids(html: str) -> tuple[str, list[tuple[int, str, str]]]:
    """h2/h3에 id를 부여하고 TOC 항목 (level, id, text) 목록을 반환한다."""
    toc: list[tuple[int, str, str]] = []
    counters: dict[int, int] = {}

    def repl(m: re.Match) -> str:
        level = len(m.group(1))
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        counters[level] = counters.get(level, 0) + 1
        sid = f"sec-{level}-{counters[level]}"
        toc.append((level, sid, text))
        return f'<h{level} id="{sid}">{m.group(2)}</h{level}>'

    html = re.sub(r"<h([23])>(.*?)</h\1>", repl, html, flags=re.S)
    return html, toc


def build_toc(toc: list[tuple[int, str, str]]) -> str:
    """사이드바 목차 HTML. h2에는 2자리 번호, h3들은 들여쓴다."""
    items: list[str] = []
    sec_no = 0
    for level, sid, text in toc:
        if level == 2:
            sec_no += 1
            items.append(
                f'<li class="lv2"><a href="#{sid}">'
                f'<span class="toc-num">{sec_no:02d}</span>{text}</a></li>'
            )
        else:
            items.append(f'<li class="lv3"><a href="#{sid}">{text}</a></li>')
    return "\n        ".join(items)


def wrap_tables(html: str) -> str:
    """넓은 표의 가로 스크롤을 위해 table을 .table-wrap으로 감싼다."""
    return re.sub(r"(<table>.*?</table>)", r'<div class="table-wrap">\1</div>', html, flags=re.S)


def mark_warn_blockquotes(html: str) -> str:
    """⚠️ 로 시작하는 blockquote에 warn 클래스를 붙인다 (상충 표시 등)."""
    def repl(m: re.Match) -> str:
        cls = ' class="warn"' if "⚠" in m.group(1)[:80] else ""
        return f"<blockquote{cls}>{m.group(1)}</blockquote>"

    return re.sub(r"<blockquote>(.*?)</blockquote>", repl, html, flags=re.S)


def count_sources(run_dir: Path) -> tuple[int, int]:
    work = run_dir / "_work"
    videos = len(list(work.glob("10_video_*.json")))
    sites = len(list(work.glob("20_site_*.json")))
    return videos, sites


def build_meta_chips(videos: int, sites: int) -> str:
    chips = []
    if videos:
        label = "영상 1개" if videos == 1 else f"영상 {videos}개"
        chips.append(f'<span class="meta-chip"><b>리뷰 소스</b> {label}</span>')
    if sites:
        label = "사이트 1개" if sites == 1 else f"사이트 {sites}개"
        chips.append(f'<span class="meta-chip"><b>공식 문서</b> {label}</span>')
    return "\n      ".join(chips)


def main() -> int:
    parser = argparse.ArgumentParser(description="report.md → report.html")
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    report_md = run_dir / "report.md"
    if not report_md.exists():
        sys.exit(f"report.md가 없습니다: {report_md}")

    md_text = report_md.read_text(encoding="utf-8")
    title, body = extract_title(md_text)

    html = md_lib.markdown(body, extensions=MD_EXTENSIONS)
    html, toc = inject_heading_ids(html)
    html = wrap_tables(html)
    html = mark_warn_blockquotes(html)

    videos, sites = count_sources(run_dir)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    # 본문에 소스 링크가 이미 있으므로 푸터 링크는 brief의 원본 URL을 그대로 노출하지 않는다.
    out = (
        template.replace("{{TITLE}}", title)
        .replace("{{TOC}}", build_toc(toc))
        .replace("{{META_CHIPS}}", build_meta_chips(videos, sites))
        .replace("{{CONTENT}}", html)
        .replace("{{TIMESTAMP}}", datetime.date.today().isoformat())
        .replace("{{SOURCE_LINKS}}", "")
    )

    out_path = run_dir / "report.html"
    out_path.write_text(out, encoding="utf-8")
    print(f"[render_report_html] wrote {out_path}")
    print(f"[render_report_html] sections={len(toc)} videos={videos} sites={sites}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
