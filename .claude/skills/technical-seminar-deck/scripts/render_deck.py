#!/usr/bin/env python3
"""deck.json → 자기 완결형 deck.html (+ deck.md).

- SVG는 인라인으로 삽입한다. 부모 문서의 --dg-* CSS 토큰을 상속받아 다크모드가 자동 대응된다.
- 프레임 이미지는 base64로 임베드한다. HTML 한 파일만 공유하면 그대로 열린다.
- 여러 SVG의 id/marker 충돌을 막기 위해 id를 slug로 네임스페이싱한다.

사용법:
    python render_deck.py RUN_DIR [--deck _work/05_deck.json] [--out deck.html]
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import re
import sys
from datetime import datetime
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent / "assets" / "deck-template.html"

KIND_LABEL = {
    "cover": "표지", "agenda": "전체 지도", "section": "섹션", "problem": "문제",
    "prereq": "배경 지식", "concept": "핵심 개념", "architecture": "시스템 구조",
    "math": "수식", "demo": "데모", "result": "결과", "limitation": "한계",
    "qa": "Q&A", "takeaway": "정리", "refs": "참고문헌", "glossary": "용어집",
}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def fmt_ts(sec) -> str:
    try:
        sec = int(float(sec))
    except (TypeError, ValueError):
        return ""
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def yt_link(url: str, t) -> str:
    if not url:
        return ""
    try:
        t = int(float(t))
    except (TypeError, ValueError):
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={t}s"


ID_ATTR = re.compile(r'\bid="([^"]+)"')
URL_REF = re.compile(r'url\(#([^)]+)\)')
HREF_REF = re.compile(r'(xlink:href|href)="#([^"]+)"')


def inline_svg(path: Path, ns: str) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"<\?xml[^>]*\?>", "", raw)
    raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw, flags=re.I)
    ids = set(ID_ATTR.findall(raw))
    for i in sorted(ids, key=len, reverse=True):
        new = f"{ns}__{i}"
        raw = raw.replace(f'id="{i}"', f'id="{new}"')
        raw = raw.replace(f"url(#{i})", f"url(#{new})")
        raw = raw.replace(f'href="#{i}"', f'href="#{new}"')
    # 크기는 CSS가 정한다 — 인라인 style/width/height를 제거해야 발표 모드에서 높이를 채울 수 있다
    raw = raw.strip()
    head_end = raw.find(">")
    head = re.sub(r'\s(?:width|height)="[^"]*"', "", raw[:head_end])
    head = re.sub(r'\sstyle="[^"]*"', "", head)
    raw = head + raw[head_end:]
    if 'role=' not in raw.split(">", 1)[0]:
        raw = raw.replace("<svg", '<svg role="img"', 1)
    return raw


def embed_img(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def render_visual(slide: dict, run_dir: Path, warnings: list) -> str:
    v = slide.get("visual") or {}
    vtype = v.get("type", "none")
    if vtype == "none" or not v.get("src"):
        return ""
    src = run_dir / v["src"]
    cap = v.get("caption", "")
    alt = v.get("alt", "") or cap
    if not src.exists():
        warnings.append(f"{slide['id']}: 비주얼 파일 없음 → {v['src']}")
        return f'<div class="visual"><div class="novisual">비주얼 자산 누락: {esc(v["src"])}</div></div>'
    # 무거운 자산은 DOM에 상주시키지 않는다 — 59장 전체가 렌더 트리에 있으면
    # Chrome이 래스터 예산 때문에 SVG를 저해상도로 그린다. 활성 슬라이드만 주입한다.
    figcap = f'<figcaption>{esc(cap)}</figcaption>' if cap else ""
    if vtype == "svg" or src.suffix.lower() == ".svg":
        ns = re.sub(r"[^A-Za-z0-9_-]", "-", src.stem)
        holder = f"svgsrc-{slide['id']}"
        payload = f'<script type="text/html" id="{holder}">{inline_svg(src, ns)}</script>'
        box = f'<div class="frame" data-svg-id="{holder}"></div>'
    else:
        payload = ""
        box = (f'<div class="frame"><img data-src="{embed_img(src)}" '
               f'alt="{esc(alt)}" decoding="async"></div>')
    return f'<figure class="visual">{box}{figcap}</figure>{payload}'


def render_notes(slide: dict, meta: dict) -> str:
    n = slide.get("notes") or {}
    if not any(n.get(k) for k in ("why", "explain", "analogy", "terms", "source", "research", "caveat")):
        return ""
    parts = ['<section class="notes"><h3>해설 노트</h3>']
    if n.get("why"):
        parts.append(f'<div class="why">{esc(n["why"])}</div>')
    for p in n.get("explain") or []:
        parts.append(f"<p>{esc(p)}</p>")
    if n.get("analogy"):
        parts.append(f'<div class="analogy">{esc(n["analogy"])}</div>')
    src = n.get("source") or {}
    if src.get("quote"):
        parts.append(f'<blockquote class="quote">{esc(src["quote"])}</blockquote>')
    if n.get("caveat"):
        parts.append(f'<div class="caveat">{esc(n["caveat"])}</div>')

    chips = []
    if src.get("t") is not None:
        link = yt_link(meta.get("source_url", ""), src["t"])
        chips.append(f'<a class="chip t" href="{esc(link)}" target="_blank" rel="noopener">원문 {esc(fmt_ts(src["t"]))}</a>')
    for term in n.get("terms") or []:
        chips.append(f'<span class="chip term">{esc(term)}</span>')
    for r in n.get("research") or []:
        label = r.get("title") or r.get("claim") or "출처"
        if r.get("url"):
            chips.append(f'<a class="chip" href="{esc(r["url"])}" target="_blank" rel="noopener">{esc(label[:52])}</a>')
        else:
            chips.append(f'<span class="chip">{esc(label[:52])}</span>')
    if chips:
        parts.append('<div class="meta-row">' + "".join(chips) + "</div>")
    parts.append("</section>")
    return "".join(parts)


def render_slide(idx: int, total: int, slide: dict, sec_title: str, run_dir: Path,
                 meta: dict, warnings: list) -> str:
    kind = slide.get("kind", "concept")
    kl = KIND_LABEL.get(kind, kind)
    visual = render_visual(slide, run_dir, warnings)
    bullets = slide.get("bullets") or []
    bl = ""
    if bullets:
        bl = '<ul class="bullets">' + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>"
    if slide.get("html_body"):
        bl += slide["html_body"]  # 표 등 사전 렌더된 조각 (신뢰된 입력)
    # 표지에는 원본 영상 링크를 항상 노출한다 — 보고서만 받은 사람이 원문을 찾을 수 있어야 한다
    if kind == "cover" and meta.get("source_url"):
        url = meta["source_url"]
        dur = fmt_ts(meta.get("duration_sec"))
        bl += ('<p class="source-link"><a href="{u}" target="_blank" rel="noopener">'
               '▶ 원본 영상 보기 — YouTube{d}</a><br><span class="url">{u}</span></p>'
               ).format(u=esc(url), d=f" · {esc(dur)}" if dur else "")
    # SVG 도해는 축소 렌더링되면 작은 라벨이 뭉개진다 → 발표 모드에서 전폭 배치하도록 표시한다
    vkind = (slide.get("visual") or {}).get("type", "none")
    body_cls = "body"
    if visual:
        body_cls += " has-visual vis-svg" if vkind == "svg" else " has-visual vis-frame"
    lead = f'<p class="lead">{esc(slide["lead"])}</p>' if slide.get("lead") else ""
    return f"""
