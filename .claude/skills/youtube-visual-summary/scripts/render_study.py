#!/usr/bin/env python3
"""Render the study view: RUN_DIR/study.html (+ images/study/*.webp).

Each item is a section with the video segment on the left (sticky player,
local clip, transcript that follows playback) and the explanation on the right.
Reads RUN_DIR/_work/study.json, or derives one item per chapter without it.
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
from pathlib import Path

from common import format_ts
from study_spec import load_study, resolve_scene

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_PATH = SKILL_DIR / "assets" / "study-template.html"

RATES = ["0.75", "1", "1.25", "1.5"]
ICON_PLAY = '<path class="i-play" d="M8 5.5v13l10.5-6.5z"/><path class="i-pause" d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/>'
ICON_LOOP = '<path d="M17 2l4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>'
ICON_FULL = '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>'


def escape(text) -> str:
    return html_mod.escape(str(text))


def render_inline(text: str) -> str:
    """HTML-escape, then apply inline markdown: `code` then **bold**."""
    s = html_mod.escape(str(text))
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def watch_url(url: str, seconds: float) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(seconds)}s"


def to_webp(source: Path, target: Path, max_width: int = 1280) -> None:
    from PIL import Image

    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        im = im.convert("RGB")
        if im.width > max_width:
            im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
        im.save(target, "WEBP", quality=85, method=6)


def build_variant(spec: dict, name: str, scene: dict, label: str, run_dir: Path) -> dict:
    """Everything the player needs for one scene; also writes its poster image."""
    s = resolve_scene(spec, scene)
    src = s["source"]
    image = run_dir / "images" / "study" / f"{name}.webp"
    if not image.exists():
        to_webp(src["internal_dir"] / s["frame"]["image_path"], image)
    clip = run_dir / "clips" / f"{name}.mp4"
    lines = [
        {"t": round(seg["start"], 2), "text": seg["text"]}
        for seg in src["segments"]
        if seg["end"] > s["start"] + 0.5 and seg["start"] < s["end"] - 0.5
    ]
    return {
        "label": label,
        "img": image.relative_to(run_dir).as_posix(),
        "clip": clip.relative_to(run_dir).as_posix() if clip.exists() else None,
        "clipStart": round(s["clip_start"], 2),
        "dur": round(s["clip_dur"], 1),
        "url": watch_url(src["url"], s["start"]),
        "ts": s["start"],
        "lines": lines,
        "paras": s["chapter"].get("summary_paragraphs", []),
    }


def script_lines(lines: list[dict]) -> str:
    return "".join(
        f'<li><button type="button" data-t="{l["t"]}"><time>{format_ts(l["t"])}</time>'
        f'<span>{escape(l["text"])}</span></button></li>'
        for l in lines
    )


def build_subs(item: dict, variants: list[dict]) -> str:
    out = ""
    for i, sub in enumerate(item.get("subs", []), 1):
        v = variants[i]
        en = f' <span class="en">{escape(sub["en"])}</span>' if sub.get("en") else ""
        points = "".join(f"<p>{render_inline(p)}</p>" for p in sub.get("points", []))
        out += f'''
      <div class="also">
        <button type="button" class="also-thumb" data-v="{i}" aria-label="{escape(sub["name"])} 장면 보기">
          <img src="{escape(v["img"])}" alt="" loading="lazy"><span class="mini-play">▶</span></button>
        <div class="also-body">
          <p class="also-kicker">함께 알아두기</p>
          <h4>{escape(sub["name"])}{en}</h4>
          <p class="also-def">{render_inline(sub.get("definition", ""))}</p>{points}
          <button type="button" class="link-btn" data-v="{i}">▶ 이 장면 보기 <span>{format_ts(v["dur"])}</span></button>
        </div>
      </div>'''
    return out


def build_section(item: dict, n: int, count: int, kicker: str, variants: list[dict], names: dict) -> str:
    v0 = variants[0]
    seg_tabs = ""
    if len(variants) > 1:
        seg_tabs = '<div class="seg" role="tablist">' + "".join(
            f'<button type="button" role="tab" class="seg-btn{" on" if i == 0 else ""}" data-v="{i}">{escape(v["label"])}</button>'
            for i, v in enumerate(variants)) + "</div>"
    speed = "".join(f'<button type="button" data-rate="{r}"{" class=on" if r == "1" else ""}>{r}×</button>' for r in RATES)
    en = f'\n    <p class="item-en">{escape(item["en"])}</p>' if item.get("en") else ""
    lead = f'\n    <p class="lead">{render_inline(item["definition"])}</p>' if item.get("definition") else ""
    points = "".join(f"<li>{render_inline(p)}</li>" for p in item.get("points", []))
    points = f'\n    <ul class="points">{points}</ul>' if points else ""
    paras = "".join(f"<p>{render_inline(p)}</p>" for p in v0["paras"])
    deep = (f'\n      <details class="deep"><summary>영상 속 설명 자세히</summary>'
            f'<div class="deep-body">{paras}</div></details>') if paras else ""
    prompt = f'''
      <div class="prompt">
        <div class="prompt-head"><span>AI에게 이렇게 요청</span><button type="button" class="copy">복사</button></div>
        <p class="prompt-text">{escape(item["prompt"])}</p>
      </div>''' if item.get("prompt") else ""
    related = "".join(f'<a href="#{escape(r)}">{escape(names[r])}</a>' for r in item.get("related", []) if r in names)
    related = f'<div class="related"><span>관련</span>{related}</div>' if related else "<div></div>"
    script = ""
    if v0["lines"]:
        script = f'''
    <details class="script" open>
      <summary>자막 따라 읽기 <span class="hint">재생하면 지금 문장이 표시됩니다 · 문장을 누르면 그 지점부터</span></summary>
      <ol>{script_lines(v0["lines"])}</ol>
    </details>'''
    return f'''
<section class="study" id="{escape(item["id"])}" data-item="{escape(item["id"])}">
  <div class="stage">
    <div class="player" data-v="0">
      <img class="poster" src="{escape(v0["img"])}" alt="{escape(item["name"])} 장면" loading="lazy">
      <span class="hover-play" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5.5v13l10.5-6.5z"/></svg></span>
    </div>
    <div class="controls">
      <button type="button" class="play" aria-label="이 구간 재생">
        <svg viewBox="0 0 24 24" aria-hidden="true">{ICON_PLAY}</svg>
        <span class="play-label">구간 재생</span><span class="play-dur">{format_ts(v0["dur"])}</span>
      </button>
      {seg_tabs}
      <div class="ctl-right">
        <div class="speed" aria-label="재생 속도">{speed}</div>
        <button type="button" class="icon loop" title="구간 반복 (L)" aria-pressed="false"><svg viewBox="0 0 24 24">{ICON_LOOP}</svg></button>
        <button type="button" class="icon full" title="크게 보기 (F)"><svg viewBox="0 0 24 24">{ICON_FULL}</svg></button>
        <a class="icon yt" href="{escape(v0["url"])}" target="_blank" rel="noopener" title="유튜브 원본에서 보기">{format_ts(v0["ts"])} ↗</a>
      </div>
    </div>{script}
  </div>
  <article class="notes">
    <p class="kicker"><span>{escape(kicker)}</span> {n:02d} / {count:02d}</p>
    <h3 class="item-title">{escape(item["name"])}</h3>{en}{lead}{points}{build_subs(item, variants)}{deep}{prompt}
    <div class="foot">{related}
      <button type="button" class="done-btn" aria-pressed="false"><span class="box"></span>공부함</button>
    </div>
  </article>
</section>'''


def build_tile(item: dict, v0: dict) -> str:
    en = f'\n      <span class="tile-en">{escape(item["en"])}</span>' if item.get("en") else ""
    return f'''
    <button type="button" class="tile" data-go="{escape(item["id"])}" data-item="{escape(item["id"])}">
      <span class="tile-img"><img src="{escape(v0["img"])}" alt="" loading="lazy"><i class="tile-done">✓</i></span>
      <span class="tile-name">{escape(item["name"])}</span>{en}
      <span class="tile-def">{escape(item.get("definition", ""))}</span>
    </button>'''


def build_body(spec: dict, run_dir: Path) -> tuple[str, str, str, dict]:
    names = {it["id"]: it["name"] for it in spec["items"]}
    sources = spec["_sources"]
    players: dict[str, list[dict]] = {}
    sections, tiles, nav = [], [], []
    for gi, group in enumerate(spec["groups"], 1):
        items = [it for it in spec["items"] if it["group"] == group["id"]]
        if not items:
            continue
        name = group.get("name", "")
        en = f' <span class="en">{escape(group["en"])}</span>' if group.get("en") else ""
        src_label = sources[str(group["source"])].get("label", "") if group.get("source") else ""
        note = " · ".join(x for x in (group.get("note", ""), src_label) if x)
        if name:
            sections.append(f'''
<header class="group" id="g-{escape(group["id"])}">
  <span class="group-no">{gi:02d}</span>
  <div><h2 class="group-name">{escape(name)}{en}</h2>
  <p class="group-note">{escape(note)}</p></div>
</header>''')
        kicker = group.get("en") or name or "Chapter"
        nav_items, group_tiles = [], []
        for n, item in enumerate(items, 1):
            scenes = [(item["id"], item["scene"], item["name"])]
            scenes += [(f'{item["id"]}--{sub["id"]}', sub["scene"], sub["name"]) for sub in item.get("subs", [])]
            variants = [build_variant(spec, nm, sc, label, run_dir) for nm, sc, label in scenes]
            players[item["id"]] = variants
            sections.append(build_section(item, n, len(items), kicker, variants, names))
            nav_items.append(
                f'<li><a href="#{escape(item["id"])}" data-item="{escape(item["id"])}">'
                f'<span class="no">{n:02d}</span>{escape(item["name"])}<i class="dot"></i></a></li>')
            group_tiles.append(build_tile(item, variants[0]))
        nav.append(f'''
<li class="nav-group" data-group="{escape(group["id"])}">
  <button type="button" class="nav-head" aria-expanded="{"true" if gi == 1 else "false"}">
    <span>{escape(name or "목차")}</span><span class="nav-count">0/{len(items)}</span><svg viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>
  </button>
  <ol class="nav-items">{"".join(nav_items)}</ol>
</li>''')
        title = (f'<h2 class="ov-title"><span>{gi:02d}</span>{escape(name)} <em>{escape(group.get("en", ""))}</em></h2>'
                 if name else "")
        tiles.append(f'\n  <div class="ov-group">{title}\n  <div class="tiles">{"".join(group_tiles)}</div></div>')
    return "".join(sections), "".join(tiles), "".join(nav), players


def build_intro_extras(spec: dict, run_dir: Path) -> tuple[str, str, str]:
    sources = spec["_sources"]
    chips = "".join(
        f'<a class="src" href="{escape(s["url"])}" target="_blank" rel="noopener">'
        + (f'<b>{escape(s["label"])}</b>' if s.get("label") else "")
        + f'{escape(s.get("title", ""))}<span>{escape(s.get("duration", ""))}</span></a>'
        for s in sources.values())
    formulas = "".join(f'''
    <div class="formula"><p class="formula-k">{escape(f.get("label", ""))}</p><p class="formula-t">{escape(f["text"])}</p><p class="formula-ex">{escape(f.get("example", ""))}</p></div>'''
                       for f in spec.get("formulas", []))
    formulas = f'\n      <div class="formulas">{formulas}</div>' if formulas else ""
    figures = ""
    for i, cheat in enumerate(spec.get("cheatsheets", []), 1):
        s = resolve_scene(spec, cheat)
        image = run_dir / "images" / "study" / f"cheatsheet-{i}.webp"
        if not image.exists():
            to_webp(s["source"]["internal_dir"] / s["frame"]["image_path"], image, 1600)
        figures += (f'<figure><img src="{escape(image.relative_to(run_dir).as_posix())}" alt="{escape(cheat.get("caption", ""))}" loading="lazy">'
                    f'<figcaption>{escape(cheat.get("caption", ""))}</figcaption></figure>')
    cheats = f'''
    <section class="cheats" id="cheats">
      <h2>한눈에 보는 정리 화면</h2>
      <p>영상에 나온 전체 정리 화면입니다. 복습할 때 이 화면으로 전체를 다시 떠올려 보세요.</p>
      <div class="cheat-grid">{figures}</div>
    </section>''' if figures else ""
    return chips, formulas, cheats


def main() -> int:
    parser = argparse.ArgumentParser(description="Render study.html for a run.")
    parser.add_argument("run_dir")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    spec = load_study(run_dir)
    sections, tiles, nav, players = build_body(spec, run_dir)
    chips, formulas, cheats = build_intro_extras(spec, run_dir)
    total = len(spec["items"])
    missing = sum(1 for vs in players.values() for v in vs if not v["clip"])

    result = TEMPLATE_PATH.read_text(encoding="utf-8")
    for key, value in {
        "TITLE": escape(spec["title"]),
        "SUBTITLE": escape(spec.get("subtitle", "")),
        "SOURCES": chips,
        "FORMULAS": formulas,
        "NAV": nav,
        "SECTIONS": sections,
        "TILES": tiles,
        "CHEATS": cheats,
        "TOTAL": str(total),
        "PLAYERS": json.dumps(players, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        result = result.replace("{{" + key + "}}", value)
    out = run_dir / "study.html"
    out.write_text(result, encoding="utf-8")
    note = f" ({missing} scenes without a local clip → YouTube deep link)" if missing else ""
    print(f"{out} — {total} items{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