<article class="slide" id="{esc(slide['id'])}">
  <div class="card">
    <div class="eyebrow"><span class="kind">{esc(kl)}</span><span>{esc(sec_title)}</span>
      <span class="spacer"></span><span>{idx+1} / {total}</span></div>
    <h2>{esc(slide.get('title',''))}</h2>
    {lead}
    <div class="{body_cls}"><div>{bl}</div>{visual}</div>
  </div>
  {render_notes(slide, meta)}
</article>"""


def build_overview(deck: dict) -> str:
    sec_by_id = {s["id"]: s.get("title", "") for s in deck.get("sections", [])}
    out, cur, buf, i = [], None, [], 0
    for slide in deck["slides"]:
        sid = slide.get("section_id")
        if sid != cur:
            if buf:
                out.append(f'<p class="ov-sec">{esc(sec_by_id.get(cur, ""))}</p><div class="ov-grid">' + "".join(buf) + "</div>")
            buf, cur = [], sid
        buf.append(
            f'<button class="ov-item" data-i="{i}"><span class="n">{i+1:02d} · '
            f'{esc(KIND_LABEL.get(slide.get("kind",""), slide.get("kind","")))}</span>'
            f'<span class="t">{esc(slide.get("title",""))}</span></button>'
        )
        i += 1
    if buf:
        out.append(f'<p class="ov-sec">{esc(sec_by_id.get(cur, ""))}</p><div class="ov-grid">' + "".join(buf) + "</div>")
    return "\n".join(out)


def append_appendix(deck: dict) -> None:
    """용어집·참고문헌·한계 슬라이드를 덱 끝에 자동 추가한다."""
    slides = deck["slides"]
    have = {s["id"] for s in slides}
    sec_id = "sec-appendix"
    if not any(s["id"] == sec_id for s in deck.get("sections", [])):
        deck.setdefault("sections", []).append({"id": sec_id, "title": "부록", "goal": "용어·출처·한계"})

    g = deck.get("glossary") or []
    if g and "apx-glossary" not in have:
        def _first(t):
            fs = t.get("first_slide")
            return '<a href="#{0}">{0}</a>'.format(esc(fs)) if fs else ""
        rows = "".join(
            f"<tr><td><strong>{esc(t.get('term',''))}</strong></td><td>{esc(t.get('ko',''))}</td>"
            f"<td>{esc(t.get('def',''))}</td><td>{_first(t)}</td></tr>"
            for t in g
        )
        slides.append({
            "id": "apx-glossary", "section_id": sec_id, "kind": "glossary",
            "title": "용어집", "lead": "이 보고서에서 처음 정의한 용어 전체",
            "html_body": f"<table><thead><tr><th>원어</th><th>한글</th><th>정의</th><th>최초 등장</th></tr></thead><tbody>{rows}</tbody></table>",
        })

    refs = deck.get("references") or []
    if refs and "apx-refs" not in have:
        items = "".join(
            f'<li><a href="{esc(r.get("url",""))}" target="_blank" rel="noopener">{esc(r.get("title",""))}</a>'
            f'{" — " + esc(r["note"]) if r.get("note") else ""}</li>' for r in refs
        )
        slides.append({
            "id": "apx-refs", "section_id": sec_id, "kind": "refs",
            "title": "참고문헌 · 더 읽을거리", "lead": "본문 주장의 근거와 후속 학습 자료",
            "html_body": f'<ul class="bullets">{items}</ul>',
        })

    gaps = deck.get("gaps") or []
    if gaps and "apx-gaps" not in have:
        items = "".join(f"<li>{esc(x)}</li>" for x in gaps)
        slides.append({
            "id": "apx-gaps", "section_id": sec_id, "kind": "limitation",
            "title": "이 보고서가 다루지 못한 것", "lead": "원문 대비 누락과 그 이유를 밝힌다",
            "html_body": f'<ul class="bullets">{items}</ul>',
        })


def render_markdown(deck: dict, run_dir: Path) -> str:
    meta = deck.get("meta", {})
    L = [f"# {meta.get('title','')}", ""]
    if meta.get("subtitle"):
        L += [f"> {meta['subtitle']}", ""]
    L += [
        f"- **원본:** [{meta.get('title','')}]({meta.get('source_url','')})",
        f"- **발표자:** {meta.get('speaker','-')} · **자리:** {meta.get('venue','-')} · **일자:** {meta.get('date','-')}",
        f"- **대상 독자:** {meta.get('audience','-')}",
        "", "---", "",
    ]
    sec_by_id = {s["id"]: s for s in deck.get("sections", [])}
    cur = None
    for i, s in enumerate(deck["slides"]):
        if s.get("section_id") != cur:
            cur = s.get("section_id")
            sec = sec_by_id.get(cur, {})
            L += [f"## {sec.get('title','')}", ""]
            if sec.get("goal"):
                L += [f"*{sec['goal']}*", ""]
        L += [f"### {i+1:02d}. {s.get('title','')}", ""]
        if s.get("lead"):
            L += [f"**{s['lead']}**", ""]
        for b in s.get("bullets") or []:
            L.append(f"- {b}")
        if s.get("bullets"):
            L.append("")
        v = s.get("visual") or {}
        if v.get("src"):
            L += [f"![{v.get('alt','')}]({v['src']})", "", f"*{v.get('caption','')}*", ""]
        n = s.get("notes") or {}
        if n:
            L += ["<details><summary>해설 노트</summary>", ""]
            if n.get("why"):
                L += [f"**왜 중요한가.** {n['why']}", ""]
            for p in n.get("explain") or []:
                L += [p, ""]
            if n.get("analogy"):
                L += [f"> **비유.** {n['analogy']}", ""]
            if n.get("caveat"):
                L += [f"> **유의.** {n['caveat']}", ""]
            src = n.get("source") or {}
            if src.get("t") is not None:
                L += [f"원문: [{fmt_ts(src['t'])}]({yt_link(meta.get('source_url',''), src['t'])})", ""]
            for r in n.get("research") or []:
                L += [f"출처: [{r.get('title','')}]({r.get('url','')})", ""]
            L += ["</details>", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--deck", default="_work/05_deck.json")
    ap.add_argument("--out", default="deck.html")
    ap.add_argument("--md", default="deck.md")
    args = ap.parse_args()

    run_dir: Path = args.run_dir
    deck = json.loads((run_dir / args.deck).read_text(encoding="utf-8"))
    append_appendix(deck)

    meta = deck.get("meta", {})
    sec_by_id = {s["id"]: s.get("title", "") for s in deck.get("sections", [])}
    warnings: list[str] = []
    total = len(deck["slides"])
    slides_html = "\n".join(
        render_slide(i, total, s, sec_by_id.get(s.get("section_id"), ""), run_dir, meta, warnings)
        for i, s in enumerate(deck["slides"])
    )

    tpl = TPL.read_text(encoding="utf-8")
    out = (tpl
           .replace("{{TITLE}}", esc(meta.get("title", "기술 세미나 보고서")))
           .replace("{{SLIDE_COUNT}}", str(total))
           .replace("{{SLIDES}}", slides_html)
           .replace("{{OVERVIEW}}", build_overview(deck))
           .replace("{{GENERATED_AT}}", datetime.now().strftime("%Y-%m-%d %H:%M")))

    (run_dir / args.out).write_text(out, encoding="utf-8")
    (run_dir / args.md).write_text(render_markdown(deck, run_dir), encoding="utf-8")

    size_mb = (run_dir / args.out).stat().st_size / 1_048_576
    print(f"[render_deck] {total} slides → {run_dir / args.out} ({size_mb:.1f} MB)")
    print(f"[render_deck] markdown → {run_dir / args.md}")
    for w in warnings:
        print(f"[render_deck] WARN {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
